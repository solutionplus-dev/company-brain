#!/usr/bin/env python3
"""Minimal PostgREST client for the brain store (standard library only).

Secrets: the key is read from .env by variable name, held in a Secret whose repr is a placeholder,
sent only as request headers, and scrubbed from every message this module prints or raises.
"""
from __future__ import annotations

import ssl
import http.client
import base64
import ipaddress
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import brain_redact


class Secret:
    __slots__ = ("_v", "name")

    def __init__(self, name: str, value: str):
        self.name, self._v = name, value

    def reveal(self) -> str:
        return self._v

    def __repr__(self):
        return f"<secret {self.name}>"

    __str__ = __repr__


class RefusedError(Exception):
    pass


class RestError(Exception):
    def __init__(self, msg, status=None, code=None):
        super().__init__(msg)
        self.status, self.code = status, code


class AuthError(RestError):
    pass


def read_env(path, names) -> dict:
    out = {}
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError:
        raise RefusedError(f"cannot read the env file {path}") from None
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        if k in names and v:
            out[k] = Secret(k, v)
    return out


def key_kind(value: str) -> str:
    if value.startswith("sb_secret_"):
        return "secret"
    if value.startswith("sb_publishable_"):
        return "publishable"
    parts = value.split(".")
    if len(parts) == 3 and value.startswith("eyJ"):
        try:
            pad = parts[1] + "=" * (-len(parts[1]) % 4)
            role = json.loads(base64.urlsafe_b64decode(pad)).get("role")
        except (ValueError, json.JSONDecodeError):
            return "unknown"
        return "service_role" if role == "service_role" else f"jwt:{role}"
    return "unknown"


def check_url(url: str, project_ref: str | None, allow_loopback: bool) -> str:
    p = urllib.parse.urlparse(url.strip().rstrip("/"))
    host = p.hostname or ""
    if p.scheme == "https" and host.endswith(".supabase.co"):
        if project_ref and host.split(".")[0] != project_ref:
            raise RefusedError("supabase_url does not match supabase_project_ref")
        return f"https://{host}"
    if allow_loopback and p.scheme == "http":
        try:
            if host == "localhost" or ipaddress.ip_address(host).is_loopback:
                return f"http://{host}:{p.port}" if p.port else f"http://{host}"
        except ValueError:
            pass
    raise RefusedError("supabase_url must be https://<project-ref>.supabase.co")


class Rest:
    def __init__(self, base: str, key: Secret, debug=False, sleep=time.sleep, tries=5, timeout=90,
                 log=None):
        kind = key_kind(key.reveal())
        if kind not in ("secret", "service_role"):
            raise RefusedError(f"the .env variable '{key.name}' does not hold a secret / service-role key "
                               f"(found: {kind.split(':')[0]}); refusing to write with it")
        self.base, self.key, self.kind = base, key, kind
        self.debug, self.sleep, self.tries, self.timeout = debug, sleep, tries, timeout
        self.log = log or sys.stderr
        self.requests = 0

    def scrub(self, s: str) -> str:
        s = s.replace(self.key.reveal(), "[redacted]")
        return brain_redact.redact(s)[0]

    def _headers(self, extra) -> dict:
        h = {"apikey": self.key.reveal(), "Accept": "application/json",
             "Content-Type": "application/json", "User-Agent": "brain-sync/1"}
        if self.kind == "service_role":  # legacy JWT key: PostgREST also needs it as bearer
            h["Authorization"] = "Bearer " + self.key.reveal()
        h.update(extra or {})
        return h

    def request(self, method: str, path: str, params=None, body=None, headers=None):
        params = list(params or [])
        if method in ("DELETE", "PATCH"):
            names = {k for k, v in params if str(v).startswith("eq.") or str(v).startswith("in.")}
            if "scope" not in names and not (method == "PATCH" and "id" in names):
                raise RestError(f"refusing {method} without a scope filter")
        qs = urllib.parse.urlencode(params, quote_via=urllib.parse.quote, safe="(),.:*_-")
        url = f"{self.base}/rest/v1/{path}" + (f"?{qs}" if qs else "")
        data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8") if body is not None else None
        hdrs = self._headers(headers)
        for attempt in range(self.tries):
            self.requests += 1
            req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                    self._trace(method, path, qs, hdrs, data, resp.status)
                    return resp.status, dict(resp.headers), (json.loads(raw) if raw.strip() else None)
            except urllib.error.HTTPError as e:
                raw = e.read()[:4000]
                self._trace(method, path, qs, hdrs, data, e.code)
                code = msg = None
                try:
                    j = json.loads(raw)
                    code, msg = j.get("code"), j.get("message")
                except (ValueError, AttributeError):
                    pass
                if e.code in (401, 403):
                    raise AuthError(f"HTTP {e.code}: the key in .env variable '{self.key.name}' was refused "
                                    f"(check it is this project's secret key and that supabase_url is right)",
                                    e.code, code) from None
                if e.code == 429 or e.code >= 500:
                    if attempt + 1 < self.tries:
                        self._backoff(attempt, e.headers.get("Retry-After"))
                        continue
                detail = f" {self.scrub(str(msg))[:200]}" if self.debug and msg else ""
                raise RestError(f"HTTP {e.code} {code or ''} on {method} {path}{detail}".strip(), e.code, code) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError, ssl.SSLError, http.client.HTTPException, OSError) as e:  # a broken TLS record or a dropped connection is retried like a timeout
                if attempt + 1 < self.tries:
                    self._backoff(attempt, None)
                    continue
                raise RestError(f"network error on {method} {path}: {e.__class__.__name__}") from None
        raise RestError(f"gave up on {method} {path}")

    def _backoff(self, attempt, retry_after):
        try:
            wait = float(retry_after) if retry_after else 2 ** attempt
        except ValueError:
            wait = 2 ** attempt
        self.sleep(min(wait, 30))

    def _trace(self, method, path, qs, hdrs, data, status):
        if not self.debug:
            return
        shown = {k: ("[redacted]" if k.lower() in ("apikey", "authorization") else v) for k, v in hdrs.items()}
        q = self.scrub(qs)[:160]
        self.log.write(f"[http] {method} /rest/v1/{path}{'?' + q if q else ''} headers={shown} "
                       f"body={len(data) if data else 0} bytes -> {status}\n")

    # -- helpers
    def get_all(self, table, select, filters, order, page=1000):
        out, off = [], 0
        while True:
            _, _, rows = self.request("GET", table, [("select", select), *filters, ("order", order),
                                                     ("limit", str(page)), ("offset", str(off))])
            rows = rows or []
            out.extend(rows)
            if len(rows) < page:
                return out
            off += page

    def count(self, table, filters) -> int:
        _, h, _ = self.request("GET", table, [("select", "*"), *filters, ("limit", "1")],
                               headers={"Prefer": "count=exact"})
        cr = {k.lower(): v for k, v in h.items()}.get("content-range", "*/0")
        m = re.search(r"/(\d+)$", cr)
        return int(m.group(1)) if m else 0

    def upsert(self, table, rows, on_conflict, batch):
        for i in range(0, len(rows), batch):
            self.request("POST", table, [("on_conflict", on_conflict)], rows[i:i + batch],
                         {"Prefer": "resolution=merge-duplicates,return=minimal"})

    def delete_in(self, table, scope, column, ids, extra=(), batch=50):
        n = 0
        ids = list(ids)
        for i in range(0, len(ids), batch):
            part = ids[i:i + batch]
            self.request("DELETE", table, [("scope", "eq." + scope), *extra,
                                           (column, "in.(" + ",".join(part) + ")")],
                         headers={"Prefer": "return=minimal"})
            n += len(part)
        return n

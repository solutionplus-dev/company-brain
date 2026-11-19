#!/usr/bin/env bash
# Idempotent setup for the vault embedding lane.
#   1. tools/index/.venv        Python 3.12 private environment (uv)
#   2. pinned packages          mlx, transformers, numpy, pathspec, mlx-vlm at a git commit
#   3. .index/models/...        the 4-bit model files, pinned revision, sha256-checked
# Installs nothing system-wide and starts no service. Safe to re-run.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
VENV="$ROOT/tools/index/.venv"
PY="$VENV/bin/python"
CFG="$HERE/embed_config.json"

cfg() { python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(eval('d'+sys.argv[2]))" "$CFG" "$1"; }

REPO="$(cfg "['model']['repo']")"
REV="$(cfg "['model']['revision']")"
LOCAL_DIR="$ROOT/$(cfg "['model']['local_dir']")"
WEIGHTS_SHA="$(cfg "['model']['weights_sha256']")"
TOK_SHA="$(cfg "['model']['tokenizer_sha256']")"
MLX_VLM_COMMIT="$(cfg "['runtime']['mlx_vlm_commit']")"
MLX_VLM_GIT="$(cfg "['runtime']['mlx_vlm_git']")"
MLX_VER="$(cfg "['runtime']['packages']['mlx']")"
TRF_VER="$(cfg "['runtime']['packages']['transformers']")"
NUMPY_VER="$(cfg "['runtime']['packages']['numpy']")"
PATHSPEC_VER="$(cfg "['runtime']['packages']['pathspec']")"
FILES="$(cfg "['model']['files']" | python3 -c "import sys,ast; print('\n'.join(ast.literal_eval(sys.stdin.read())))")"

echo "[setup] root=$ROOT"

# 1. private environment: arm64 Python 3.12 (an x86_64 interpreter cannot install the MLX wheels)
if [ -x "$PY" ] && ! "$PY" -c "import platform,sys; sys.exit(0 if platform.machine()=='arm64' else 1)"; then
  echo "[setup] venv is not arm64; moving it aside to .index/"
  mv "$VENV" "$ROOT/.index/venv_discarded_$(date +%Y%m%d%H%M%S)"
fi
if [ ! -x "$PY" ]; then
  echo "[setup] creating $VENV (Python 3.12, arm64)"
  uv venv --python cpython-3.12-macos-aarch64-none "$VENV"
else
  echo "[setup] venv present: $("$PY" -V) $("$PY" -c 'import platform; print(platform.machine())')"
fi

# 2. pinned packages (only when missing or at the wrong version)
need_pkgs=$("$PY" - <<EOF
import importlib.metadata as md
want = {"mlx": "$MLX_VER", "transformers": "$TRF_VER", "numpy": "$NUMPY_VER", "pathspec": "$PATHSPEC_VER"}
missing = []
for name, ver in want.items():
    try:
        have = md.version(name)
    except md.PackageNotFoundError:
        have = None
    if have != ver:
        missing.append(f"{name}=={ver}")
print(" ".join(missing))
EOF
)
if [ -n "$need_pkgs" ]; then
  echo "[setup] installing: $need_pkgs"
  uv pip install --python "$PY" $need_pkgs
else
  echo "[setup] pinned packages present"
fi

# mlx-vlm at the commit the model card validates against
if ! "$PY" -c "import mlx_vlm.embedding_loader" >/dev/null 2>&1; then
  echo "[setup] installing mlx-vlm @ $MLX_VLM_COMMIT"
  uv pip install --python "$PY" "mlx-vlm @ git+$MLX_VLM_GIT@$MLX_VLM_COMMIT"
else
  echo "[setup] mlx-vlm present"
fi

# 3. model files (pinned revision; weights and tokenizer checked by sha256)
mkdir -p "$LOCAL_DIR"
sha_of() { shasum -a 256 "$1" | awk '{print $1}'; }
for f in $FILES; do
  dest="$LOCAL_DIR/$f"
  mkdir -p "$(dirname "$dest")"
  want=""
  case "$f" in
    model.safetensors) want="$WEIGHTS_SHA" ;;
    tokenizer.json) want="$TOK_SHA" ;;
  esac
  if [ -f "$dest" ] && { [ -z "$want" ] || [ "$(sha_of "$dest")" = "$want" ]; }; then
    continue
  fi
  echo "[setup] downloading $f"
  curl -L --fail --retry 3 -o "$dest.part" "https://huggingface.co/$REPO/resolve/$REV/$f"
  if [ -n "$want" ] && [ "$(sha_of "$dest.part")" != "$want" ]; then
    echo "[setup] sha256 mismatch for $f" >&2
    rm -f "$dest.part"   # our own partial download, not a vault file
    exit 1
  fi
  mv "$dest.part" "$dest"
done
echo "[setup] model files verified in $LOCAL_DIR"

# 4. smoke test: the runtime imports, the model loads, output is 768-d and finite
"$PY" "$HERE/embed.py" selftest
echo "[setup] done"

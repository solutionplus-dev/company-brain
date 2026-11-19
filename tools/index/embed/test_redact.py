#!/usr/bin/env python3
"""Unit tests for redact.py. Run: python3 tools/index/embed/test_redact.py"""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from redact import redact, MARK  # noqa: E402


class RedactTests(unittest.TestCase):
    def test_iban_valid_is_redacted(self):
        out, n = redact("Bankverbindung DE89 3704 0044 0532 0130 00 für die Miete")
        self.assertIn(MARK, out)
        self.assertNotIn("3704", out)
        self.assertGreaterEqual(n, 1)

    def test_iban_invalid_check_digits_kept(self):
        out, _ = redact("Referenz DE12 3456 7890 1234 5678 90")
        self.assertIn("DE12 3456 7890 1234 5678 90", out)

    def test_birth_date_after_keyword_redacted(self):
        out, n = redact("Max Muster, geboren am 12.03.1980 in Hamburg")
        self.assertEqual(out, "Max Muster, geboren am [redacted] in Hamburg")
        self.assertEqual(n, 1)

    def test_geburtsdatum_written_month_redacted(self):
        out, _ = redact("Geburtsdatum: 1. Januar 1985")
        self.assertIn(MARK, out)
        self.assertNotIn("1985", out)

    def test_dob_english_redacted(self):
        out, _ = redact("DOB 1985-06-30 on file")
        self.assertIn(MARK, out)

    def test_invoice_date_kept(self):
        out, n = redact("Rechnung vom 12.03.2030 über 123,45 EUR")
        self.assertEqual(out, "Rechnung vom 12.03.2030 über 123,45 EUR")
        self.assertEqual(n, 0)

    def test_activation_token_redacted(self):
        out, _ = redact("Aktivierungscode: AB12-CD34-EF56")
        self.assertEqual(out, "Aktivierungscode: [redacted]")

    def test_legitimierungs_id_redacted(self):
        out, _ = redact("Legitimierungs-ID 884213 gilt 10 Minuten")
        self.assertNotIn("884213", out)

    def test_password_token_redacted(self):
        out, _ = redact("Passwort: geheim123")
        self.assertEqual(out, "Passwort: [redacted]")

    def test_password_stopword_kept(self):
        out, n = redact("Passwort ist im Tresor")
        self.assertEqual(out, "Passwort ist im Tresor")
        self.assertEqual(n, 0)

    def test_uppercase_pin_redacted_lowercase_kept(self):
        out, _ = redact("PIN 4711 und pin the file")
        self.assertIn("PIN [redacted]", out)
        self.assertIn("pin the file", out)

    def test_international_phone_redacted(self):
        out, _ = redact("Anruf unter +44 20 7946 0958 heute")
        self.assertIn(MARK, out)
        self.assertNotIn("7946", out)

    def test_national_phone_redacted(self):
        out, _ = redact("Tel. 0170 1234567")
        self.assertEqual(out, "Tel. [redacted]")

    def test_register_tax_vat_invoice_numbers_kept(self):
        text = ("HRB 123456, Steuernummer 12/345/67890, USt-IdNr DE123456789, "
                "Rechnung 2030000123")
        out, n = redact(text)
        self.assertEqual(out, text)
        self.assertEqual(n, 0)

    def test_short_dates_not_taken_for_phones(self):
        out, n = redact("Stichtag 05-12-2030 und 2030-12-05")
        self.assertEqual(out, "Stichtag 05-12-2030 und 2030-12-05")
        self.assertEqual(n, 0)

    def test_private_email_redacted_company_kept(self):
        out, _ = redact("Von max.muster@gmail.com an info@example-studio.test")
        self.assertIn("[redacted]", out)
        self.assertIn("info@example-studio.test", out)
        self.assertNotIn("gmail", out)

    def test_plain_text_unchanged(self):
        text = "Der Vertrag wurde am 3. März 2026 unterschrieben."
        self.assertEqual(redact(text), (text, 0))


if __name__ == "__main__":
    unittest.main()

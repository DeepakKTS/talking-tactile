"""Tests for scripts/preflight.py's decisions. Run: python3 -m unittest -v scripts/test_preflight.py

The checks that ask the machine (lsof, openssl, gh, git, the API) are run by make preflight
itself; these cover what each answer is judged to mean."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import preflight as pf

# Built from parts so this file does not itself hold an assignment the secret check refuses.
SET = pf.KEY_NAME + "="


class KeyLineTest(unittest.TestCase):
    def test_a_value_counts_with_quotes_spaces_or_export(self) -> None:
        for text in (SET + "abc", f'{SET}"abc"', f"export {SET}abc", "OTHER=1\n" + pf.KEY_NAME + " = abc\n"):
            self.assertTrue(pf.key_line_set(text), text)

    def test_an_empty_value_or_another_name_does_not(self) -> None:
        for text in ("", SET, SET + '""', SET + "   ", "#" + SET + "abc", "OTHER_" + SET + "abc"):
            self.assertFalse(pf.key_line_set(text), text)


class CertTest(unittest.TestCase):
    def test_names_and_addresses_come_from_the_san_line(self) -> None:
        text = ("X509v3 Subject Alternative Name: \n"
                "    DNS:Mac.local, DNS:localhost, IP Address:192.168.1.10, IP Address:127.0.0.1, IP Address:0:0:0:0:0:0:0:1\n")
        names = pf.cert_names(text)
        self.assertLessEqual({"Mac.local", "localhost", "192.168.1.10", "127.0.0.1"}, names)
        self.assertNotIn("192.168.1.11", names)


class PortTest(unittest.TestCase):
    def test_free_or_the_right_server_is_ok(self) -> None:
        self.assertTrue(pf.port_ok(8000, None))
        self.assertTrue(pf.port_ok(8000, ("Python", "1")))
        self.assertTrue(pf.port_ok(5173, ("node", "2")))
        self.assertTrue(pf.port_ok(8443, ("python3.11", "3")))

    def test_anything_else_on_a_demo_port_fails(self) -> None:
        self.assertFalse(pf.port_ok(5173, ("Python", "1")))
        self.assertFalse(pf.port_ok(8000, ("ControlCenter", "4")))


class FigureTest(unittest.TestCase):
    def test_a_published_sheet_with_regions_is_ok(self) -> None:
        ok, detail = pf.figure_detail(200, json.dumps({"regions": [{}, {}]}).encode())
        self.assertEqual((ok, detail), (True, "2 regions"))

    def test_an_error_no_json_or_no_regions_fails(self) -> None:
        self.assertFalse(pf.figure_detail(404, b'{"error": "not_published"}')[0])
        self.assertFalse(pf.figure_detail(0, b"connection refused")[0])
        self.assertFalse(pf.figure_detail(200, b"<html>")[0])
        self.assertFalse(pf.figure_detail(200, b"[]")[0])
        self.assertFalse(pf.figure_detail(200, b'{"regions": []}')[0])


class CreditsTest(unittest.TestCase):
    def test_enough_left_is_ok_and_too_little_fails(self) -> None:
        self.assertEqual(pf.credits_left(5.308, 150), (True, "$144.69 of $150 left (spent $5.31)"))
        self.assertFalse(pf.credits_left(145.0, 150)[0])


if __name__ == "__main__":
    unittest.main()

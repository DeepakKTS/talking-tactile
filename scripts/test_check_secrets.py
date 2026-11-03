"""Tests for scripts/check_secrets.py. Run: python3 -m unittest -v scripts/test_check_secrets.py

Each test builds a throwaway git repo with a fake key in services/api/.env, stages files and
runs the check the way the pre-commit hook does. The fake key must never appear in the output.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CHECK = Path(__file__).resolve().parent / "check_secrets.py"
FAKE_KEY = "LLM_fake0123456789abcdefFAKEKEY"
# Built from parts so this file does not itself hold an assignment the check refuses.
ASSIGN = "MODEL_API_KEY" + "="


# The throwaway repos must never see the real repository's git settings. Under the pre-commit
# hook of a commit with a path ("git commit <path>"), GIT_INDEX_FILE points at the real repo's
# temporary index; inherited, it let "git add -f services/api/.env" here stage a path in the
# real index, and the hook's "git reset --hard" then deleted the real services/api/.env
# (Oct 30). So every git and check run here gets an environment without GIT_* variables.
CLEAN_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


class CheckSecretsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        (self.repo / ".gitignore").write_text(".env\n")
        env = self.repo / "services" / "api" / ".env"
        env.parent.mkdir(parents=True)
        env.write_text(f'{ASSIGN}"{FAKE_KEY}"\nMETA_API_BASE=https://api.meta.ai/v1\n')
        self.stage(".gitignore", ".env\n")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True, env=CLEAN_ENV)

    def stage(self, rel: str, content: str | bytes) -> None:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content)
        self.git("add", "-f", rel)

    def run_check(self) -> subprocess.CompletedProcess[str]:
        r = subprocess.run(
            [sys.executable, str(CHECK)], cwd=self.repo, capture_output=True, text=True, env=CLEAN_ENV
        )
        self.assertNotIn(FAKE_KEY, r.stdout + r.stderr)
        self.assertNotIn(FAKE_KEY[4:12], r.stdout + r.stderr)
        return r

    def test_clean_staged_content_passes(self) -> None:
        self.stage("app/main.py", 'key = os.environ.get("MODEL_API_KEY")\n')
        self.assertEqual(self.run_check().returncode, 0)

    def test_the_key_value_anywhere_is_refused_without_printing_it(self) -> None:
        self.stage("notes.md", f"debug: the header was Bearer {FAKE_KEY}\n")
        r = self.run_check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("notes.md", r.stderr)

    def test_the_key_inside_a_binary_file_is_refused(self) -> None:
        self.stage("fixtures/blob.bin", b"\x00\x01" + FAKE_KEY.encode() + b"\xff")
        r = self.run_check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("fixtures/blob.bin", r.stderr)

    def test_an_assignment_outside_env_example_is_refused(self) -> None:
        self.stage("scripts/run.sh", f"{ASSIGN}abc make dev\n")
        r = self.run_check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("scripts/run.sh", r.stderr)

    def test_an_assignment_with_spaces_is_refused(self) -> None:
        self.stage("config.py", "MODEL_API_KEY" + ' = "x"\n')
        self.assertEqual(self.run_check().returncode, 1)

    def test_an_empty_assignment_in_env_example_passes(self) -> None:
        self.stage(".env.example", f"{ASSIGN}\nMOCK_META=0\n")
        self.assertEqual(self.run_check().returncode, 0)

    def test_the_key_in_env_example_is_still_refused(self) -> None:
        self.stage(".env.example", f"{ASSIGN}{FAKE_KEY}\n")
        self.assertEqual(self.run_check().returncode, 1)

    def test_a_force_added_env_file_is_refused(self) -> None:
        self.git("add", "-f", "services/api/.env")
        r = self.run_check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("services/api/.env", r.stderr)

    def test_certificate_and_key_files_are_refused(self) -> None:
        for rel in ("apps/web/.certs/phone.pem", "apps/web/.certs/phone-key.pem", "x/server.key", "x/id.p12"):
            with self.subTest(rel=rel):
                self.stage(rel, "not a real key\n")
                r = self.run_check()
                self.assertEqual(r.returncode, 1)
                self.assertIn(rel, r.stderr)
                self.git("rm", "-q", "--cached", rel)

    def test_a_private_key_block_in_any_file_is_refused(self) -> None:
        block = "-----BEGIN " + "RSA PRIVATE" + " KEY-----\nMIIfake\n-----END RSA PRIVATE KEY-----\n"
        self.stage("notes/setup.md", "copied by mistake:\n" + block)
        r = self.run_check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("holds a private key", r.stderr)

    def test_only_staged_content_counts(self) -> None:
        self.stage("notes.md", "clean\n")
        (self.repo / "notes.md").write_text(f"unstaged {FAKE_KEY}\n")
        self.assertEqual(self.run_check().returncode, 0)

    def test_a_deleted_file_is_not_read(self) -> None:
        self.stage("old.md", "clean\n")
        self.git("commit", "-q", "-m", "x")
        self.git("rm", "-q", "old.md")
        self.assertEqual(self.run_check().returncode, 0)

    def test_without_an_env_file_the_assignment_check_still_runs(self) -> None:
        (self.repo / "services" / "api" / ".env").unlink()
        self.stage("a.sh", f"{ASSIGN}abc\n")
        self.assertEqual(self.run_check().returncode, 1)


if __name__ == "__main__":
    unittest.main()

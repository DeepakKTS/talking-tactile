"""Tests for scripts/hooks/pre-commit. Run: python3 -m unittest -v scripts/test_pre_commit.py

Each test builds a throwaway git repo with the real hook and stand-in checks: the secret
check passes, the unittest and node files hold one passing test, and "make check" fails when
the working copy of app.txt says "fail". The repo has an ignored services/api/.env and
apps/web/.certs/, an untracked file, an unstaged edit and an unstaged deletion; after every
commit, failing or passing, all of them must be as they were. On Oct 30 the hook's
"git reset --hard" deleted the real services/api/.env.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "hooks" / "pre-commit"
# The same rule as test_check_secrets.py: the throwaway repo never sees the real one's git
# variables, such as GIT_INDEX_FILE under the real hook.
CLEAN_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
PASSING_UNITTEST = (
    "import unittest\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        pass\n"
)
NODE_TEST = 'import test from "node:test";\ntest("ok", () => {});\n'
CHECK = "import sys\nfrom pathlib import Path\nsys.exit(Path('app.txt').read_text() == 'fail')\n"
# Kept apart from the real key name and format: none of this is a secret.
IGNORED = {
    "services/api/.env": "FAKE_SETTING=not-a-secret\n",
    "apps/web/.certs/phone.pem": "fake certificate\n",
    "apps/web/.certs/phone-key.pem": "fake key\n",
}


class PreCommitHookTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.git("config", "core.hooksPath", "scripts/hooks")
        files = {
            ".gitignore": ".env\n.certs/\n",
            "scripts/check_secrets.py": "",
            "scripts/test_tracker.py": PASSING_UNITTEST,
            "scripts/test_check_secrets.py": PASSING_UNITTEST,
            "scripts/test_pre_commit.py": PASSING_UNITTEST,
            "scripts/test_preflight.py": PASSING_UNITTEST,
            "scripts/test_results.py": PASSING_UNITTEST,
            "spikes/tracking/test/ok.test.mjs": NODE_TEST,
            "Makefile": "check:\n\tpython3 check.py\n",
            "check.py": CHECK,
            "app.txt": "pass",
            "gone.txt": "tracked, then deleted without staging\n",
        }
        for rel, text in files.items():
            self.write(rel, text)
        hook = self.repo / "scripts" / "hooks" / "pre-commit"
        hook.parent.mkdir(parents=True)
        shutil.copy(HOOK, hook)
        hook.chmod(0o755)
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", "start")
        for rel, text in IGNORED.items():
            self.write(rel, text)
        self.write("notes.txt", "untracked\n")
        (self.repo / "gone.txt").unlink()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, rel: str, text: str) -> None:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def git(self, *args: str) -> str:
        r = subprocess.run(
            ["git", *args], cwd=self.repo, check=True, capture_output=True, text=True, env=CLEAN_ENV
        )
        return r.stdout

    def commit(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "commit", "-m", "change"],
            check=False,
            cwd=self.repo,
            capture_output=True,
            text=True,
            env=CLEAN_ENV,
        )

    def stage_then_edit(self, staged: str) -> None:
        self.write("app.txt", staged)
        self.git("add", "app.txt")
        self.write("app.txt", "unstaged")

    def assert_untouched(self) -> None:
        for rel, text in IGNORED.items():
            self.assertEqual((self.repo / rel).read_text(), text, rel)
        self.assertEqual(self.git("check-ignore", *IGNORED).split(), list(IGNORED))
        self.assertEqual((self.repo / "notes.txt").read_text(), "untracked\n")
        self.assertEqual((self.repo / "app.txt").read_text(), "unstaged")
        self.assertFalse((self.repo / "gone.txt").exists())
        self.assertEqual(list(self.repo.joinpath(".git").glob("pre-commit-aside.*")), [])

    def test_failing_commit_tests_the_staged_content_and_keeps_every_file(self) -> None:
        self.stage_then_edit("fail")  # the working copy passes; only the staged one fails
        r = self.commit()
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.git("rev-list", "--count", "HEAD").strip(), "1")
        self.assertEqual(self.git("show", ":app.txt"), "fail")  # still staged
        self.assert_untouched()

    def test_passing_commit_keeps_every_file(self) -> None:
        self.stage_then_edit("pass again")
        r = self.commit()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.git("show", "HEAD:app.txt"), "pass again")
        self.assert_untouched()

    def test_a_test_that_stages_a_path_blocks_the_commit(self) -> None:
        self.write("Makefile", "check:\n\tgit add -f services/api/.env\n")
        self.git("add", "Makefile")
        r = self.commit()
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("the tests changed the staged content", r.stderr)
        self.assertEqual(self.git("rev-list", "--count", "HEAD").strip(), "1")
        self.assertTrue((self.repo / "services/api/.env").exists())


if __name__ == "__main__":
    unittest.main()

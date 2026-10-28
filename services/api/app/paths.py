"""Repo paths shared by the backend. The repo root holds config/, docs/ and fixtures/."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO_ROOT / "config"
TACTILE_RULES_YAML = CONFIG_DIR / "tactile_rules.yaml"
EXPLORE_YAML = CONFIG_DIR / "explore.yaml"
REGIONS_SCHEMA = REPO_ROOT / "docs" / "regions.schema.json"
FIXTURES_DIR = REPO_ROOT / "fixtures"
GOLDEN_REGIONS = FIXTURES_DIR / "regions" / "golden.json"
REGION_CASES = FIXTURES_DIR / "regions" / "cases.json"
RECORDED_DIR = FIXTURES_DIR / "recorded"  # real Meta responses, auth stripped
LEDGER = REPO_ROOT / "eval" / "live" / "ledger.jsonl"  # one line per live Meta call
ENV_FILE = REPO_ROOT / "services" / "api" / ".env"  # git-ignored; holds the key
DATA_DIR = REPO_ROOT / "data"  # git-ignored
FIGURES_DIR = DATA_DIR / "figures"
JOBS_DB = DATA_DIR / "jobs.sqlite"

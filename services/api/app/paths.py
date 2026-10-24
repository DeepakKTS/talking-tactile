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
DATA_DIR = REPO_ROOT / "data"  # git-ignored
FIGURES_DIR = DATA_DIR / "figures"
JOBS_DB = DATA_DIR / "jobs.sqlite"

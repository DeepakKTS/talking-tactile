"""Prompt and request templates for the Meta stages, one versioned JSON file each. The
stage cache keys on the file's hash, so editing a prompt re-runs its stage. A new version
gets a new file; the stage names the file it uses."""

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

PROMPTS_DIR = Path(__file__).resolve().parent


class Prompt(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    template: dict[str, Any]
    digest: str  # sha256 of the file bytes


def load_prompt(name: str, root: Path = PROMPTS_DIR) -> Prompt:
    raw = (root / name).read_bytes()
    template = json.loads(raw)
    if not isinstance(template, dict):
        raise ValueError(f"prompt {name} must be a JSON object")
    return Prompt(name=name, template=template, digest=hashlib.sha256(raw).hexdigest())


def schema_digest(schema: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()

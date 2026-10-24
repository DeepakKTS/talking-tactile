"""The per-stage cache under data/figures/<figure_id>/<stage>/<key>/.

A stage key is a hash of the previous stage's key and everything else the stage reads, so
one key names one output and a hit needs no look at the inputs. An output is written whole
under a temporary name and then renamed, so a crash never leaves half of one behind.

Mock responses are cached under the mock's own keys. Delete data/figures after the
recorded fixtures change."""

import hashlib
import json
import os
import shutil
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from functools import cache
from pathlib import Path

import numpy as np
from PIL import Image

from app.models.mask import BoolImage

_APP_DIR = Path(__file__).resolve().parents[1]
_KEY_DIR_CHARS = 16


def stage_key(stage: str, previous: str, **inputs: object) -> str:
    blob = json.dumps({"stage": stage, "previous": previous, **inputs}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


@cache
def code_digest() -> str:
    """A hash of the backend source. Stages that cost nothing key on it, so a code change
    re-runs them; the Meta stages do not, so a code change never pays for a call again."""
    h = hashlib.sha256()
    for path in sorted(_APP_DIR.rglob("*.py")):
        h.update(path.relative_to(_APP_DIR).as_posix().encode() + b"\0")
        h.update(path.read_bytes() + b"\0")
    return h.hexdigest()


class FigureCache:
    def __init__(self, root: Path, figure_id: str) -> None:
        self.root = root / figure_id

    def dir(self, stage: str, key: str) -> Path:
        return self.root / stage / key[:_KEY_DIR_CHARS]

    def has(self, stage: str, key: str) -> bool:
        return self.dir(stage, key).is_dir()

    def drop(self, stage: str, key: str) -> None:
        shutil.rmtree(self.dir(stage, key), ignore_errors=True)

    @contextmanager
    def write(self, stage: str, key: str) -> Iterator[Path]:
        """Yields an empty directory to write the output into. It becomes the cache entry
        when the block ends without an error. When another run wrote the same entry first,
        that one is kept."""
        final = self.dir(stage, key)
        tmp = final.parent / f".tmp-{uuid.uuid4().hex}"
        tmp.mkdir(parents=True)
        try:
            yield tmp
            try:
                os.rename(tmp, final)
            except OSError:
                if not final.is_dir():
                    raise
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def save_mask(path: Path, data: BoolImage) -> None:
    Image.fromarray(data).save(path)


def load_mask(path: Path) -> BoolImage:
    with Image.open(path) as img:
        pixels: BoolImage = np.asarray(img.convert("1"), dtype=bool)
    return pixels

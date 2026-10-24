"""The per-stage cache under data/figures/<figure_id>/<stage>/<key>/.

A stage key is a hash of the previous stage's key, the digests of the upstream outputs the
stage reads, and everything else it depends on: prompts, response schemas, the client's
cache tag (which covers the mock fixtures), config and code. One key names one output.

Each entry holds a digest of its own files, written last. A hit is an entry whose files
still match it; anything else is deleted and made again. Entries are written under a
temporary name and renamed, so a crash never leaves half of one behind."""

import hashlib
import json
import logging
import os
import re
import shutil
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from functools import cache
from pathlib import Path

import numpy as np
from PIL import Image

from app.models.mask import BoolImage

log = logging.getLogger(__name__)

_APP_DIR = Path(__file__).resolve().parents[1]
_KEY_DIR_CHARS = 16
_DIGEST_FILE = ".digest"
_FIGURE_ID = re.compile(r"[0-9a-f]{64}")


def is_figure_id(value: str) -> bool:
    """A figure id is a lowercase hex sha256. Checked before an id touches any path."""
    return _FIGURE_ID.fullmatch(value) is not None


def entry_digest(entry: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(p for p in entry.rglob("*") if p.is_file() and p.name != _DIGEST_FILE):
        h.update(path.relative_to(entry).as_posix().encode() + b"\0")
        h.update(path.read_bytes() + b"\0")
    return h.hexdigest()


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
        if not is_figure_id(figure_id):
            raise ValueError("a figure id is 64 lowercase hex characters")
        self.root = root / figure_id

    def dir(self, stage: str, key: str) -> Path:
        return self.root / stage / key[:_KEY_DIR_CHARS]

    def digest(self, stage: str, key: str) -> str | None:
        """The entry's digest when it exists and its files still match it. A damaged entry
        is deleted."""
        entry = self.dir(stage, key)
        if not entry.is_dir():
            return None
        try:
            stored = (entry / _DIGEST_FILE).read_text("utf-8").strip()
        except OSError:
            stored = ""
        if stored != entry_digest(entry):
            log.warning("cache entry %s is damaged; making it again", entry)
            shutil.rmtree(entry, ignore_errors=True)
            return None
        return stored

    @contextmanager
    def write(self, stage: str, key: str) -> Iterator[Path]:
        """Yields an empty directory to write the output into. It becomes the cache entry,
        digest included, when the block ends without an error. When another run wrote the
        same entry first, that one is kept."""
        final = self.dir(stage, key)
        tmp = final.parent / f".tmp-{uuid.uuid4().hex}"
        tmp.mkdir(parents=True)
        try:
            yield tmp
            (tmp / _DIGEST_FILE).write_text(entry_digest(tmp), "utf-8")
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

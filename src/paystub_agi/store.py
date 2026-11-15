"""Optional store for the costly OCR read (DL-038, DL-039).

Only the read is saved: the model is asked afresh every time, because its answers
vary between calls. Saved reads contain document contents: the caller's folder must
be git-ignored, and nothing here logs. Keys are content fingerprints, so a renamed
stub is still found.
"""

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from paystub_agi.config import ReadingConfig
from paystub_agi.errors import StoreError

_KEY = re.compile(r"[0-9a-f]{64}")


class StoredRead(BaseModel):
    """The part of an OCR read that later steps need; images are rebuilt instead."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(repr=False)
    reader: str


class EvidenceStore(Protocol):
    def get(self, key: str) -> str | None: ...

    def put(self, key: str, value: str) -> None: ...


class FileEvidenceStore:
    """One JSON file per key in a folder chosen by the caller."""

    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def _path(self, key: str) -> Path:
        # Only fingerprints become file names, so a key can't point outside the folder.
        if not _KEY.fullmatch(key):
            raise StoreError("a store key must be 64 lower-case hex characters")
        return self._folder / f"{key}.json"

    def get(self, key: str) -> str | None:
        path = self._path(key)
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise StoreError(f"cannot read saved item {path}") from exc

    def put(self, key: str, value: str) -> None:
        path = self._path(key)
        temporary = path.with_suffix(".tmp")
        try:
            self._folder.mkdir(parents=True, exist_ok=True)
            temporary.write_text(value, encoding="utf-8")
            # Swapped in whole, so a crash never leaves a half-written item.
            os.replace(temporary, path)
        except OSError as exc:
            raise StoreError(f"cannot save item {path}") from exc


def save_read(store: EvidenceStore, key: str, read: StoredRead) -> None:
    store.put(key, read.model_dump_json())


def load_read(store: EvidenceStore, key: str) -> StoredRead | None:
    text = store.get(key)
    if text is None:
        return None
    try:
        return StoredRead.model_validate_json(text)
    except ValidationError:
        pass
    # Raised outside the handler so the saved document values aren't chained.
    raise StoreError(f"saved item {key} is damaged; delete it to read the stub again")


def read_key(contents: bytes, config: ReadingConfig) -> str:
    """Same file contents, readers and saved format give the same key."""
    digest = hashlib.sha256()
    for part in (
        contents,
        json.dumps(config.strategy).encode(),
        json.dumps(StoredRead.model_json_schema(), sort_keys=True).encode(),
    ):
        # Length first, so ("ab", "c") and ("a", "bc") can't give the same key.
        digest.update(len(part).to_bytes(8, "big"))
        digest.update(part)
    return digest.hexdigest()

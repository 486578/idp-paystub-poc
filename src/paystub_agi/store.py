"""Optional evidence store: saves the costly OCR read and model answer (DL-038).

Saved items contain document contents: the caller's folder must be git-ignored, and
nothing here logs. Keys are content fingerprints, so a renamed stub is still found.
"""

import hashlib
import json
import os
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from paystub_agi.config import ReadingConfig
from paystub_agi.errors import StoreError
from paystub_agi.reading import PageImage

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


def save(store: EvidenceStore, key: str, value: BaseModel) -> None:
    store.put(key, value.model_dump_json())


def load[M: BaseModel](store: EvidenceStore, key: str, model: type[M]) -> M | None:
    text = store.get(key)
    if text is None:
        return None
    try:
        return model.model_validate_json(text)
    except ValidationError:
        pass
    # Raised outside the handler so the saved document values aren't chained.
    raise StoreError(f"saved item {key} is damaged; delete it to read the stub again")


def _digest(*parts: bytes) -> str:
    digest = hashlib.sha256()
    for part in parts:
        # Length first, so ("ab", "c") and ("a", "bc") can't give the same key.
        digest.update(len(part).to_bytes(8, "big"))
        digest.update(part)
    return digest.hexdigest()


def read_key(contents: bytes, config: ReadingConfig) -> str:
    """Same file contents, readers and saved format give the same key."""
    return _digest(
        b"read",
        contents,
        json.dumps(config.strategy).encode(),
        json.dumps(StoredRead.model_json_schema(), sort_keys=True).encode(),
    )


def evidence_key(fingerprint: str, text: str, images: Sequence[PageImage]) -> str:
    """`fingerprint` comes from `EvidenceExtractor.fingerprint`."""
    image_parts = [part for i in images for part in (i.media_type.encode(), i.data)]
    return _digest(b"evidence", fingerprint.encode(), text.encode(), *image_parts)

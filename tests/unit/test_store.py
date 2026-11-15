import json
from pathlib import Path

import pytest

from paystub_agi.config import ReadingConfig
from paystub_agi.errors import StoreError
from paystub_agi.models import PaystubEvidence
from paystub_agi.reading import PageImage
from paystub_agi.store import (
    EvidenceStore,
    FileEvidenceStore,
    StoredRead,
    evidence_key,
    load,
    read_key,
    save,
)

KEY = "a" * 64
OTHER_KEY = "b" * 64
PDF = b"%PDF-1.7 synthetic stub"
PNG = PageImage(page_number=1, media_type="image/png", data=b"png-bytes")


class MemoryStore:
    """A dict-backed `EvidenceStore` for tests."""

    def __init__(self, items: dict[str, str] | None = None) -> None:
        self.items = dict(items or {})

    def get(self, key: str) -> str | None:
        return self.items.get(key)

    def put(self, key: str, value: str) -> None:
        self.items[key] = value


def _memory(items: dict[str, str] | None = None) -> EvidenceStore:
    return MemoryStore(items)


def _evidence() -> PaystubEvidence:
    return PaystubEvidence.model_validate(
        {
            "gross": "1760.00",
            "net": "1224.70",
            "pay_frequency": "Biweekly",
            "period_start": "2026-07-01",
            "period_end": "2026-07-14",
            "pay_date": None,
            "federal_taxable_wages": None,
            "annual_amount": None,
            "earnings": [
                {"label": "Regular", "amount": "1760.00", "in_brackets": False}
            ],
            "taxes": [],
            "deductions": [],
            "footnotes": [],
        }
    )


# --- file store ----------------------------------------------------------------------


def test_store_file_missing_key_returns_none(tmp_path: Path) -> None:
    assert FileEvidenceStore(tmp_path).get(KEY) is None


def test_store_file_put_then_get_returns_value(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)

    store.put(KEY, '{"x": 1}')

    assert store.get(KEY) == '{"x": 1}'
    assert store.get(OTHER_KEY) is None


def test_store_file_put_overwrites(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)

    store.put(KEY, "first")
    store.put(KEY, "second")

    assert store.get(KEY) == "second"


def test_store_file_creates_folder(tmp_path: Path) -> None:
    folder = tmp_path / "evidence" / "nested"

    FileEvidenceStore(folder).put(KEY, "value")

    assert (folder / f"{KEY}.json").read_text(encoding="utf-8") == "value"


def test_store_file_leaves_no_temporary_file(tmp_path: Path) -> None:
    FileEvidenceStore(tmp_path).put(KEY, "value")

    assert [p.name for p in tmp_path.iterdir()] == [f"{KEY}.json"]


@pytest.mark.parametrize(
    "bad",
    ["", "../" + "a" * 61, "A" * 64, "a" * 63, "a" * 65, "g" * 64, "a" * 63 + "/"],
)
def test_store_file_rejects_unsafe_key(tmp_path: Path, bad: str) -> None:
    store = FileEvidenceStore(tmp_path)

    with pytest.raises(StoreError, match="key"):
        store.get(bad)
    with pytest.raises(StoreError, match="key"):
        store.put(bad, "value")
    assert list(tmp_path.iterdir()) == []


def test_store_file_unreadable_item_raises_store_error(tmp_path: Path) -> None:
    (tmp_path / f"{KEY}.json").mkdir()

    with pytest.raises(StoreError, match=KEY):
        FileEvidenceStore(tmp_path).get(KEY)


def test_store_file_write_failure_raises_store_error(tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("x", encoding="utf-8")

    with pytest.raises(StoreError, match="save"):
        FileEvidenceStore(blocker).put(KEY, "value")


# --- typed load and save -------------------------------------------------------------


def test_store_model_round_trip_keeps_exact_amounts() -> None:
    store = _memory()

    save(store, KEY, _evidence())
    loaded = load(store, KEY, PaystubEvidence)

    assert loaded == _evidence()
    assert loaded is not None
    assert str(loaded.net) == "1224.70"


def test_store_read_round_trip() -> None:
    store = _memory()
    read = StoredRead(text="--- Page 1 ---\nGross Pay", reader="pdfplumber")

    save(store, KEY, read)

    assert load(store, KEY, StoredRead) == read


def test_store_load_missing_returns_none() -> None:
    assert load(_memory(), KEY, PaystubEvidence) is None


def test_store_load_damaged_item_raises_without_document_values() -> None:
    store = _memory({KEY: json.dumps({"gross": "SECRET-123-45-6789"})})

    with pytest.raises(StoreError) as caught:
        load(store, KEY, PaystubEvidence)

    assert KEY in str(caught.value)
    assert "SECRET" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_store_load_invalid_json_raises() -> None:
    with pytest.raises(StoreError, match="damaged"):
        load(_memory({KEY: "{not json"}), KEY, StoredRead)


# --- keys ----------------------------------------------------------------------------


def test_store_read_key_same_contents_same_key() -> None:
    assert read_key(PDF, ReadingConfig()) == read_key(bytes(PDF), ReadingConfig())


def test_store_read_key_changes_with_contents() -> None:
    assert read_key(PDF, ReadingConfig()) != read_key(PDF + b" ", ReadingConfig())


def test_store_read_key_changes_with_strategy() -> None:
    textract_only = ReadingConfig(strategy=("textract",))

    assert read_key(PDF, ReadingConfig()) != read_key(PDF, textract_only)


def test_store_read_key_ignores_image_settings() -> None:
    images = ReadingConfig(max_images=1, image_dpi=72, grayscale=False)

    assert read_key(PDF, ReadingConfig()) == read_key(PDF, images)


def test_store_evidence_key_changes_with_each_input() -> None:
    base = evidence_key("fingerprint", "text", ())

    assert base == evidence_key("fingerprint", "text", ())
    assert base != evidence_key("other", "text", ())
    assert base != evidence_key("fingerprint", "other", ())
    assert base != evidence_key("fingerprint", "text", (PNG,))
    other_png = PageImage(page_number=1, media_type="image/png", data=b"other")
    assert evidence_key("f", "t", (PNG,)) != evidence_key("f", "t", (other_png,))


def test_store_evidence_key_parts_cannot_run_together() -> None:
    assert evidence_key("ab", "c", ()) != evidence_key("a", "bc", ())


def test_store_keys_are_safe_file_names(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)

    for key in (read_key(PDF, ReadingConfig()), evidence_key("f", "t", (PNG,))):
        store.put(key, "value")
        assert store.get(key) == "value"


def test_store_read_and_evidence_keys_never_collide() -> None:
    assert read_key(b"x", ReadingConfig(strategy=("t",))) != evidence_key("x", "t", ())

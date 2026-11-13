"""Read the local sample stubs with the free digital reader only (no AWS, no cost).

Skipped when the PDFs aren't in docs/paystubs/ (they stay out of git).
"""

from pathlib import Path

import pytest

from paystub_agi.config import ReadingConfig
from paystub_agi.reading import IdpOcrStubReader

STUBS = Path(__file__).parents[2] / "docs" / "paystubs"


def _read(name: str, *, images: bool = False) -> tuple[str, str, int]:
    path = STUBS / name
    if not path.is_file():
        pytest.skip(f"{name} not in {STUBS}")
    stub = IdpOcrStubReader(ReadingConfig(strategy="digital_only")).read(
        str(path), images=images
    )
    return stub.reader, stub.text, len(stub.images)


def test_local_stub_0006_reads_digitally_with_its_amounts() -> None:
    reader, text, _ = _read("stub_0006.pdf")

    assert reader == "pdfplumber"
    assert "[Table 1]" in text
    for amount in ("1,760.00", "1,224.70", "85.00", "12.00", "70.40", "88.00"):
        assert amount in text


def test_local_stub_0010_reads_digitally_with_its_amounts() -> None:
    reader, text, _ = _read("stub_0010.pdf")

    assert reader == "pdfplumber"
    for amount in ("1,836.22", "1,173.95", "106.95", "55.53", "34.65", "11.91"):
        assert amount in text


def test_local_stub_renders_one_page_image() -> None:
    _, _, images = _read("stub_0006.pdf", images=True)

    assert images == 1

"""Real Textract read of a local sample stub. Opt-in: costs money and needs AWS.

Run with: uv run pytest -m integration tests/integration/test_reading_textract.py
Needs AWS credentials from the usual chain (e.g. AWS_PROFILE) and these variables:
  PAYSTUB_TEST_AWS_REGION       region for Textract
  PAYSTUB_TEST_STAGING_BUCKET   optional; only needed for multi-page PDFs
"""

import os
from pathlib import Path

import pytest
from idp_ocr import TextractReader

from paystub_agi.config import ReadingConfig
from paystub_agi.reading import IdpOcrStubReader

pytestmark = pytest.mark.integration

STUB = Path(__file__).parents[2] / "docs" / "paystubs" / "stub_0006.pdf"


def test_textract_reads_stub_0006_with_tables() -> None:
    region = os.environ.get("PAYSTUB_TEST_AWS_REGION")
    if not region:
        pytest.skip("set PAYSTUB_TEST_AWS_REGION to run")
    if not STUB.is_file():
        pytest.skip(f"{STUB.name} not in {STUB.parent}")
    textract = TextractReader(
        region=region, staging_bucket=os.environ.get("PAYSTUB_TEST_STAGING_BUCKET")
    )
    reader = IdpOcrStubReader(ReadingConfig(strategy="ocr_only"), ocr=[textract])

    stub = reader.read(str(STUB), images=False)

    assert stub.reader == "textract"
    assert "[Table 1]" in stub.text
    for amount in ("1,760.00", "1,224.70", "85.00"):
        assert amount in stub.text

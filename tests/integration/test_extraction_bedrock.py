"""Real model extraction of a local sample stub. Opt-in: costs money and needs AWS.

Run with: uv run pytest -m integration tests/integration/test_extraction_bedrock.py
Needs AWS credentials from the usual chain (e.g. AWS_PROFILE) and these variables:
  PAYSTUB_TEST_AWS_REGION   region for Bedrock
  PAYSTUB_TEST_MODEL_ID     a Bedrock Converse model or inference profile ID
The stub is read with the free local reader; only the model call is paid.
"""

import os
from decimal import Decimal
from pathlib import Path

import boto3
import pytest
from idp_genai.providers.bedrock import bedrock_capabilities
from idp_genai.service import GenAIService

from paystub_agi.config import ExtractionConfig, ReadingConfig
from paystub_agi.extraction import EvidenceExtractor
from paystub_agi.reading import IdpOcrStubReader

pytestmark = pytest.mark.integration

STUB = Path(__file__).parents[2] / "docs" / "paystubs" / "stub_0006.pdf"


def test_bedrock_extracts_stub_0006_evidence() -> None:
    region = os.environ.get("PAYSTUB_TEST_AWS_REGION")
    model = os.environ.get("PAYSTUB_TEST_MODEL_ID")
    if not region or not model:
        pytest.skip("set PAYSTUB_TEST_AWS_REGION and PAYSTUB_TEST_MODEL_ID to run")
    if not STUB.is_file():
        pytest.skip(f"{STUB.name} not in {STUB.parent}")
    stub = IdpOcrStubReader(ReadingConfig(strategy=("pdfplumber",))).read(
        str(STUB), images=False
    )
    service = GenAIService.create_bedrock_service(
        client=boto3.client("bedrock-runtime", region_name=region),
        capabilities=bedrock_capabilities(),
    )

    evidence = EvidenceExtractor(
        service, model=model, config=ExtractionConfig()
    ).extract(stub)

    assert evidence.gross == Decimal("1760.00")
    assert evidence.net == Decimal("1224.70")
    assert Decimal("85.00") in {abs(d.amount) for d in evidence.deductions if d.amount}

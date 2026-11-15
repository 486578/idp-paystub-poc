"""stub_0006 end to end: the real free reader on the local PDF + a canned model answer.

No network and no model call. Skipped when the local sample PDF is absent.
The canned answer copies the printed labels and amounts only (no names).
"""

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from idp_core.models import AttemptContext, CallMetrics, ModelCapabilities
from idp_genai.responses import ParsedResponse
from idp_genai.service import Attachment

from paystub_agi import AnalyzerConfig, FileEvidenceStore, PaystubAnalyzer, StubStatus
from paystub_agi.config import ReadingConfig

STUB = Path(__file__).parents[2] / "docs" / "paystubs" / "stub_0006.pdf"


def _line(label: str, amount: float) -> dict[str, Any]:
    return {"label": label, "amount": amount, "in_brackets": False}


def _row(label: str, amount: float, heading: str) -> dict[str, Any]:
    return {
        "label": label,
        "amount": amount,
        "section_heading": heading,
        "codes": [],
        "markers": [],
        "in_employer_section": heading == "Benefits",
        "in_brackets": False,
    }


ANSWER = {
    "gross": 1760.00,
    "net": 1224.70,
    "pay_frequency": None,
    "period_start": "2026-07-01",
    "period_end": "2026-07-14",
    "pay_date": "2026-07-17",
    "federal_taxable_wages": None,
    "annual_amount": None,
    "earnings": [_line("Regular", 1760.00)],
    "taxes": [
        _line("FIT", 158.40),
        _line("FICA SS", 109.12),
        _line("FICA Me", 25.52),
        _line("PA SIT", 54.03),
        _line("EIT", 17.60),
        _line("LST", 2.00),
        _line("SUTA", 1.23),
    ],
    "deductions": [
        _row("Medical", 85.00, "Deductions"),
        _row("Dental", 12.00, "Deductions"),
        _row("401k", 70.40, "Deductions"),
        _row("Pension ER", 88.00, "Benefits"),
    ],
    "footnotes": [],
}


class CannedGenAI:
    capabilities = ModelCapabilities(features=("text",))

    def __init__(self) -> None:
        self.texts: list[str | None] = []

    def extract(
        self,
        *,
        model: str,
        task: str,
        document_text: str | None,
        attachments: tuple[Attachment, ...],
        schema: type,
        max_output_tokens: int,
        temperature: float | None,
    ) -> ParsedResponse:
        self.texts.append(document_text)
        context = AttemptContext(
            run_id="run",
            document_id="doc",
            operation_id="extract",
            attempt_id="attempt",
            attempt_number=1,
        )
        return ParsedResponse(
            "parsed", ANSWER, CallMetrics(context=context, duration_ms=None)
        )


@pytest.fixture()
def stub() -> Path:
    if not STUB.is_file():
        pytest.skip(f"{STUB.name} not in {STUB.parent}")
    return STUB


def _analyzer(genai: CannedGenAI, store: FileEvidenceStore | None) -> PaystubAnalyzer:
    config = AnalyzerConfig(reading=ReadingConfig(strategy=("pdfplumber",)))
    return PaystubAnalyzer.create(config, genai=genai, model="canned", store=store)


def test_analyzer_stub_0006_is_ok_with_the_key_agi(stub: Path) -> None:
    genai = CannedGenAI()

    result = _analyzer(genai, None).analyze(str(stub))

    assert result.status is StubStatus.OK
    assert result.agi.agi == Decimal("45760.00")
    assert result.flags == ()
    assert result.reader == "pdfplumber"
    assert genai.texts[0] is not None and "| Pension ER | 88.00 |" in genai.texts[0]


def test_analyzer_stub_0006_second_run_uses_the_saved_read(
    stub: Path, tmp_path: Path
) -> None:
    genai = CannedGenAI()
    analyzer = _analyzer(genai, FileEvidenceStore(tmp_path))

    first = analyzer.analyze(str(stub))
    second = analyzer.analyze(str(stub))

    assert (first.read_from_store, second.read_from_store) == (False, True)
    assert second.model_copy(update={"read_from_store": False}) == first
    assert genai.texts[0] == genai.texts[1]
    assert len(genai.texts) == 2

import json
from decimal import Decimal
from typing import Any

import pytest
from idp_core.exceptions import UnsupportedInputError
from idp_core.models import (
    AttemptContext,
    CallMetrics,
    ModelCapabilities,
    ModelRequest,
    ModelResult,
    TokenCount,
)
from idp_genai.responses import ParsedResponse
from idp_genai.service import Attachment, GenAIService

from paystub_agi.config import ExtractionConfig
from paystub_agi.errors import ConfigError, ExtractionError
from paystub_agi.extraction import EvidenceExtractor
from paystub_agi.models import PaystubEvidence
from paystub_agi.reading import PageImage, ReadStub

MODEL = "test-model"
OCR_TEXT = "--- Page 1 ---\nGross Pay 1760.00\nNet Pay 1224.70"
TEXT_ONLY = ModelCapabilities(features=("text",))
WITH_IMAGES = ModelCapabilities(
    features=("text", "images"), image_media_types=("image/png", "image/jpeg")
)
PNG = PageImage(page_number=1, media_type="image/png", data=b"png-bytes")
JPEG = PageImage(page_number=2, media_type="image/jpeg", data=b"jpeg-bytes")


def _context() -> AttemptContext:
    return AttemptContext(
        run_id="run-1",
        document_id="doc-1",
        operation_id="extract",
        attempt_id="attempt-1",
        attempt_number=1,
    )


def _metrics() -> CallMetrics:
    return CallMetrics(context=_context(), duration_ms=None)


def _evidence_data(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "gross": 1760.0,
        "net": 1224.7,
        "pay_frequency": "Biweekly",
        "period_start": "2026-07-01",
        "period_end": "2026-07-14",
        "pay_date": "2026-07-17",
        "federal_taxable_wages": None,
        "annual_amount": None,
        "earnings": [{"label": "Regular", "amount": 1760.0, "in_brackets": False}],
        "taxes": [{"label": "Social Security", "amount": 109.12, "in_brackets": False}],
        "deductions": [
            {
                "label": "Medical",
                "amount": 85.0,
                "section_heading": "Deductions",
                "codes": [],
                "markers": [],
                "in_employer_section": False,
                "in_brackets": False,
            }
        ],
        "footnotes": [],
    }
    values.update(overrides)
    return values


def _parsed(data: object) -> ParsedResponse:
    return ParsedResponse("parsed", data, _metrics())


def _stub(*images: PageImage) -> ReadStub:
    return ReadStub(text=OCR_TEXT, reader="pdfplumber", pages=(1,), images=images)


class FakeGenAI:
    """Stands in for `idp_genai.GenAIService`; records each call."""

    def __init__(
        self,
        response: ParsedResponse | Exception | None = None,
        capabilities: ModelCapabilities = TEXT_ONLY,
    ) -> None:
        self._response = response if response is not None else _parsed(_evidence_data())
        self._capabilities = capabilities
        self.calls: list[dict[str, Any]] = []

    @property
    def capabilities(self) -> ModelCapabilities:
        return self._capabilities

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
        self.calls.append(
            {
                "model": model,
                "task": task,
                "document_text": document_text,
                "attachments": attachments,
                "schema": schema,
                "max_output_tokens": max_output_tokens,
                "temperature": temperature,
            }
        )
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _extractor(
    genai: FakeGenAI, config: ExtractionConfig | None = None
) -> EvidenceExtractor:
    return EvidenceExtractor(genai, model=MODEL, config=config or ExtractionConfig())


# --- the request ---------------------------------------------------------------------


@pytest.mark.parametrize("blank", ["", "   "])
def test_extraction_blank_model_id_is_rejected(blank: str) -> None:
    with pytest.raises(ConfigError, match="model"):
        EvidenceExtractor(FakeGenAI(), model=blank, config=ExtractionConfig())


def test_extraction_sends_ocr_text_as_document_text() -> None:
    genai = FakeGenAI()

    _extractor(genai).extract(_stub())

    assert genai.calls[0]["document_text"] == OCR_TEXT


def test_extraction_passes_model_and_settings() -> None:
    genai = FakeGenAI()
    config = ExtractionConfig(temperature=0.3, max_output_tokens=2000)

    _extractor(genai, config).extract(_stub())

    call = genai.calls[0]
    assert call["model"] == MODEL
    assert call["temperature"] == 0.3
    assert call["max_output_tokens"] == 2000


def test_extraction_requests_the_evidence_schema() -> None:
    genai = FakeGenAI()

    _extractor(genai).extract(_stub())

    assert genai.calls[0]["schema"] is PaystubEvidence


def _field_names(schema: object) -> set[str]:
    if isinstance(schema, dict):
        names = set(schema.get("properties", {}))
        return names.union(*(_field_names(value) for value in schema.values()))
    if isinstance(schema, list):
        return set().union(*(_field_names(item) for item in schema))
    return set()


def test_extraction_schema_has_no_pretax_field() -> None:
    names = _field_names(PaystubEvidence.model_json_schema())

    assert "label" in names
    assert not [n for n in names if "pre" in n.lower() or "post" in n.lower()]


@pytest.mark.parametrize(
    "phrase",
    [
        "this period",  # DL-030 item 4
        "year-to-date",  # DL-030 items 1 and 2
        "parentheses",  # DL-025 item 1 / Q25
        "exactly as printed",
        "null",
        "plain number",
        "yyyy-mm-dd",
        "do not decide",
        "in_brackets",  # DL-037
        "total deductions",  # DL-045: no total rows
        "direct deposit",  # DL-045: no net-pay distribution rows
    ],
)
def test_extraction_prompt_contains(phrase: str) -> None:
    genai = FakeGenAI()

    _extractor(genai).extract(_stub())

    assert phrase in genai.calls[0]["task"].lower()


def test_extraction_prompt_does_not_turn_brackets_into_minus() -> None:
    genai = FakeGenAI()

    _extractor(genai).extract(_stub())

    assert "-85.00" not in genai.calls[0]["task"]


# --- the answer ----------------------------------------------------------------------


def test_extraction_valid_response_returns_evidence() -> None:
    evidence = _extractor(FakeGenAI()).extract(_stub())

    assert evidence.gross == Decimal("1760.0")
    assert evidence.deductions[0].label == "Medical"
    assert evidence.deductions[0].amount == Decimal("85.0")


def test_extraction_float_amount_becomes_exact_decimal() -> None:
    evidence = _extractor(FakeGenAI()).extract(_stub())

    assert evidence.net == Decimal("1224.7")
    assert evidence.taxes[0].amount == Decimal("109.12")


# --- images --------------------------------------------------------------------------


def test_extraction_wants_images_when_auto_and_model_takes_images() -> None:
    assert _extractor(FakeGenAI(capabilities=WITH_IMAGES)).wants_images is True


def test_extraction_does_not_want_images_for_text_only_model() -> None:
    assert _extractor(FakeGenAI(capabilities=TEXT_ONLY)).wants_images is False


def test_extraction_does_not_want_images_when_setting_is_never() -> None:
    genai = FakeGenAI(capabilities=WITH_IMAGES)
    extractor = _extractor(genai, ExtractionConfig(send_images="never"))

    assert extractor.wants_images is False


def test_extraction_sends_page_images_as_attachments() -> None:
    genai = FakeGenAI(capabilities=WITH_IMAGES)

    _extractor(genai).extract(_stub(PNG, JPEG))

    assert genai.calls[0]["attachments"] == (
        Attachment(media_type="image/png", data=b"png-bytes"),
        Attachment(media_type="image/jpeg", data=b"jpeg-bytes"),
    )


@pytest.mark.parametrize(
    ("capabilities", "send_images"),
    [(TEXT_ONLY, "auto"), (WITH_IMAGES, "never")],
)
def test_extraction_does_not_send_images_when_not_wanted(
    capabilities: ModelCapabilities, send_images: str
) -> None:
    genai = FakeGenAI(capabilities=capabilities)
    config = ExtractionConfig.model_validate({"send_images": send_images})

    _extractor(genai, config).extract(_stub(PNG))

    assert genai.calls[0]["attachments"] == ()


# --- failures ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status", ["refused", "truncated", "invalid_json", "provider_error"]
)
def test_extraction_failed_response_raises_with_status(status: str) -> None:
    response = ParsedResponse(status, None, _metrics(), detail="x")  # type: ignore[arg-type]

    with pytest.raises(ExtractionError) as caught:
        _extractor(FakeGenAI(response)).extract(_stub())

    assert caught.value.code == status


@pytest.mark.parametrize("data", [None, ["not", "an", "object"], "text"])
def test_extraction_non_object_data_raises_invalid_json(data: object) -> None:
    with pytest.raises(ExtractionError) as caught:
        _extractor(FakeGenAI(_parsed(data))).extract(_stub())

    assert caught.value.code == "invalid_json"


@pytest.mark.parametrize(
    "data",
    [
        _evidence_data(gross="N/A"),
        _evidence_data(pretax=True),
        {key: value for key, value in _evidence_data().items() if key != "net"},
        _evidence_data(period_start="07/01/2026"),
    ],
)
def test_extraction_schema_mismatch_raises_schema_invalid(
    data: dict[str, Any],
) -> None:
    with pytest.raises(ExtractionError) as caught:
        _extractor(FakeGenAI(_parsed(data))).extract(_stub())

    assert caught.value.code == "schema_invalid"


def test_extraction_schema_error_hides_document_values() -> None:
    data = _evidence_data(gross="SECRET-123-45-6789")

    with pytest.raises(ExtractionError) as caught:
        _extractor(FakeGenAI(_parsed(data))).extract(_stub())

    assert "SECRET" not in str(caught.value)
    assert "gross" in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_extraction_library_input_error_is_wrapped() -> None:
    error = UnsupportedInputError("Model does not support the requested input.")

    with pytest.raises(ExtractionError) as caught:
        _extractor(FakeGenAI(error)).extract(_stub())

    assert caught.value.code == "rejected_input"
    assert caught.value.__cause__ is error


# --- the real idp-genai service ------------------------------------------------------


class FakeModelClient:
    """An `idp_core` ModelClient answering with canned JSON; no network."""

    def __init__(self, output: dict[str, Any]) -> None:
        self._output = output
        self.requests: list[ModelRequest] = []

    @property
    def capabilities(self) -> ModelCapabilities:
        return TEXT_ONLY

    def invoke(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        count = TokenCount(value=1, source="provider_reported")
        return ModelResult(
            provider="fake",
            model=request.model,
            status="succeeded",
            output_json=json.dumps(self._output),
            metrics=CallMetrics(
                context=request.context,
                duration_ms=1.0,
                input_tokens=count,
                output_tokens=count,
            ),
        )


def test_extraction_works_with_the_real_genai_service() -> None:
    client = FakeModelClient(_evidence_data())
    extractor = EvidenceExtractor(
        GenAIService(client), model=MODEL, config=ExtractionConfig()
    )

    evidence = extractor.extract(_stub())

    request = client.requests[0]
    user_text = request.messages[-1].content
    assert evidence.net == Decimal("1224.7")
    assert f"<untrusted_document>\n{OCR_TEXT}\n</untrusted_document>" in user_text
    assert request.response_schema_json is not None
    schema = json.loads(request.response_schema_json)
    assert set(schema["properties"]) == set(PaystubEvidence.model_fields)

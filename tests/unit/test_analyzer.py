from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from idp_core.models import ModelCapabilities
from idp_genai.responses import ParsedResponse
from idp_genai.service import Attachment

from paystub_agi.analyzer import PaystubAnalyzer
from paystub_agi.config import AnalyzerConfig, ReadingConfig
from paystub_agi.errors import ConfigError, ExtractionError, ReadingError
from paystub_agi.models import (
    CheckCode,
    CheckName,
    Decision,
    PaystubEvidence,
    StubStatus,
)
from paystub_agi.reading import PageImage, ReadStub

# Synthetic stub modelled on stub_0006 (numbers only).
TEXT = """--- Page 1 ---
Pay Period 07/01/2026 - 07/14/2026
Regular 1,760.00 Gross Pay 1,760.00
Federal Income Tax 158.40 Social Security 109.12 Medicare 25.52
Deductions Medical 85.00 Dental 12.00 401k 70.40
Benefits Pension ER 88.00
Net Pay 1,299.56"""
PNG = PageImage(page_number=1, media_type="image/png", data=b"png")


def _row(label: str, amount: str, heading: str = "Deductions", **extra: Any) -> Any:
    return {
        "label": label,
        "amount": amount,
        "section_heading": heading,
        "codes": [],
        "markers": [],
        "in_employer_section": heading == "Benefits",
        "in_brackets": extra.get("in_brackets", False),
    }


def _line(label: str, amount: str) -> dict[str, Any]:
    return {"label": label, "amount": amount, "in_brackets": False}


def _evidence(**overrides: Any) -> PaystubEvidence:
    values: dict[str, Any] = {
        "gross": "1760.00",
        "net": "1299.56",
        "pay_frequency": None,
        "period_start": "2026-07-01",
        "period_end": "2026-07-14",
        "pay_date": None,
        "federal_taxable_wages": None,
        "annual_amount": None,
        "earnings": [_line("Regular", "1760.00")],
        "taxes": [
            _line("Federal Income Tax", "158.40"),
            _line("Social Security", "109.12"),
            _line("Medicare", "25.52"),
        ],
        "deductions": [
            _row("Medical", "85.00"),
            _row("Dental", "12.00"),
            _row("401k", "70.40"),
            _row("Pension ER", "88.00", "Benefits"),
        ],
        "footnotes": [],
    }
    values.update(overrides)
    return PaystubEvidence.model_validate(values)


class FakeReader:
    """A `StubReader` that records every call."""

    def __init__(
        self,
        text: str = TEXT,
        pages: tuple[int, ...] = (1, 2),
        error: ReadingError | None = None,
    ) -> None:
        self._text, self._pages, self._error = text, pages, error
        self.reads: list[tuple[Path, bool]] = []
        self.renders: list[tuple[Path, tuple[int, ...]]] = []

    @contextmanager
    def local_copy(self, source: str) -> Iterator[Path]:
        yield Path(source)

    def read_file(self, path: Path, *, images: bool) -> ReadStub:
        self.reads.append((path, images))
        if self._error is not None:
            raise self._error
        return ReadStub(
            text=self._text,
            reader="fake",
            pages=self._pages,
            images=(PNG,) if images else (),
        )

    def render(self, path: Path, pages: Sequence[int]) -> tuple[PageImage, ...]:
        self.renders.append((path, tuple(pages)))
        return (PNG,)


class FakeExtractor:
    """An `Extractor` returning canned evidence; records what it was given."""

    def __init__(
        self,
        evidence: PaystubEvidence | None = None,
        *,
        wants_images: bool = False,
        error: ExtractionError | None = None,
    ) -> None:
        self._evidence = evidence or _evidence()
        self._wants_images = wants_images
        self._error = error
        self.stubs: list[ReadStub] = []

    @property
    def wants_images(self) -> bool:
        return self._wants_images

    def extract(self, stub: ReadStub) -> PaystubEvidence:
        self.stubs.append(stub)
        if self._error is not None:
            raise self._error
        return self._evidence


class MemoryStore:
    def __init__(self) -> None:
        self.items: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.items.get(key)

    def put(self, key: str, value: str) -> None:
        self.items[key] = value


@pytest.fixture()
def pdf(tmp_path: Path) -> Path:
    path = tmp_path / "stub.pdf"
    path.write_bytes(b"%PDF-1.4 synthetic")
    return path


def _analyzer(
    reader: FakeReader | None = None,
    extractor: FakeExtractor | None = None,
    *,
    store: MemoryStore | None = None,
    **config: Any,
) -> PaystubAnalyzer:
    return PaystubAnalyzer(
        AnalyzerConfig.from_mapping(config),
        reader=reader or FakeReader(),
        extractor=extractor or FakeExtractor(),
        store=store,
    )


# --- the whole chain -----------------------------------------------------------------


def test_analyzer_clean_stub_is_ok_with_agi(pdf: Path) -> None:
    evidence = _evidence()

    result = _analyzer(extractor=FakeExtractor(evidence)).analyze(str(pdf))

    assert result.status is StubStatus.OK
    assert result.flags == ()
    assert result.agi.agi == Decimal("45760.00")
    assert [d.line.label for d in result.decisions] == [
        "Medical",
        "Dental",
        "401k",
        "Pension ER",
    ]
    assert result.decisions[3].decision is Decision.EXCLUDED
    assert result.evidence == evidence
    assert (result.reader, result.read_from_store) == ("fake", False)


def test_analyzer_result_repr_has_no_document_values(pdf: Path) -> None:
    evidence = _evidence(deductions=[_row("SECRET-LABEL", "85.00")])

    result = _analyzer(extractor=FakeExtractor(evidence)).analyze(str(pdf))

    assert "SECRET" not in repr(result)
    assert "85.00" not in repr(result)
    assert "status" in repr(result)


def test_analyzer_gives_checks_the_ocr_text(pdf: Path) -> None:
    reader = FakeReader(text="--- Page 1 ---\nNothing printed here")

    result = _analyzer(reader).analyze(str(pdf))

    assert CheckName.GROUNDING not in result.checks_not_run
    assert CheckCode.AMOUNT_NOT_IN_DOCUMENT in [f.code for f in result.flags]
    assert result.status is StubStatus.OK


# --- status --------------------------------------------------------------------------


def test_analyzer_review_flag_makes_stub_needs_review(pdf: Path) -> None:
    evidence = _evidence(deductions=[_row("Medical", "85.00", in_brackets=True)])

    result = _analyzer(extractor=FakeExtractor(evidence)).analyze(str(pdf))

    assert result.status is StubStatus.NEEDS_REVIEW
    assert all(d.decision is not Decision.NEEDS_REVIEW for d in result.decisions)


def test_analyzer_review_decision_makes_stub_needs_review(pdf: Path) -> None:
    analyzer = _analyzer(rules={"bare_benefit_names": "needs_review"})

    result = analyzer.analyze(str(pdf))

    assert result.status is StubStatus.NEEDS_REVIEW
    assert not [f for f in result.flags if f.send_to_review]


def test_analyzer_missing_agi_makes_stub_needs_review(pdf: Path) -> None:
    evidence = _evidence(period_start=None, period_end=None)

    result = _analyzer(extractor=FakeExtractor(evidence)).analyze(str(pdf))

    assert result.agi.agi is None
    assert result.status is StubStatus.NEEDS_REVIEW


@pytest.mark.parametrize(
    "overrides",
    [
        {"gross": "0.00"},
        {"gross": "0.00", "deductions": [_row("Medical", "85.00", in_brackets=True)]},
    ],
)
def test_analyzer_zero_gross_is_invalid(pdf: Path, overrides: dict[str, Any]) -> None:
    evidence = _evidence(**overrides)

    result = _analyzer(extractor=FakeExtractor(evidence)).analyze(str(pdf))

    assert result.status is StubStatus.INVALID
    assert result.agi.invalid_proof_of_income is True


def test_analyzer_flagged_rows_are_moved_to_review(pdf: Path) -> None:
    evidence = _evidence(federal_taxable_wages="1500.00")
    analyzer = _analyzer(
        extractor=FakeExtractor(evidence), checks={"send_to_review": True}
    )

    result = analyzer.analyze(str(pdf))

    medical = result.decisions[0]
    assert medical.decision is Decision.NEEDS_REVIEW
    assert medical.escalated_by is CheckCode.FEDERAL_TAXABLE_WAGES_MISMATCH
    assert result.status is StubStatus.NEEDS_REVIEW


# --- the saved OCR read (DL-039) -----------------------------------------------------


def test_analyzer_without_store_reads_every_time(pdf: Path) -> None:
    reader = FakeReader()
    analyzer = _analyzer(reader)

    analyzer.analyze(str(pdf))
    analyzer.analyze(str(pdf))

    assert len(reader.reads) == 2


def test_analyzer_saves_the_read_and_reuses_it(pdf: Path) -> None:
    reader, extractor = FakeReader(), FakeExtractor()
    analyzer = _analyzer(reader, extractor, store=MemoryStore())

    first = analyzer.analyze(str(pdf))
    second = analyzer.analyze(str(pdf))

    assert len(reader.reads) == 1
    assert (first.read_from_store, second.read_from_store) == (False, True)
    assert second.reader == "fake"
    assert extractor.stubs[1].text == extractor.stubs[0].text == TEXT
    assert extractor.stubs[1].pages == (1, 2)


def test_analyzer_calls_the_model_on_every_run(pdf: Path) -> None:
    extractor = FakeExtractor()
    analyzer = _analyzer(extractor=extractor, store=MemoryStore())

    for _ in range(3):
        analyzer.analyze(str(pdf))

    assert len(extractor.stubs) == 3


def test_analyzer_store_finds_a_renamed_file(pdf: Path, tmp_path: Path) -> None:
    renamed = tmp_path / "renamed.pdf"
    renamed.write_bytes(pdf.read_bytes())
    reader = FakeReader()
    analyzer = _analyzer(reader, store=MemoryStore())

    analyzer.analyze(str(pdf))
    result = analyzer.analyze(str(renamed))

    assert len(reader.reads) == 1
    assert result.read_from_store is True


def test_analyzer_store_reads_again_when_the_file_changes(
    pdf: Path, tmp_path: Path
) -> None:
    other = tmp_path / "other.pdf"
    other.write_bytes(b"%PDF-1.4 different")
    reader = FakeReader()
    analyzer = _analyzer(reader, store=MemoryStore())

    analyzer.analyze(str(pdf))
    analyzer.analyze(str(other))

    assert len(reader.reads) == 2


# --- page images ---------------------------------------------------------------------


def test_analyzer_asks_for_images_only_when_the_model_wants_them(pdf: Path) -> None:
    for wants in (False, True):
        reader, extractor = FakeReader(), FakeExtractor(wants_images=wants)

        _analyzer(reader, extractor).analyze(str(pdf))

        assert reader.reads[0][1] is wants
        assert extractor.stubs[0].images == ((PNG,) if wants else ())


def test_analyzer_rerenders_images_for_a_saved_read(pdf: Path) -> None:
    reader, extractor = FakeReader(), FakeExtractor(wants_images=True)
    analyzer = _analyzer(reader, extractor, store=MemoryStore())

    analyzer.analyze(str(pdf))
    analyzer.analyze(str(pdf))

    assert reader.renders == [(pdf, (1, 2))]
    assert extractor.stubs[1].images == (PNG,)


def test_analyzer_saved_read_without_images_does_not_render(pdf: Path) -> None:
    reader = FakeReader()
    analyzer = _analyzer(reader, store=MemoryStore())

    analyzer.analyze(str(pdf))
    analyzer.analyze(str(pdf))

    assert reader.renders == []


# --- failures ------------------------------------------------------------------------


def test_analyzer_reading_error_gives_no_result(pdf: Path) -> None:
    extractor = FakeExtractor()
    reader = FakeReader(error=ReadingError("unreadable", code="no_evidence"))

    with pytest.raises(ReadingError):
        _analyzer(reader, extractor).analyze(str(pdf))

    assert extractor.stubs == []


def test_analyzer_extraction_error_gives_no_result(pdf: Path) -> None:
    extractor = FakeExtractor(error=ExtractionError("bad", code="schema_invalid"))

    with pytest.raises(ExtractionError):
        _analyzer(extractor=extractor).analyze(str(pdf))


# --- building the standard parts -----------------------------------------------------


class FakeGenAI:
    capabilities = ModelCapabilities(features=("text",))

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
        raise AssertionError("not called in these tests")


def test_analyzer_create_builds_the_standard_parts() -> None:
    config = AnalyzerConfig(reading=ReadingConfig(strategy=("pdfplumber",)))

    analyzer = PaystubAnalyzer.create(config, genai=FakeGenAI(), model="m")

    assert isinstance(analyzer, PaystubAnalyzer)


def test_analyzer_create_reader_not_supplied_is_config_error() -> None:
    with pytest.raises(ConfigError, match="textract"):
        PaystubAnalyzer.create(AnalyzerConfig(), genai=FakeGenAI(), model="m")


def test_analyzer_create_blank_model_is_config_error() -> None:
    config = AnalyzerConfig(reading=ReadingConfig(strategy=("pdfplumber",)))

    with pytest.raises(ConfigError, match="model"):
        PaystubAnalyzer.create(config, genai=FakeGenAI(), model=" ")

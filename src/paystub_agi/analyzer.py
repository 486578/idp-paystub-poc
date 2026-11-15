"""Runs every step for one stub (architecture section 5). Holds no business rules.

read (or load the saved read) → model → rules → checks → review → AGI → status.
The model is called on every run (DL-039); only the OCR read may come from the store.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path

from idp_core.contracts import Reader
from idp_ocr import S3Downloader

from paystub_agi.agi import compute_agi
from paystub_agi.checks import apply_review, run_checks
from paystub_agi.config import AnalyzerConfig
from paystub_agi.extraction import EvidenceExtractor, Extractor, GenAI
from paystub_agi.models import (
    AgiResult,
    CheckReport,
    Decision,
    DeductionDecision,
    PaystubResult,
    StubStatus,
)
from paystub_agi.reading import IdpOcrStubReader, ReadStub, StubReader
from paystub_agi.rules import classify
from paystub_agi.store import (
    EvidenceStore,
    StoredRead,
    load_read,
    read_key,
    save_read,
)


def _status(
    decisions: Sequence[DeductionDecision], report: CheckReport, agi: AgiResult
) -> StubStatus:
    """DL-040: invalid first (there's no AGI to review), then any reason to review."""
    if agi.invalid_proof_of_income:
        return StubStatus.INVALID
    if (
        agi.agi is None
        or any(flag.send_to_review for flag in report.flags)
        or any(d.decision is Decision.NEEDS_REVIEW for d in decisions)
    ):
        return StubStatus.NEEDS_REVIEW
    return StubStatus.OK


class PaystubAnalyzer:
    """One analyzer per model; several analyzers may share one store."""

    def __init__(
        self,
        config: AnalyzerConfig,
        *,
        reader: StubReader,
        extractor: Extractor,
        store: EvidenceStore | None = None,
    ) -> None:
        self._config = config
        self._reader = reader
        self._extractor = extractor
        self._store = store

    @classmethod
    def create(
        cls,
        config: AnalyzerConfig,
        *,
        genai: GenAI,
        model: str,
        readers: Mapping[str, Reader] | None = None,
        downloader: S3Downloader | None = None,
        store: EvidenceStore | None = None,
    ) -> PaystubAnalyzer:
        """Builds the standard parts from the caller's clients and settings."""
        return cls(
            config,
            reader=IdpOcrStubReader(
                config.reading, readers=readers, downloader=downloader
            ),
            extractor=EvidenceExtractor(genai, model=model, config=config.extraction),
            store=store,
        )

    def analyze(self, source: str) -> PaystubResult:
        """`source` is a local path or `s3://bucket/key`."""
        with self._reader.local_copy(source) as path:
            stub, from_store = self._read(path)
        evidence = self._extractor.extract(stub)
        decisions = classify(evidence, self._config.rules)
        report = run_checks(evidence, decisions, self._config.checks, stub.text)
        reviewed = apply_review(decisions, report)
        agi = compute_agi(evidence, reviewed, self._config.agi)
        return PaystubResult(
            status=_status(reviewed, report, agi),
            agi=agi,
            decisions=reviewed,
            flags=report.flags,
            checks_not_run=report.not_run,
            evidence=evidence,
            reader=stub.reader,
            read_from_store=from_store,
        )

    def _read(self, path: Path) -> tuple[ReadStub, bool]:
        images = self._extractor.wants_images
        if self._store is None:
            return self._reader.read_file(path, images=images), False
        key = read_key(path.read_bytes(), self._config.reading)
        saved = load_read(self._store, key)
        if saved is None:
            stub = self._reader.read_file(path, images=images)
            read = StoredRead(text=stub.text, reader=stub.reader, pages=stub.pages)
            save_read(self._store, key, read)
            return stub, False
        pictures = self._reader.render(path, saved.pages) if images else ()
        stub = ReadStub(
            text=saved.text, reader=saved.reader, pages=saved.pages, images=pictures
        )
        return stub, True

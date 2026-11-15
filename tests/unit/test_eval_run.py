from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from evaluation.download import StubRef
from evaluation.run import StubOutcome, run_models, save_outcome
from paystub_agi.errors import ExtractionError, ReadingError
from paystub_agi.models import AgiResult, PaystubEvidence, PaystubResult, StubStatus

REF_A = StubRef(folder="advs_paystubs", stub="stub_0006")
REF_B = StubRef(folder="generated_scanned", stub="stub01")


def _result() -> PaystubResult:
    evidence = PaystubEvidence.model_validate(
        {
            "gross": "1760.00",
            "net": "1299.56",
            "pay_frequency": None,
            "period_start": None,
            "period_end": None,
            "pay_date": None,
            "federal_taxable_wages": None,
            "annual_amount": None,
            "earnings": [],
            "taxes": [],
            "deductions": [],
            "footnotes": [],
        }
    )
    agi = AgiResult(
        agi=Decimal("45760.00"),
        agi_if_review_pretax=Decimal("45760.00"),
        pay_frequency=None,
        frequency_source=None,
        periods_per_year=26,
        method=None,
        one_time_total=Decimal(0),
        pretax_total=Decimal(0),
        review_total=Decimal(0),
        warnings=(),
    )
    return PaystubResult(
        status=StubStatus.OK,
        agi=agi,
        decisions=(),
        flags=(),
        checks_not_run=(),
        evidence=evidence,
        reader="pdfplumber",
        read_from_store=False,
    )


class FakeAnalyzer:
    def __init__(self, failures: dict[str, Exception] | None = None) -> None:
        self._failures = failures or {}
        self.sources: list[str] = []

    def analyze(self, source: str) -> PaystubResult:
        self.sources.append(source)
        for name, error in self._failures.items():
            if source.endswith(name):
                raise error
        return _result()


def _stubs(tmp_path: Path) -> list[tuple[StubRef, Path]]:
    return [
        (REF_A, tmp_path / "advs_paystubs" / "stub_0006.pdf"),
        (REF_B, tmp_path / "generated_scanned" / "stub01.png"),
    ]


def test_eval_run_every_model_reads_every_stub(tmp_path: Path) -> None:
    opus, gpt = FakeAnalyzer(), FakeAnalyzer()

    outcomes = list(run_models({"opus": opus, "gpt": gpt}, _stubs(tmp_path)))

    assert [(o.model, o.stub) for o in outcomes] == [
        ("opus", "advs_paystubs/stub_0006"),
        ("opus", "generated_scanned/stub01"),
        ("gpt", "advs_paystubs/stub_0006"),
        ("gpt", "generated_scanned/stub01"),
    ]
    assert opus.sources == [str(p) for _, p in _stubs(tmp_path)]
    assert all(o.result is not None and o.error is None for o in outcomes)


@pytest.mark.parametrize(
    ("error", "kind", "code"),
    [
        (
            ExtractionError("bad answer", code="schema_invalid"),
            "ExtractionError",
            "schema_invalid",
        ),
        (ReadingError("unreadable", code="no_evidence"), "ReadingError", "no_evidence"),
        (ReadingError("not found"), "ReadingError", None),
    ],
)
def test_eval_run_records_a_failure_and_continues(
    tmp_path: Path, error: Exception, kind: str, code: str | None
) -> None:
    analyzer = FakeAnalyzer({"stub_0006.pdf": error})

    first, second = run_models({"opus": analyzer}, _stubs(tmp_path))

    assert (first.result, first.error, first.error_code) == (None, kind, code)
    assert first.message == str(error)
    assert second.result is not None


def test_eval_run_unexpected_errors_stop_the_run(tmp_path: Path) -> None:
    analyzer = FakeAnalyzer({"stub_0006.pdf": RuntimeError("credentials expired")})

    with pytest.raises(RuntimeError):
        list(run_models({"opus": analyzer}, _stubs(tmp_path)))


def test_eval_run_saves_one_json_per_model_and_stub(tmp_path: Path) -> None:
    outcome = StubOutcome(model="opus", stub=REF_A.id, result=_result())

    path = save_outcome(tmp_path / "results", "run-1", outcome)

    assert path == tmp_path / "results" / "run-1" / "opus" / "advs_paystubs" / (
        "stub_0006.json"
    )
    assert StubOutcome.model_validate_json(path.read_text(encoding="utf-8")) == outcome


@pytest.mark.parametrize("bad", ["", "../x", "a b", "run/1"])
def test_eval_run_rejects_unsafe_run_ids(tmp_path: Path, bad: str) -> None:
    outcome = StubOutcome(model="opus", stub=REF_A.id, result=_result())

    with pytest.raises(ValueError, match="run id"):
        save_outcome(tmp_path, bad, outcome)


@pytest.mark.parametrize(
    ("model", "stub"), [("../opus", REF_A.id), ("opus", "a/../b"), ("opus", "x")]
)
def test_eval_run_outcome_rejects_unsafe_names(model: str, stub: str) -> None:
    with pytest.raises(ValueError):
        StubOutcome(model=model, stub=stub, result=_result())


def test_eval_run_outcome_needs_a_result_or_an_error() -> None:
    values: dict[str, Any] = {"model": "opus", "stub": REF_A.id}

    with pytest.raises(ValueError):
        StubOutcome.model_validate(values)
    with pytest.raises(ValueError):
        StubOutcome.model_validate({**values, "result": _result(), "error": "X"})

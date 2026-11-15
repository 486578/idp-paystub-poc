import csv
from decimal import Decimal
from pathlib import Path

from evaluation.report import summarize, write_report
from evaluation.score import FieldScore, RowScore, StubScore
from paystub_agi.models import Decision, RuleId


def _stub(
    model: str,
    stub: str,
    *,
    status: str = "ok",
    agi_match: bool = True,
    rows: tuple[RowScore, ...] = (),
    fields: tuple[FieldScore, ...] = (),
    error: str | None = None,
) -> StubScore:
    return StubScore(
        model=model,
        stub=stub,
        status=status,
        error=error,
        fields=fields,
        rows=rows,
        our_agi=None if status == "failed" else Decimal("45760.00"),
        key_agi=Decimal("45760.00"),
        agi_match=agi_match,
        agi_difference=None if status == "failed" else Decimal(0),
    )


AGREE = RowScore(outcome="agree", our_decision=Decision.NOT_PRETAX, rule_id=RuleId.R9)
OPEN = RowScore(
    outcome="disagree",
    direction="key_subtracts",
    bucket="open_question",
    key_type="health",
    key_amount=Decimal("85.00"),
    key_pretax=True,
    our_label="Medical",
    our_amount=Decimal("85.00"),
    our_decision=Decision.NOT_PRETAX,
    rule_id=RuleId.R9,
)
MISSING = RowScore(outcome="missing", bucket="extraction_problem", key_type="dental")
NET_WRONG = FieldScore(name="net", ours="1.00", key="2.00", match=False)
GROSS_OK = FieldScore(name="gross", ours="1.00", key="1.00", match=True)

SCORES = [
    _stub("opus", "a/s1", rows=(AGREE, OPEN), fields=(GROSS_OK, NET_WRONG)),
    _stub("opus", "a/s2", status="needs_review", agi_match=False, rows=(MISSING,)),
    _stub("opus", "a/s3", status="failed", agi_match=False, error="ExtractionError"),
    _stub("gpt", "a/s1", rows=(AGREE,)),
]


def test_eval_report_summary_counts_per_model() -> None:
    opus, gpt = summarize(SCORES)

    assert (opus.model, opus.stubs, opus.failed, opus.agi_exact) == ("opus", 3, 1, 1)
    assert opus.statuses == {"ok": 1, "needs_review": 1, "failed": 1}
    assert opus.outcomes == {"agree": 1, "disagree": 1, "missing": 1}
    assert opus.buckets == {"open_question": 1, "extraction_problem": 1}
    assert opus.field_mismatches == {"net": 1}
    assert (gpt.model, gpt.stubs, gpt.agi_exact) == ("gpt", 1, 1)


def test_eval_report_writes_one_csv_row_per_stub(tmp_path: Path) -> None:
    write_report(SCORES, tmp_path)

    with (tmp_path / "stubs.csv").open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert [(r["model"], r["stub"], r["status"]) for r in rows] == [
        ("opus", "a/s1", "ok"),
        ("opus", "a/s2", "needs_review"),
        ("opus", "a/s3", "failed"),
        ("gpt", "a/s1", "ok"),
    ]
    assert rows[0]["field_mismatches"] == "net"
    assert (rows[0]["agi_match"], rows[0]["agi_difference"]) == ("True", "0")
    assert rows[2]["error"] == "ExtractionError"


def test_eval_report_writes_one_csv_row_per_deduction_row(tmp_path: Path) -> None:
    write_report(SCORES, tmp_path)

    with (tmp_path / "rows.csv").open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 4
    second = rows[1]
    assert (second["model"], second["stub"], second["outcome"]) == (
        "opus",
        "a/s1",
        "disagree",
    )
    assert (second["bucket"], second["rule_id"], second["our_label"]) == (
        "open_question",
        "R9",
        "Medical",
    )


def test_eval_report_writes_a_readable_summary(tmp_path: Path) -> None:
    write_report(SCORES, tmp_path)

    text = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "| opus | 3 | 1 | 1 |" in text
    assert "| gpt | 1 | 0 | 1 |" in text
    assert "open_question" in text

import csv
from decimal import Decimal
from pathlib import Path
from typing import Any

from evaluation.report import explain, summarize, write_report
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


# --- plain-words explanations ----------------------------------------------------------


def _off(**overrides: Any) -> StubScore:
    values: dict[str, Any] = {
        "model": "opus",
        "stub": "a/s9",
        "status": "ok",
        "our_agi": Decimal("47710.00"),
        "key_agi": Decimal("45500.00"),
        "agi_match": False,
        "agi_difference": Decimal("2210.00"),
    }
    values.update(overrides)
    return StubScore(**values)


def test_eval_report_explain_match_has_no_reason() -> None:
    assert explain(SCORES[0]) == ("match", "")


def test_eval_report_explain_failed_gives_the_error() -> None:
    score = _off(status="failed", our_agi=None, agi_difference=None)
    score = score.model_copy(
        update={"error": "ReadingError", "error_code": "unsupported_input"}
    )

    assert explain(score) == ("failed", "ReadingError (unsupported_input)")


def test_eval_report_explain_both_without_agi() -> None:
    score = _off(our_agi=None, key_agi=None, agi_difference=None)

    assert explain(score) == ("both_empty", "Neither we nor the key have an AGI")


def test_eval_report_explain_pretax_disagreement() -> None:
    result, why = explain(_off(rows=(AGREE, OPEN)))

    assert result == "mismatch"
    assert why == '"Medical" 85.00: ours not pre-tax (R9), key pre-tax'


def test_eval_report_explain_row_sent_to_review() -> None:
    row = RowScore(outcome="needs_review", our_label="HSA", our_amount=Decimal("5"))

    assert explain(_off(rows=(row,)))[1] == '"HSA" 5: sent to review'


def test_eval_report_explain_names_only_fields_that_change_agi() -> None:
    gross = FieldScore(name="gross", ours="1.00", key="2.00", match=False)
    one_time = FieldScore(name="one_time_total", ours=None, key="100.0", match=False)

    why = explain(_off(fields=(gross, NET_WRONG, one_time)))[1]

    assert why == (
        "Gross differs: ours 1.00, key 2.00; One-time pay differs: ours none, key 100.0"
    )


def test_eval_report_explain_federal_taxable_wages_method() -> None:
    why = explain(_off(agi_method="federal_taxable_wages"))[1]

    assert why == "Ours starts from the printed federal taxable wages"


def test_eval_report_explain_missing_row_only_when_key_says_pretax() -> None:
    pretax = RowScore(
        outcome="missing", key_type="401k", key_amount=Decimal("50"), key_pretax=True
    )

    why = explain(_off(rows=(pretax, MISSING)))[1]

    assert why == "Missing pre-tax deduction: key 401k 50"


def test_eval_report_explain_extra_row_only_when_counted_pretax() -> None:
    pretax = RowScore(
        outcome="extra",
        our_label="Tip Offset",
        our_amount=Decimal("150"),
        our_decision=Decision.PRETAX,
    )
    other = pretax.model_copy(update={"our_decision": Decision.NOT_PRETAX})

    why = explain(_off(rows=(pretax, other)))[1]

    assert why == 'Extra row counted pre-tax: "Tip Offset" 150'


def test_eval_report_explain_says_when_no_cause_is_found() -> None:
    assert explain(_off())[1] == "No row or field difference found"


def test_eval_report_explain_says_we_have_no_agi() -> None:
    score = _off(status="needs_review", our_agi=None, agi_difference=None)

    assert explain(score)[1] == "We have no AGI (status needs_review)"


def test_eval_report_writes_a_simple_overview_csv(tmp_path: Path) -> None:
    write_report([*SCORES, _off(rows=(OPEN,))], tmp_path)

    with (tmp_path / "overview.csv").open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert list(rows[0]) == [
        "model",
        "stub",
        "result",
        "our_agi",
        "key_agi",
        "difference",
        "why",
    ]
    assert [(r["stub"], r["result"]) for r in rows] == [
        ("a/s1", "match"),
        ("a/s2", "mismatch"),
        ("a/s3", "failed"),
        ("a/s1", "match"),
        ("a/s9", "mismatch"),
    ]
    assert rows[4]["why"] == '"Medical" 85.00: ours not pre-tax (R9), key pre-tax'


def test_eval_report_summary_explains_mismatches_and_failures(tmp_path: Path) -> None:
    row = OPEN.model_copy(update={"our_label": "A | B"})
    write_report([*SCORES, _off(rows=(row,))], tmp_path)

    text = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert (
        '| a/s9 | 47710.00 | 45500.00 | 2210.00 | "A \\| B" 85.00: ours not pre-tax '
        "(R9), key pre-tax |" in text
    )
    assert "| a/s3 | ExtractionError |" in text

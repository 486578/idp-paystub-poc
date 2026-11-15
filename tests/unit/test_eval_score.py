from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from evaluation.answer_keys import AnswerKey
from evaluation.run import StubOutcome
from evaluation.score import score_outcome
from paystub_agi.models import (
    AgiResult,
    Decision,
    DeductionDecision,
    DeductionLine,
    PaystubEvidence,
    PaystubResult,
    RuleId,
    StubStatus,
)

STUB = "advs_paystubs/stub_0006"


def _key(deductions: list[tuple[str, str, bool | None]], **overrides: Any) -> AnswerKey:
    values: dict[str, Any] = {
        "schema_version": "1",
        "stub_id": "stub_0006",
        "category": "advs_paystubs",
        "amounts": {"gross": "1760.00", "net": "1299.56"},
        "deductions": [
            {"type": t, "amount": a, "employee_pretax": p} for t, a, p in deductions
        ],
        "period": {
            "start_date": "2026-07-01",
            "end_date": "2026-07-14",
            "pay_date": "2026-07-17",
        },
        "calculated": {
            "agi": "45760.00",
            "annual_gross": "45760.00",
            "pay_frequency": "biweekly",
            "periods_per_year": 26,
            "frequency_source": "period_dates",
            "method": "gross_less_pretax",
            "one_time_total": "0",
            "pretax_deductions": "0",
            "warnings": [],
        },
    }
    values.update(overrides)
    return AnswerKey.model_validate(values)


def _decided(
    label: str, amount: str, decision: Decision, rule: RuleId
) -> DeductionDecision:
    line = DeductionLine(
        label=label,
        amount=Decimal(amount),
        section_heading="Deductions",
        codes=(),
        markers=(),
        in_employer_section=False,
        in_brackets=False,
    )
    return DeductionDecision(line=line, decision=decision, rule_id=rule, evidence=label)


def _outcome(
    decisions: list[DeductionDecision],
    *,
    agi: str | None = "45760.00",
    one_time: str = "0",
    **evidence: Any,
) -> StubOutcome:
    values: dict[str, Any] = {
        "gross": "1760.00",
        "net": "1299.56",
        "pay_frequency": None,
        "period_start": "2026-07-01",
        "period_end": "2026-07-14",
        "pay_date": "2026-07-17",
        "federal_taxable_wages": None,
        "annual_amount": None,
        "earnings": [],
        "taxes": [],
        "deductions": [d.line.model_dump() for d in decisions],
        "footnotes": [],
    }
    values.update(evidence)
    result = PaystubResult(
        status=StubStatus.OK,
        agi=AgiResult(
            agi=None if agi is None else Decimal(agi),
            agi_if_review_pretax=None if agi is None else Decimal(agi),
            pay_frequency=None,
            frequency_source=None,
            periods_per_year=26,
            method=None,
            one_time_total=Decimal(one_time),
            pretax_total=Decimal(0),
            review_total=Decimal(0),
            warnings=(),
        ),
        decisions=tuple(decisions),
        flags=(),
        checks_not_run=(),
        evidence=PaystubEvidence.model_validate(values),
        reader="pdfplumber",
        read_from_store=False,
    )
    return StubOutcome(model="opus", stub=STUB, result=result)


def _score(
    outcome: StubOutcome, key: AnswerKey, disputed: frozenset[str] = frozenset()
) -> Any:
    return score_outcome(outcome, key, disputed=disputed)


# --- 7b: fields ----------------------------------------------------------------------


def test_eval_score_matching_fields_all_match() -> None:
    score = _score(_outcome([]), _key([]))

    assert [(f.name, f.match) for f in score.fields] == [
        ("gross", True),
        ("net", True),
        ("period_start", True),
        ("period_end", True),
        ("pay_date", True),
        ("one_time_total", True),
    ]


def test_eval_score_money_within_a_cent_matches() -> None:
    score = _score(_outcome([], gross="1760.01"), _key([]))

    assert score.fields[0].match is True


def test_eval_score_money_off_by_more_than_a_cent_does_not_match() -> None:
    score = _score(_outcome([], net="1299.58"), _key([]))

    net = score.fields[1]
    assert (net.match, net.ours, net.key) == (False, "1299.58", "1299.56")


def test_eval_score_different_date_does_not_match() -> None:
    score = _score(_outcome([], pay_date=date(2026, 7, 18).isoformat()), _key([]))

    assert score.fields[4].match is False


def test_eval_score_missing_value_on_one_side_does_not_match() -> None:
    score = _score(_outcome([], gross=None), _key([]))

    assert score.fields[0].match is False


def test_eval_score_one_time_total_compares_with_the_key() -> None:
    score = _score(_outcome([], one_time="132.00"), _key([]))

    assert (score.fields[5].ours, score.fields[5].key) == ("132.00", "0")


# --- 7b: rows paired by amount -------------------------------------------------------


def test_eval_score_rows_are_paired_by_amount_not_name() -> None:
    decided = [
        _decided("DENTAL EE", "12.00", Decision.NOT_PRETAX, RuleId.R9),
        _decided("Medical", "85.00", Decision.NOT_PRETAX, RuleId.R9),
    ]
    key = _key([("health_insurance", "85.00", False), ("dental", "12.00", False)])

    score = _score(_outcome(decided), key)

    assert [(r.key_type, r.our_label, r.outcome) for r in score.rows] == [
        ("health_insurance", "Medical", "agree"),
        ("dental", "DENTAL EE", "agree"),
    ]


def test_eval_score_negative_amounts_pair_with_positive_key_amounts() -> None:
    decided = [_decided("Health", "-87.00", Decision.PRETAX, RuleId.R6)]

    score = _score(_outcome(decided), _key([("health", "87.00", True)]))

    assert score.rows[0].outcome == "agree"


def test_eval_score_key_row_we_did_not_read_is_missing() -> None:
    score = _score(_outcome([]), _key([("dental", "12.00", False)]))

    row = score.rows[0]
    assert (row.outcome, row.bucket, row.our_label) == (
        "missing",
        "extraction_problem",
        None,
    )


def test_eval_score_our_extra_row_is_an_extraction_problem() -> None:
    decided = [_decided("Mystery", "5.00", Decision.NOT_PRETAX, RuleId.R10)]

    score = _score(_outcome(decided), _key([]))

    assert (score.rows[0].outcome, score.rows[0].bucket) == (
        "extra",
        "extraction_problem",
    )


def test_eval_score_extra_employer_row_is_expected() -> None:
    decided = [_decided("Pension ER", "88.00", Decision.EXCLUDED, RuleId.R1)]

    score = _score(_outcome(decided), _key([]))

    assert (score.rows[0].outcome, score.rows[0].bucket) == ("extra_excluded", None)


def test_eval_score_each_row_pairs_once() -> None:
    decided = [_decided("Dental", "12.00", Decision.NOT_PRETAX, RuleId.R9)]
    key = _key([("dental", "12.00", False), ("vision", "12.00", False)])

    score = _score(_outcome(decided), key)

    assert [r.outcome for r in score.rows] == ["agree", "missing"]


# --- 7b: key rows that are taxes (pilot finding: keys list taxes as deductions) ------


def _tax(label: str, amount: str) -> dict[str, Any]:
    return {"label": label, "amount": amount, "in_brackets": False}


def test_eval_score_key_tax_row_pairs_with_our_tax_line() -> None:
    outcome = _outcome([], taxes=[_tax("FIT", "158.40")])

    row = _score(outcome, _key([("federal_tax", "158.40", False)])).rows[0]

    assert (row.outcome, row.bucket, row.our_label) == ("tax_line", None, "FIT")


def test_eval_score_our_deduction_is_paired_before_a_tax_of_the_same_amount() -> None:
    decided = [_decided("Dental", "12.00", Decision.NOT_PRETAX, RuleId.R9)]
    outcome = _outcome(decided, taxes=[_tax("LST", "12.00")])

    rows = _score(outcome, _key([("dental", "12.00", False)])).rows

    assert [(r.outcome, r.our_label) for r in rows] == [("agree", "Dental")]


def test_eval_score_tax_lines_pair_once() -> None:
    outcome = _outcome([], taxes=[_tax("FIT", "10.00")])
    key = _key([("federal_tax", "10.00", False), ("state_tax", "10.00", False)])

    assert [r.outcome for r in _score(outcome, key).rows] == ["tax_line", "missing"]


# --- 7c: classification and buckets --------------------------------------------------


@pytest.mark.parametrize(
    ("decision", "key_pretax", "outcome", "direction"),
    [
        (Decision.PRETAX, True, "agree", None),
        (Decision.NOT_PRETAX, False, "agree", None),
        (Decision.EXCLUDED, False, "agree", None),
        (Decision.PRETAX, False, "disagree", "we_subtract"),
        (Decision.NOT_PRETAX, True, "disagree", "key_subtracts"),
        (Decision.NEEDS_REVIEW, True, "needs_review", None),
    ],
)
def test_eval_score_decision_against_the_key_label(
    decision: Decision, key_pretax: bool, outcome: str, direction: str | None
) -> None:
    decided = [_decided("Medical", "85.00", decision, RuleId.R9)]

    row = _score(_outcome(decided), _key([("health", "85.00", key_pretax)])).rows[0]

    assert (row.outcome, row.direction) == (outcome, direction)


@pytest.mark.parametrize(
    ("rule", "bucket"),
    [
        (RuleId.R4, "agreed_rule_disagrees"),
        (RuleId.R1, "agreed_rule_disagrees"),
        (RuleId.R5, "agreed_rule_disagrees"),
        (RuleId.R6, "open_question"),
        (RuleId.R9, "open_question"),
        (RuleId.R10, "open_question"),
    ],
)
def test_eval_score_disagreement_bucket_follows_the_rule(
    rule: RuleId, bucket: str
) -> None:
    decided = [_decided("Medical", "85.00", Decision.PRETAX, rule)]

    row = _score(_outcome(decided), _key([("health", "85.00", False)])).rows[0]

    assert row.bucket == bucket


def test_eval_score_disputed_stub_disagreements_are_known_key_errors() -> None:
    decided = [_decided("Medical", "85.00", Decision.PRETAX, RuleId.R4)]
    key = _key([("health", "85.00", False)])

    row = _score(_outcome(decided), key, frozenset({STUB})).rows[0]

    assert row.bucket == "known_key_error"


def test_eval_score_agreement_has_no_bucket() -> None:
    decided = [_decided("Medical", "85.00", Decision.PRETAX, RuleId.R4)]

    row = _score(_outcome(decided), _key([("health", "85.00", True)])).rows[0]

    assert row.bucket is None


def test_eval_score_unlabelled_key_row_is_reported() -> None:
    decided = [_decided("Medical", "85.00", Decision.PRETAX, RuleId.R4)]

    row = _score(_outcome(decided), _key([("health", "85.00", None)])).rows[0]

    assert (row.outcome, row.bucket) == ("key_unlabelled", None)


# --- 7d: AGI -------------------------------------------------------------------------


def test_eval_score_agi_exact_match() -> None:
    score = _score(_outcome([]), _key([]))

    assert (score.agi_match, score.agi_difference) == (True, Decimal("0.00"))


def test_eval_score_agi_one_cent_off_is_not_a_match() -> None:
    score = _score(_outcome([], agi="45760.01"), _key([]))

    assert (score.agi_match, score.agi_difference) == (False, Decimal("0.01"))


def test_eval_score_no_agi_is_not_a_match() -> None:
    score = _score(_outcome([], agi=None), _key([]))

    assert (score.agi_match, score.our_agi, score.agi_difference) == (False, None, None)


def test_eval_score_status_comes_from_the_result() -> None:
    assert _score(_outcome([]), _key([])).status == "ok"


# --- failed stubs --------------------------------------------------------------------


def test_eval_score_failed_stub_has_no_comparisons() -> None:
    outcome = StubOutcome(
        model="opus", stub=STUB, error="ExtractionError", error_code="schema_invalid"
    )

    score = _score(outcome, _key([("dental", "12.00", False)]))

    assert (score.status, score.error, score.error_code) == (
        "failed",
        "ExtractionError",
        "schema_invalid",
    )
    assert (score.fields, score.rows, score.agi_match) == ((), (), False)
    assert score.key_agi == Decimal("45760.00")

"""Score one outcome against its answer key: 7b fields and rows, 7c, 7d (DL-041).

Rows are paired by amount, not name: the keys use normalised names
(`health_insurance`) while we keep the stub's wording (architecture 7b).
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from evaluation.answer_keys import AnswerKey, KeyDeduction
from evaluation.run import StubOutcome
from paystub_agi.models import Decision, DeductionDecision, PaystubResult, RuleId

_CENT = Decimal("0.01")
# R1–R5 are agreed rules; a disagreement there needs investigating (architecture 7c).
_AGREED_RULES = frozenset({RuleId.R1, RuleId.R2, RuleId.R3, RuleId.R4, RuleId.R5})

Outcome = Literal[
    "agree",
    "disagree",
    "needs_review",
    "key_unlabelled",
    "missing",
    "extra",
    "extra_excluded",
]
Bucket = Literal[
    "known_key_error", "open_question", "agreed_rule_disagrees", "extraction_problem"
]


class _Score(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FieldScore(_Score):
    name: str
    ours: str | None
    key: str | None
    match: bool


class RowScore(_Score):
    key_type: str | None = None
    key_amount: Decimal | None = None
    key_pretax: bool | None = None
    our_label: str | None = None
    our_amount: Decimal | None = None
    our_decision: Decision | None = None
    rule_id: RuleId | None = None
    outcome: Outcome
    direction: Literal["we_subtract", "key_subtracts"] | None = None
    bucket: Bucket | None = None


class StubScore(_Score):
    model: str
    stub: str
    status: str
    error: str | None = None
    error_code: str | None = None
    fields: tuple[FieldScore, ...] = ()
    rows: tuple[RowScore, ...] = ()
    our_agi: Decimal | None = None
    key_agi: Decimal | None
    agi_match: bool = False
    agi_difference: Decimal | None = None


def _money(name: str, ours: Decimal | None, key: Decimal | None) -> FieldScore:
    if ours is None or key is None:
        match = ours is None and key is None
    else:
        match = abs(ours - key) <= _CENT
    return FieldScore(
        name=name,
        ours=None if ours is None else str(ours),
        key=None if key is None else str(key),
        match=match,
    )


def _date(name: str, ours: date | None, key: date | None) -> FieldScore:
    return FieldScore(
        name=name,
        ours=None if ours is None else ours.isoformat(),
        key=None if key is None else key.isoformat(),
        match=ours == key,
    )


def _fields(result: PaystubResult, key: AnswerKey) -> tuple[FieldScore, ...]:
    ours = result.evidence
    return (
        _money("gross", ours.gross, key.amounts.gross),
        _money("net", ours.net, key.amounts.net),
        _date("period_start", ours.period_start, key.period.start_date),
        _date("period_end", ours.period_end, key.period.end_date),
        _date("pay_date", ours.pay_date, key.period.pay_date),
        _money(
            "one_time_total",
            result.agi.one_time_total,
            key.calculated.one_time_total,
        ),
    )


def _paired(key_row: KeyDeduction, ours: DeductionDecision, disputed: bool) -> RowScore:
    common = {
        "key_type": key_row.type,
        "key_amount": key_row.amount,
        "key_pretax": key_row.employee_pretax,
        "our_label": ours.line.label,
        "our_amount": ours.line.amount,
        "our_decision": ours.decision,
        "rule_id": ours.rule_id,
    }
    if key_row.employee_pretax is None:
        return RowScore(**common, outcome="key_unlabelled")
    if ours.decision is Decision.NEEDS_REVIEW:
        return RowScore(**common, outcome="needs_review")
    we_subtract = ours.decision is Decision.PRETAX
    if we_subtract == key_row.employee_pretax:
        return RowScore(**common, outcome="agree")
    if disputed:
        bucket: Bucket = "known_key_error"
    elif ours.rule_id in _AGREED_RULES:
        bucket = "agreed_rule_disagrees"
    else:
        bucket = "open_question"
    return RowScore(
        **common,
        outcome="disagree",
        direction="we_subtract" if we_subtract else "key_subtracts",
        bucket=bucket,
    )


def _same_amount(ours: Decimal | None, key: Decimal | None) -> bool:
    return ours is not None and key is not None and abs(ours) == abs(key)


def _rows(
    decisions: Sequence[DeductionDecision], key: AnswerKey, disputed: bool
) -> tuple[RowScore, ...]:
    unused = list(range(len(decisions)))
    rows: list[RowScore] = []
    for key_row in key.deductions:
        match = next(
            (
                i
                for i in unused
                if _same_amount(decisions[i].line.amount, key_row.amount)
            ),
            None,
        )
        if match is None:
            rows.append(
                RowScore(
                    key_type=key_row.type,
                    key_amount=key_row.amount,
                    key_pretax=key_row.employee_pretax,
                    outcome="missing",
                    bucket="extraction_problem",
                )
            )
            continue
        unused.remove(match)
        rows.append(_paired(key_row, decisions[match], disputed))
    for i in unused:
        ours = decisions[i]
        excluded = ours.decision is Decision.EXCLUDED
        rows.append(
            RowScore(
                our_label=ours.line.label,
                our_amount=ours.line.amount,
                our_decision=ours.decision,
                rule_id=ours.rule_id,
                outcome="extra_excluded" if excluded else "extra",
                bucket=None if excluded else "extraction_problem",
            )
        )
    return tuple(rows)


def score_outcome(
    outcome: StubOutcome, key: AnswerKey, *, disputed: frozenset[str]
) -> StubScore:
    key_agi = key.calculated.agi
    result = outcome.result
    if result is None:
        return StubScore(
            model=outcome.model,
            stub=outcome.stub,
            status="failed",
            error=outcome.error,
            error_code=outcome.error_code,
            key_agi=key_agi,
        )
    our_agi = result.agi.agi
    difference = None if our_agi is None or key_agi is None else our_agi - key_agi
    return StubScore(
        model=outcome.model,
        stub=outcome.stub,
        status=result.status.value,
        fields=_fields(result, key),
        rows=_rows(result.decisions, key, outcome.stub in disputed),
        our_agi=our_agi,
        key_agi=key_agi,
        agi_match=difference == 0,
        agi_difference=difference,
    )

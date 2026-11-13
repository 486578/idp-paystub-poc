"""Answer keys: loading, and conversion into component inputs for the 7a replay.

`reference_decisions` ports the reference `agi.py` `_is_pretax` exactly, because the
keys' `calculated` block was produced with it. It is NOT the component's rule engine.
"""

from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from paystub_agi.models import (
    AmountLine,
    Decision,
    DeductionLine,
    Money,
    PayFrequency,
    PaystubEvidence,
)

# Copied from the reference agi.py (POSTTAX_EXCLUSIONS); keep in sync.
_POSTTAX_EXCLUSIONS = (
    "roth",
    "life_ins",
    "life_insurance",
    "supplemental",
    "ltd",
    "std",
    "accident",
    "critical",
    "cancer",
    "loan",
    "garnish",
    "child_support",
    "alimony",
    "union_dues",
    "charity",
    "after_tax",
    "aftertax",
    "post_tax",
    "posttax",
    "contr_ins",
    "pension",
    "simple_ira",
    "sgli",
    "usglife",
    "us_glife",
    "fica_medicare",
    "fica_social_security",
    "sdi",
    "stock_cont",
    "stock_purch",
    "stock",
    "co_stk_cnt",
    "aflac",
    "fica",
    "medicare",
    "social_security",
    "pers_pension",
    "pers_ci",
)
_EXPLICIT_POSTTAX = ("post_tax", "posttax", "after_tax", "aftertax")
_EXPLICIT_PRETAX = ("pretax", "pre_tax")
_ONE_TIME = ("bonus", "overtime")


class _Key(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class KeyAmounts(_Key):
    gross: Money = None
    net: Money = None
    total_deductions: Money = None
    taxes: Money = None
    bonus: Money = None
    overtime: Money = None
    commission: Money = None


class KeyDeduction(_Key):
    type: str
    amount: Money
    employee_pretax: bool | None


class KeyPeriod(_Key):
    start_date: date | None = None
    end_date: date | None = None
    pay_date: date | None = None


class KeyCalculated(_Key):
    agi: Money
    annual_gross: Money
    pay_frequency: PayFrequency | None
    periods_per_year: int | None
    frequency_source: str | None
    method: str | None
    one_time_total: Money
    pretax_deductions: Money
    warnings: list[str]


class AnswerKey(_Key):
    schema_version: str
    stub_id: str
    category: str
    amounts: KeyAmounts
    deductions: list[KeyDeduction]
    period: KeyPeriod
    calculated: KeyCalculated


class ReferenceDecision(_Key):
    line: DeductionLine
    decision: Decision


def load_answer_key(path: Path) -> AnswerKey:
    return AnswerKey.model_validate_json(path.read_text(encoding="utf-8"))


def _normalize(text: str) -> str:
    return text.strip().lower().replace(" ", "_").replace("-", "_")


def _reference_is_pretax(deduction: KeyDeduction) -> bool:
    kind = _normalize(deduction.type)
    if any(marker in kind for marker in _EXPLICIT_POSTTAX):
        return False
    if any(marker in kind for marker in _EXPLICIT_PRETAX):
        return True
    if any(pattern in kind for pattern in _POSTTAX_EXCLUSIONS):
        return False
    return deduction.employee_pretax is True


def _line(deduction: KeyDeduction) -> DeductionLine:
    return DeductionLine(
        label=deduction.type,
        amount=deduction.amount,
        section_heading=None,
        codes=(),
        markers=(),
        in_employer_section=False,
        in_brackets=False,
    )


def to_evidence(key: AnswerKey) -> PaystubEvidence:
    earnings = tuple(
        AmountLine(label=kind, amount=getattr(key.amounts, kind), in_brackets=False)
        for kind in _ONE_TIME
        if getattr(key.amounts, kind) is not None
    )
    return PaystubEvidence(
        gross=key.amounts.gross,
        net=key.amounts.net,
        pay_frequency=None,
        period_start=key.period.start_date,
        period_end=key.period.end_date,
        pay_date=key.period.pay_date,
        federal_taxable_wages=None,
        annual_amount=None,
        earnings=earnings,
        taxes=(),
        deductions=tuple(_line(d) for d in key.deductions),
        footnotes=(),
    )


def reference_decisions(key: AnswerKey) -> tuple[ReferenceDecision, ...]:
    return tuple(
        ReferenceDecision(
            line=_line(d),
            decision=Decision.PRETAX
            if _reference_is_pretax(d)
            else Decision.NOT_PRETAX,
        )
        for d in key.deductions
    )

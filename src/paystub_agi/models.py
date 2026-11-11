"""Evidence, decision and result models. All amounts are US dollars as `Decimal`."""

import math
import re
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict

_PLAIN_NUMBER = re.compile(r"-?(\d+(\.\d*)?|\.\d+)")


def _to_money(value: object) -> object:
    if value is None or isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ValueError("amount must be a number, not a boolean")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("amount must be finite")
        # str() gives the shortest repr, so 1224.7 stays 1224.7, not a binary artefact.
        return Decimal(str(value))
    if isinstance(value, str) and _PLAIN_NUMBER.fullmatch(value.strip()):
        return Decimal(value.strip())
    raise ValueError("amount must be a plain number such as 85 or 85.00")


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("text must not be blank")
    return value


# Pydantic itself rejects NaN and infinite Decimals.
Money = Annotated[Decimal | None, BeforeValidator(_to_money)]
Text = Annotated[str, AfterValidator(_not_blank)]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PayFrequency(StrEnum):
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    SEMIMONTHLY = "semimonthly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    ONE_TIME = "one_time"


class Decision(StrEnum):
    PRETAX = "pretax"
    NOT_PRETAX = "not_pretax"
    NEEDS_REVIEW = "needs_review"
    EXCLUDED = "excluded"


class RuleId(StrEnum):
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"
    R5 = "R5"
    R6 = "R6"
    R7 = "R7"
    R8 = "R8"
    R9 = "R9"
    R10 = "R10"


class AmountLine(_Model):
    """A labelled amount copied from the stub (an earning or a tax)."""

    label: Text
    amount: Money


class CodeValue(_Model):
    """A code printed next to a deduction, e.g. column "Type", value "PRE"."""

    column: Text | None
    value: Text


class Footnote(_Model):
    marker: Text
    text: Text


class DeductionLine(_Model):
    """One deduction row as printed. Deliberately has no pre-tax field."""

    label: Text
    amount: Money
    section_heading: Text | None
    codes: tuple[CodeValue, ...]
    markers: tuple[Text, ...]
    in_employer_section: bool


class PaystubEvidence(_Model):
    """Everything the model copied from one paystub, for the current period."""

    gross: Money
    net: Money
    pay_frequency: Text | None
    period_start: date | None
    period_end: date | None
    pay_date: date | None
    federal_taxable_wages: Money
    earnings: tuple[AmountLine, ...]
    taxes: tuple[AmountLine, ...]
    deductions: tuple[DeductionLine, ...]
    footnotes: tuple[Footnote, ...]


class DeductionDecision(_Model):
    """The rule engine's verdict on one deduction, with the rule and quoted evidence."""

    line: DeductionLine
    decision: Decision
    rule_id: RuleId
    evidence: Text


class AgiMethod(StrEnum):
    GROSS_LESS_PRETAX = "gross_less_pretax"
    ONE_TIME_ONLY = "one_time_only"


class FrequencySource(StrEnum):
    DOCUMENT = "document"
    PERIOD_DATES = "period_dates"
    DEFAULT = "default"


class AgiResult(_Model):
    """Annual AGI from one paystub. `agi` is None when it can't be calculated."""

    agi: Money
    # Same formula, but `needs_review` deductions are also subtracted.
    agi_if_review_pretax: Money
    pay_frequency: PayFrequency | None
    frequency_source: FrequencySource | None
    periods_per_year: int | None
    method: AgiMethod | None
    one_time_total: Decimal
    pretax_total: Decimal
    review_total: Decimal
    warnings: tuple[str, ...]

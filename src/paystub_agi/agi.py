"""Annual AGI from one paystub, based on the reference `agi.py`.

AGI = (gross - one_time - pretax) * periods_per_year + one_time, in `Decimal`,
rounded half up to cents once at the end. Departures from the reference follow the
source document (decisionlog DL-025): $0.00 pay is invalid, commission next to other
pay is one-time, and a printed annual amount is the last resort.
"""

import calendar
from collections.abc import Iterable, Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from paystub_agi.config import AgiConfig
from paystub_agi.matching import contains_any
from paystub_agi.models import (
    AgiMethod,
    AgiResult,
    AmountLine,
    Decision,
    DeductionLine,
    FrequencySource,
    PayFrequency,
    PaystubEvidence,
)

_CENT = Decimal("0.01")
_ZERO = Decimal("0")

_FREQUENCY_ALIASES = {
    "weekly": PayFrequency.WEEKLY,
    "biweekly": PayFrequency.BIWEEKLY,
    "semimonthly": PayFrequency.SEMIMONTHLY,
    "monthly": PayFrequency.MONTHLY,
    "quarterly": PayFrequency.QUARTERLY,
    "annual": PayFrequency.ANNUAL,
    "annually": PayFrequency.ANNUAL,
    "yearly": PayFrequency.ANNUAL,
    "onetime": PayFrequency.ONE_TIME,
}

_NO_FREQUENCY = "Pay frequency could not be determined"
_NO_GROSS = "No gross pay"
_ZERO_PAY = "Gross pay or taxable wages are $0.00"
_EXCEEDS = "One-time earnings and pre-tax deductions exceed regular pay"
_EXCEEDS_WAGES = "One-time earnings exceed federal taxable wages"
_WAGES_ABOVE_GROSS = (
    "Federal taxable wages are above gross pay (year-to-date figure?); "
    "used gross instead"
)
_NO_AMOUNT = "A deduction counted for AGI has no amount"


class Classified(Protocol):
    """A deduction with a decision; `DeductionDecision` is the usual one."""

    @property
    def line(self) -> DeductionLine: ...

    @property
    def decision(self) -> Decision: ...


def _cents(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def infer_pay_frequency(start: date | None, end: date | None) -> PayFrequency | None:
    """Infer the frequency from the period length; ambiguous lengths give None."""
    if start is None or end is None:
        return None
    span = (end - start).days + 1
    if 5 <= span <= 8:
        return PayFrequency.WEEKLY
    if 13 <= span <= 16:
        last_day = calendar.monthrange(end.year, end.month)[1]
        if start.day in (1, 16) and end.day in (15, last_day):
            return PayFrequency.SEMIMONTHLY
        return PayFrequency.BIWEEKLY if span <= 15 else None
    if 27 <= span <= 32:
        return PayFrequency.MONTHLY
    if 88 <= span <= 95:
        return PayFrequency.QUARTERLY
    if 360 <= span <= 370:
        return PayFrequency.ANNUAL
    return None


def _printed_or_inferred_frequency(
    evidence: PaystubEvidence,
) -> tuple[PayFrequency, FrequencySource] | None:
    printed = "".join(
        ch for ch in (evidence.pay_frequency or "").lower() if ch.isalnum()
    )
    if printed in _FREQUENCY_ALIASES:
        return _FREQUENCY_ALIASES[printed], FrequencySource.DOCUMENT
    inferred = infer_pay_frequency(evidence.period_start, evidence.period_end)
    if inferred is not None:
        return inferred, FrequencySource.PERIOD_DATES
    return None


def _is_zero(value: Decimal | None) -> bool:
    return value is not None and abs(value) < _CENT


def _one_time_total(earnings: Sequence[AmountLine], config: AgiConfig) -> Decimal:
    commission_once = config.commission_with_other_pay == "one_time" and any(
        line.amount and not contains_any(line.label, config.commission_earnings)
        for line in earnings
    )
    return sum(
        (
            line.amount or _ZERO
            for line in earnings
            if contains_any(line.label, config.one_time_earnings)
            or (
                commission_once and contains_any(line.label, config.commission_earnings)
            )
        ),
        _ZERO,
    )


def _deduction_total(
    decisions: Iterable[Classified], decision: Decision, warnings: list[str]
) -> Decimal:
    total = _ZERO
    for item in decisions:
        if item.decision is not decision:
            continue
        if item.line.amount is None:
            if _NO_AMOUNT not in warnings:
                warnings.append(_NO_AMOUNT)
            continue
        total += abs(item.line.amount)
    return total


def compute_agi(
    evidence: PaystubEvidence, decisions: Iterable[Classified], config: AgiConfig
) -> AgiResult:
    """Calculate annual AGI. Never raises on missing data; explains it in warnings."""
    decided = tuple(decisions)
    one_time = _one_time_total(evidence.earnings, config)
    blank = {
        "agi": None,
        "agi_if_review_pretax": None,
        "pay_frequency": None,
        "frequency_source": None,
        "periods_per_year": None,
        "method": None,
        "one_time_total": _cents(one_time),
        "pretax_total": _cents(_ZERO),
        "review_total": _cents(_ZERO),
        "warnings": (),
    }

    resolved = _printed_or_inferred_frequency(evidence)
    if _is_zero(evidence.gross) or _is_zero(evidence.federal_taxable_wages):
        return AgiResult.model_validate(
            {**blank, "invalid_proof_of_income": True, "warnings": (_ZERO_PAY,)}
        )
    annual = evidence.annual_amount
    no_pay_figure = evidence.gross is None and evidence.federal_taxable_wages is None
    if annual is not None and (resolved is None or no_pay_figure):
        return AgiResult.model_validate(
            {
                **blank,
                "agi": _cents(annual),
                "agi_if_review_pretax": _cents(annual),
                "method": AgiMethod.ANNUAL_AMOUNT,
            }
        )
    if resolved is None and config.default_frequency is not None:
        resolved = config.default_frequency, FrequencySource.DEFAULT
    if resolved is None:
        return AgiResult.model_validate({**blank, "warnings": (_NO_FREQUENCY,)})
    frequency, source = resolved
    periods = config.periods_per_year[frequency]
    known = {
        **blank,
        "pay_frequency": frequency,
        "frequency_source": source,
        "periods_per_year": periods,
    }

    warnings: list[str] = []
    pretax = _deduction_total(decided, Decision.PRETAX, warnings)
    review = _deduction_total(decided, Decision.NEEDS_REVIEW, warnings)

    wages = evidence.federal_taxable_wages
    if wages is not None and evidence.gross is not None and wages > evidence.gross:
        # Impossible for one paycheck; most likely the year-to-date column (DL-030).
        warnings.append(_WAGES_ABOVE_GROSS)
        wages = None
    if wages is not None:
        # Printed taxable wages already reflect pre-tax deductions (DL-024).
        if config.one_time_with_federal_wages == "once":
            agi = (wages - one_time) * periods + one_time
            if wages - one_time < _ZERO:
                warnings.append(_EXCEEDS_WAGES)
        else:
            agi = wages * periods
        return AgiResult.model_validate(
            {
                **known,
                "agi": _cents(agi),
                "agi_if_review_pretax": _cents(agi),
                "method": AgiMethod.FEDERAL_TAXABLE_WAGES,
                "pretax_total": _cents(pretax),
                "review_total": _cents(review),
                "warnings": tuple(warnings),
            }
        )

    gross = evidence.gross
    if gross is None:
        return AgiResult.model_validate({**known, "warnings": (_NO_GROSS,)})
    agi = (gross - one_time - pretax) * periods + one_time
    if agi - one_time < _ZERO:
        warnings.append(_EXCEEDS)
    return AgiResult.model_validate(
        {
            **known,
            "agi": _cents(agi),
            "agi_if_review_pretax": _cents(
                (gross - one_time - pretax - review) * periods + one_time
            ),
            "method": AgiMethod.GROSS_LESS_PRETAX,
            "pretax_total": _cents(pretax),
            "review_total": _cents(review),
            "warnings": tuple(warnings),
        }
    )

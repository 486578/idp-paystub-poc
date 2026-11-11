from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from paystub_agi.agi import compute_agi, infer_pay_frequency
from paystub_agi.config import AgiConfig
from paystub_agi.models import (
    AgiMethod,
    AmountLine,
    Decision,
    DeductionDecision,
    DeductionLine,
    FrequencySource,
    PayFrequency,
    PaystubEvidence,
    RuleId,
)

BIWEEKLY_START = date(2026, 7, 1)
BIWEEKLY_END = date(2026, 7, 14)


def _evidence(**overrides: Any) -> PaystubEvidence:
    values: dict[str, Any] = {
        "gross": Decimal("1760"),
        "net": None,
        "pay_frequency": None,
        "period_start": BIWEEKLY_START,
        "period_end": BIWEEKLY_END,
        "pay_date": None,
        "federal_taxable_wages": None,
        "earnings": (),
        "taxes": (),
        "deductions": (),
        "footnotes": (),
    }
    values.update(overrides)
    return PaystubEvidence.model_validate(values)


def _decided(label: str, amount: str | None, decision: Decision) -> DeductionDecision:
    line = DeductionLine(
        label=label,
        amount=None if amount is None else Decimal(amount),
        section_heading=None,
        codes=(),
        markers=(),
        in_employer_section=False,
    )
    return DeductionDecision(
        line=line, decision=decision, rule_id=RuleId.R9, evidence=label
    )


def _earning(label: str, amount: str | None) -> AmountLine:
    return AmountLine(label=label, amount=None if amount is None else Decimal(amount))


# --- pay frequency from period dates (ported from the reference) ------------------


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (date(2026, 7, 1), date(2026, 7, 7), PayFrequency.WEEKLY),
        (date(2026, 7, 1), date(2026, 7, 5), PayFrequency.WEEKLY),
        (date(2026, 7, 1), date(2026, 7, 8), PayFrequency.WEEKLY),
        (date(2026, 7, 1), date(2026, 7, 4), None),
        (date(2026, 7, 1), date(2026, 7, 9), None),
        (date(2026, 7, 2), date(2026, 7, 15), PayFrequency.BIWEEKLY),
        (date(2026, 7, 2), date(2026, 7, 14), PayFrequency.BIWEEKLY),
        (date(2026, 7, 1), date(2026, 7, 15), PayFrequency.SEMIMONTHLY),
        (date(2026, 7, 16), date(2026, 7, 31), PayFrequency.SEMIMONTHLY),
        (date(2026, 2, 16), date(2026, 2, 28), PayFrequency.SEMIMONTHLY),
        (date(2026, 7, 16), date(2026, 7, 30), PayFrequency.BIWEEKLY),
        (date(2026, 7, 2), date(2026, 7, 17), None),
        (date(2026, 7, 1), date(2026, 7, 28), PayFrequency.MONTHLY),
        (date(2026, 7, 1), date(2026, 7, 27), PayFrequency.MONTHLY),
        (date(2026, 7, 1), date(2026, 8, 1), PayFrequency.MONTHLY),
        (date(2026, 7, 1), date(2026, 8, 2), None),
        (date(2026, 7, 1), date(2026, 9, 28), PayFrequency.QUARTERLY),
        (date(2026, 1, 1), date(2026, 12, 31), PayFrequency.ANNUAL),
        (date(2026, 7, 14), date(2026, 7, 1), None),
    ],
)
def test_agi_infer_pay_frequency_from_period_length(
    start: date, end: date, expected: PayFrequency | None
) -> None:
    assert infer_pay_frequency(start, end) is expected


@pytest.mark.parametrize(
    ("start", "end"), [(None, BIWEEKLY_END), (BIWEEKLY_START, None), (None, None)]
)
def test_agi_infer_pay_frequency_missing_date_is_none(
    start: date | None, end: date | None
) -> None:
    assert infer_pay_frequency(start, end) is None


# --- choosing the frequency ---------------------------------------------------------


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        ("Bi-Weekly", PayFrequency.BIWEEKLY),
        ("SEMI MONTHLY", PayFrequency.SEMIMONTHLY),
        ("Weekly", PayFrequency.WEEKLY),
        ("monthly", PayFrequency.MONTHLY),
        ("Quarterly", PayFrequency.QUARTERLY),
        ("Annually", PayFrequency.ANNUAL),
        ("yearly", PayFrequency.ANNUAL),
        ("Annual", PayFrequency.ANNUAL),
        ("One-Time", PayFrequency.ONE_TIME),
    ],
)
def test_agi_printed_frequency_wins_over_period_dates(
    printed: str, expected: PayFrequency
) -> None:
    result = compute_agi(_evidence(pay_frequency=printed), (), AgiConfig())

    assert result.pay_frequency is expected
    assert result.frequency_source is FrequencySource.DOCUMENT


def test_agi_unknown_printed_frequency_falls_back_to_dates() -> None:
    result = compute_agi(_evidence(pay_frequency="Fortnightly"), (), AgiConfig())

    assert result.pay_frequency is PayFrequency.BIWEEKLY
    assert result.frequency_source is FrequencySource.PERIOD_DATES


def test_agi_uses_configured_default_frequency_last() -> None:
    config = AgiConfig(default_frequency=PayFrequency.MONTHLY)

    result = compute_agi(_evidence(period_start=None), (), config)

    assert result.pay_frequency is PayFrequency.MONTHLY
    assert result.frequency_source is FrequencySource.DEFAULT
    assert result.agi == Decimal("21120.00")


def test_agi_without_any_frequency_is_none_with_warning() -> None:
    result = compute_agi(_evidence(period_start=None), (), AgiConfig())

    assert result.agi is None
    assert result.agi_if_review_pretax is None
    assert result.pay_frequency is None
    assert result.periods_per_year is None
    assert result.warnings == ("Pay frequency could not be determined",)


def test_agi_uses_periods_from_config() -> None:
    periods = dict(AgiConfig().periods_per_year)
    periods[PayFrequency.BIWEEKLY] = 27

    result = compute_agi(_evidence(), (), AgiConfig(periods_per_year=periods))

    assert result.periods_per_year == 27
    assert result.agi == Decimal("47520.00")


# --- the formula -----------------------------------------------------------------------


def test_agi_stub_0006_with_nothing_pretax() -> None:
    decisions = (
        _decided("Medical", "85.00", Decision.NOT_PRETAX),
        _decided("Dental", "12.00", Decision.NOT_PRETAX),
        _decided("401k", "70.40", Decision.NOT_PRETAX),
    )

    result = compute_agi(_evidence(), decisions, AgiConfig())

    assert result.agi == Decimal("45760.00")
    assert result.method is AgiMethod.GROSS_LESS_PRETAX
    assert result.periods_per_year == 26
    assert result.pretax_total == Decimal("0.00")
    assert result.warnings == ()


def test_agi_stub_0006_with_all_three_pretax() -> None:
    decisions = (
        _decided("Medical", "85.00", Decision.PRETAX),
        _decided("Dental", "12.00", Decision.PRETAX),
        _decided("401k", "70.40", Decision.PRETAX),
    )

    result = compute_agi(_evidence(), decisions, AgiConfig())

    assert result.agi == Decimal("41407.60")
    assert result.pretax_total == Decimal("167.40")


def test_agi_needs_review_rows_give_a_range() -> None:
    decisions = (
        _decided("Medical", "85.00", Decision.NEEDS_REVIEW),
        _decided("Dental", "12.00", Decision.NEEDS_REVIEW),
        _decided("401k", "70.40", Decision.NEEDS_REVIEW),
    )

    result = compute_agi(_evidence(), decisions, AgiConfig())

    assert result.agi == Decimal("45760.00")
    assert result.agi_if_review_pretax == Decimal("41407.60")
    assert result.review_total == Decimal("167.40")


def test_agi_without_review_rows_range_collapses() -> None:
    result = compute_agi(_evidence(), (), AgiConfig())

    assert result.agi_if_review_pretax == result.agi


def test_agi_excluded_rows_are_never_subtracted() -> None:
    decisions = (_decided("Pension ER", "88.00", Decision.EXCLUDED),)

    result = compute_agi(_evidence(), decisions, AgiConfig())

    assert result.agi == Decimal("45760.00")
    assert result.agi_if_review_pretax == Decimal("45760.00")


def test_agi_negative_deduction_amount_is_subtracted_as_positive() -> None:
    evidence = _evidence(gross=Decimal("1052.70"))
    decisions = (_decided("Health", "-87.00", Decision.PRETAX),)

    result = compute_agi(evidence, decisions, AgiConfig())

    assert result.agi == Decimal("25108.20")


def test_agi_pretax_row_without_amount_is_skipped_with_warning() -> None:
    decisions = (_decided("Uniform", None, Decision.PRETAX),)

    result = compute_agi(_evidence(), decisions, AgiConfig())

    assert result.agi == Decimal("45760.00")
    assert result.warnings == ("A deduction counted for AGI has no amount",)


def test_agi_review_row_without_amount_is_skipped_with_warning() -> None:
    decisions = (_decided("Uniform", None, Decision.NEEDS_REVIEW),)

    result = compute_agi(_evidence(), decisions, AgiConfig())

    assert result.agi_if_review_pretax == Decimal("45760.00")
    assert result.warnings == ("A deduction counted for AGI has no amount",)


def test_agi_missing_amount_on_not_pretax_row_is_not_warned() -> None:
    decisions = (_decided("Misc", None, Decision.NOT_PRETAX),)

    assert compute_agi(_evidence(), decisions, AgiConfig()).warnings == ()


def test_agi_missing_amount_warning_is_given_once() -> None:
    decisions = (
        _decided("Uniform", None, Decision.PRETAX),
        _decided("Meals", None, Decision.PRETAX),
        _decided("Misc", None, Decision.NEEDS_REVIEW),
    )

    result = compute_agi(_evidence(), decisions, AgiConfig())

    assert result.warnings == ("A deduction counted for AGI has no amount",)


# --- one-time pay ------------------------------------------------------------------


def test_agi_bonus_and_overtime_are_added_once() -> None:
    evidence = _evidence(
        gross=Decimal("2000"),
        earnings=(
            _earning("Regular", "1300"),
            _earning("Overtime 1.5x", "200"),
            _earning("Bonus Pay", "500"),
        ),
    )

    result = compute_agi(evidence, (), AgiConfig())

    assert result.one_time_total == Decimal("700.00")
    assert result.agi == Decimal("34500.00")


def test_agi_one_time_needs_whole_word_match() -> None:
    evidence = _evidence(earnings=(_earning("Bonusable Hours", "100"),))

    assert compute_agi(evidence, (), AgiConfig()).one_time_total == Decimal("0.00")


def test_agi_one_time_earnings_come_from_config() -> None:
    evidence = _evidence(
        gross=Decimal("2000"),
        earnings=(_earning("Commission", "500"), _earning("Bonus", "100")),
    )
    config = AgiConfig(one_time_earnings=("commission",))

    result = compute_agi(evidence, (), config)

    assert result.one_time_total == Decimal("500.00")
    assert result.agi == Decimal("39500.00")


def test_agi_one_time_earning_without_amount_counts_zero() -> None:
    evidence = _evidence(earnings=(_earning("Bonus", None),))

    assert compute_agi(evidence, (), AgiConfig()).one_time_total == Decimal("0.00")


def test_agi_warns_when_one_time_and_pretax_exceed_regular_pay() -> None:
    evidence = _evidence(gross=Decimal("100"), earnings=(_earning("Bonus", "80"),))
    decisions = (_decided("401k", "50", Decision.PRETAX),)

    result = compute_agi(evidence, decisions, AgiConfig())

    assert result.agi == Decimal("-700.00")
    assert result.warnings == (
        "One-time earnings and pre-tax deductions exceed regular pay",
    )


# --- no regular pay -------------------------------------------------------------------


def test_agi_without_gross_is_none_with_warning() -> None:
    result = compute_agi(_evidence(gross=None), (), AgiConfig())

    assert result.agi is None
    assert result.periods_per_year == 26
    assert result.warnings == ("No gross pay",)


@pytest.mark.parametrize("gross", ["0", "0.004"])
def test_agi_no_regular_pay_with_bonus_is_one_time_only(gross: str) -> None:
    evidence = _evidence(gross=Decimal(gross), earnings=(_earning("Bonus", "500"),))
    decisions = (_decided("401k", "50", Decision.PRETAX),)

    result = compute_agi(evidence, decisions, AgiConfig())

    assert result.method is AgiMethod.ONE_TIME_ONLY
    assert result.agi == Decimal("500.00")
    assert result.agi_if_review_pretax == Decimal("500.00")
    assert result.pretax_total == Decimal("0.00")


def test_agi_no_regular_pay_and_no_one_time_is_none_with_warning() -> None:
    result = compute_agi(_evidence(gross=Decimal("0")), (), AgiConfig())

    assert result.agi is None
    assert result.warnings == ("No regular pay and no one-time earnings",)


# --- rounding -------------------------------------------------------------------------


def test_agi_rounds_half_up_once_at_the_end() -> None:
    evidence = _evidence(gross=Decimal("0.125"), pay_frequency="annual")

    result = compute_agi(evidence, (), AgiConfig())

    assert result.agi == Decimal("0.13")


def test_agi_does_not_round_before_multiplying() -> None:
    evidence = _evidence(gross=Decimal("1000.004"), pay_frequency="weekly")

    result = compute_agi(evidence, (), AgiConfig())

    assert result.agi == Decimal("52000.21")

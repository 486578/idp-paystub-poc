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
        "annual_amount": None,
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
        in_brackets=False,
    )
    return DeductionDecision(
        line=line, decision=decision, rule_id=RuleId.R9, evidence=label
    )


def _earning(label: str, amount: str | None) -> AmountLine:
    return AmountLine(
        label=label,
        amount=None if amount is None else Decimal(amount),
        in_brackets=False,
    )


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


# --- commission (source doc: alone = regular pay; with other pay = bonus column) -----


def test_agi_commission_with_other_pay_counts_once_by_default() -> None:
    evidence = _evidence(
        gross=Decimal("2000"),
        earnings=(_earning("Regular", "1500"), _earning("Commission", "500")),
    )

    result = compute_agi(evidence, (), AgiConfig())

    assert result.one_time_total == Decimal("500.00")
    assert result.agi == Decimal("39500.00")


def test_agi_commission_alone_is_regular_pay() -> None:
    evidence = _evidence(
        gross=Decimal("2000"), earnings=(_earning("Commission", "2000"),)
    )

    result = compute_agi(evidence, (), AgiConfig())

    assert result.one_time_total == Decimal("0.00")
    assert result.agi == Decimal("52000.00")


def test_agi_commission_next_to_zero_pay_line_is_alone() -> None:
    evidence = _evidence(
        gross=Decimal("2000"),
        earnings=(_earning("Regular", "0.00"), _earning("Commission", "2000")),
    )

    assert compute_agi(evidence, (), AgiConfig()).one_time_total == Decimal("0.00")


def test_agi_commission_can_be_configured_as_regular_pay() -> None:
    evidence = _evidence(
        gross=Decimal("2000"),
        earnings=(_earning("Regular", "1500"), _earning("Commission", "500")),
    )
    config = AgiConfig(commission_with_other_pay="regular")

    assert compute_agi(evidence, (), config).agi == Decimal("52000.00")


def test_agi_commission_labels_come_from_config() -> None:
    evidence = _evidence(
        gross=Decimal("2000"),
        earnings=(_earning("Regular", "1500"), _earning("Comm Pay", "500")),
    )
    config = AgiConfig(commission_earnings=("comm",))

    assert compute_agi(evidence, (), config).one_time_total == Decimal("500.00")


def test_agi_commission_listed_as_one_time_is_not_counted_twice() -> None:
    evidence = _evidence(
        gross=Decimal("2000"),
        earnings=(_earning("Regular", "1500"), _earning("Commission", "500")),
    )
    config = AgiConfig(one_time_earnings=("commission",))

    assert compute_agi(evidence, (), config).one_time_total == Decimal("500.00")


# --- invalid proof of income (source doc: $0.00 gross or taxable wages) -----------


@pytest.mark.parametrize("gross", ["0", "0.00", "0.004"])
def test_agi_zero_gross_is_invalid_proof_of_income(gross: str) -> None:
    evidence = _evidence(gross=Decimal(gross), earnings=(_earning("Bonus", "500"),))

    result = compute_agi(evidence, (), AgiConfig())

    assert result.invalid_proof_of_income is True
    assert result.agi is None
    assert result.agi_if_review_pretax is None
    assert result.method is None
    assert result.warnings == ("Gross pay or taxable wages are $0.00",)


def test_agi_zero_federal_taxable_wages_is_invalid_proof_of_income() -> None:
    evidence = _evidence(federal_taxable_wages=Decimal("0.00"))

    result = compute_agi(evidence, (), AgiConfig())

    assert result.invalid_proof_of_income is True
    assert result.agi is None


def test_agi_zero_is_invalid_even_without_a_frequency() -> None:
    result = compute_agi(
        _evidence(gross=Decimal("0"), period_start=None), (), AgiConfig()
    )

    assert result.warnings == ("Gross pay or taxable wages are $0.00",)


def test_agi_valid_stub_is_not_marked_invalid() -> None:
    assert compute_agi(_evidence(), (), AgiConfig()).invalid_proof_of_income is False


# --- federal taxable wages (business answer + source doc: use them when printed) -----


def test_agi_uses_printed_federal_taxable_wages() -> None:
    evidence = _evidence(federal_taxable_wages=Decimal("1592.60"))

    result = compute_agi(evidence, (), AgiConfig())

    assert result.agi == Decimal("41407.60")
    assert result.method is AgiMethod.FEDERAL_TAXABLE_WAGES


def test_agi_federal_wages_ignore_deduction_decisions() -> None:
    evidence = _evidence(federal_taxable_wages=Decimal("1592.60"))
    decisions = (
        _decided("401k", "100.00", Decision.PRETAX),
        _decided("Medical", "85.00", Decision.NEEDS_REVIEW),
    )

    result = compute_agi(evidence, decisions, AgiConfig())

    assert result.agi == Decimal("41407.60")
    assert result.agi_if_review_pretax == Decimal("41407.60")


def test_agi_federal_wages_count_bonus_once_by_default() -> None:
    evidence = _evidence(
        gross=Decimal("2000"),
        federal_taxable_wages=Decimal("1800"),
        earnings=(_earning("Regular", "1500"), _earning("Bonus", "500")),
    )

    assert compute_agi(evidence, (), AgiConfig()).agi == Decimal("34300.00")


def test_agi_federal_wages_can_annualise_one_time_pay() -> None:
    evidence = _evidence(
        gross=Decimal("2000"),
        federal_taxable_wages=Decimal("1800"),
        earnings=(_earning("Regular", "1500"), _earning("Bonus", "500")),
    )
    config = AgiConfig(one_time_with_federal_wages="annualise")

    assert compute_agi(evidence, (), config).agi == Decimal("46800.00")


def test_agi_federal_wages_above_gross_fall_back_to_gross() -> None:
    evidence = _evidence(
        gross=Decimal("1052.70"), federal_taxable_wages=Decimal("13519.80")
    )
    decisions = (_decided("Health", "87.00", Decision.PRETAX),)

    result = compute_agi(evidence, decisions, AgiConfig())

    assert result.agi == Decimal("25108.20")
    assert result.method is AgiMethod.GROSS_LESS_PRETAX
    assert result.warnings == (
        "Federal taxable wages are above gross pay (year-to-date figure?); "
        "used gross instead",
    )


def test_agi_federal_wages_equal_to_gross_are_used() -> None:
    evidence = _evidence(federal_taxable_wages=Decimal("1760"))

    result = compute_agi(evidence, (), AgiConfig())

    assert (result.agi, result.method) == (
        Decimal("45760.00"),
        AgiMethod.FEDERAL_TAXABLE_WAGES,
    )


def test_agi_federal_wages_used_when_gross_is_missing() -> None:
    evidence = _evidence(gross=None, federal_taxable_wages=Decimal("1592.60"))

    result = compute_agi(evidence, (), AgiConfig())

    assert (result.agi, result.method) == (
        Decimal("41407.60"),
        AgiMethod.FEDERAL_TAXABLE_WAGES,
    )


def test_agi_federal_wages_without_frequency_fall_back_to_annual_amount() -> None:
    evidence = _evidence(
        period_start=None,
        federal_taxable_wages=Decimal("1592.60"),
        annual_amount=Decimal("45760"),
    )

    assert compute_agi(evidence, (), AgiConfig()).method is AgiMethod.ANNUAL_AMOUNT


def test_agi_federal_wages_without_frequency_or_annual_amount_is_none() -> None:
    evidence = _evidence(period_start=None, federal_taxable_wages=Decimal("1592.60"))

    result = compute_agi(evidence, (), AgiConfig())

    assert result.agi is None
    assert result.warnings == ("Pay frequency could not be determined",)


def test_agi_federal_wages_below_one_time_pay_warns() -> None:
    evidence = _evidence(
        federal_taxable_wages=Decimal("400"), earnings=(_earning("Bonus", "500"),)
    )

    result = compute_agi(evidence, (), AgiConfig())

    assert result.agi == Decimal("-2100.00")
    assert result.warnings == ("One-time earnings exceed federal taxable wages",)


# --- printed annual amount (source doc: last resort) --------------------------------


def test_agi_annual_amount_used_when_frequency_unknown() -> None:
    evidence = _evidence(period_start=None, annual_amount=Decimal("45760"))

    result = compute_agi(evidence, (), AgiConfig())

    assert result.agi == Decimal("45760.00")
    assert result.agi_if_review_pretax == Decimal("45760.00")
    assert result.method is AgiMethod.ANNUAL_AMOUNT
    assert result.pay_frequency is None
    assert result.warnings == ()


def test_agi_annual_amount_used_when_gross_missing() -> None:
    evidence = _evidence(gross=None, annual_amount=Decimal("45760"))

    result = compute_agi(evidence, (), AgiConfig())

    assert (result.agi, result.method) == (
        Decimal("45760.00"),
        AgiMethod.ANNUAL_AMOUNT,
    )


def test_agi_annual_amount_beats_configured_default_frequency() -> None:
    evidence = _evidence(period_start=None, annual_amount=Decimal("45760"))
    config = AgiConfig(default_frequency=PayFrequency.MONTHLY)

    assert compute_agi(evidence, (), config).method is AgiMethod.ANNUAL_AMOUNT


def test_agi_annual_amount_ignored_when_gross_and_frequency_known() -> None:
    evidence = _evidence(annual_amount=Decimal("99999"))

    result = compute_agi(evidence, (), AgiConfig())

    assert (result.agi, result.method) == (
        Decimal("45760.00"),
        AgiMethod.GROSS_LESS_PRETAX,
    )


# --- no regular pay -------------------------------------------------------------------


def test_agi_without_gross_is_none_with_warning() -> None:
    result = compute_agi(_evidence(gross=None), (), AgiConfig())

    assert result.agi is None
    assert result.periods_per_year == 26
    assert result.warnings == ("No gross pay",)


# --- rounding -------------------------------------------------------------------------


def test_agi_rounds_half_up_once_at_the_end() -> None:
    evidence = _evidence(gross=Decimal("0.125"), pay_frequency="annual")

    result = compute_agi(evidence, (), AgiConfig())

    assert result.agi == Decimal("0.13")


def test_agi_does_not_round_before_multiplying() -> None:
    evidence = _evidence(gross=Decimal("1000.004"), pay_frequency="weekly")

    result = compute_agi(evidence, (), AgiConfig())

    assert result.agi == Decimal("52000.21")

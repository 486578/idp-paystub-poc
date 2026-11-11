from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from paystub_agi.models import (
    AmountLine,
    CheckCode,
    CheckFlag,
    CheckName,
    CheckReport,
    CodeValue,
    Decision,
    DeductionDecision,
    DeductionLine,
    Footnote,
    PayFrequency,
    PaystubEvidence,
    RuleId,
)


def _deduction(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "label": "Medical",
        "amount": 85,
        "section_heading": "Deductions",
        "codes": [],
        "markers": [],
        "in_employer_section": False,
    }
    values.update(overrides)
    return values


def _evidence(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "gross": 1760,
        "net": 1224.7,
        "pay_frequency": None,
        "period_start": "2026-07-01",
        "period_end": "2026-07-14",
        "pay_date": "2026-07-17",
        "federal_taxable_wages": None,
        "earnings": [{"label": "Regular", "amount": 1760}],
        "taxes": [{"label": "Social Security", "amount": 109.12}],
        "deductions": [_deduction()],
        "footnotes": [],
    }
    values.update(overrides)
    return values


# --- amounts -------------------------------------------------------------------


def test_models_amount_from_int_is_decimal() -> None:
    line = AmountLine(label="Regular", amount=1760)

    assert line.amount == Decimal("1760")
    assert isinstance(line.amount, Decimal)


def test_models_amount_from_float_keeps_printed_digits() -> None:
    line = AmountLine(label="Net", amount=1224.7)

    assert str(line.amount) == "1224.7"


def test_models_amount_from_float_noise_is_not_rounded() -> None:
    line = AmountLine(label="Noise", amount=0.1 + 0.2)

    assert line.amount == Decimal("0.30000000000000004")


def test_models_amount_from_numeric_string_is_decimal() -> None:
    line = AmountLine(label="Medical", amount="85.00")

    assert str(line.amount) == "85.00"


def test_models_amount_negative_is_kept() -> None:
    line = AmountLine(label="Health", amount=-87)

    assert line.amount == Decimal("-87")


def test_models_amount_none_is_allowed() -> None:
    line = AmountLine(label="Uniform", amount=None)

    assert line.amount is None


@pytest.mark.parametrize(
    "bad",
    ["N/A", "", "  ", "$85.00", "1,234.56", "(85.00)", True, False, "NaN", "Infinity"],
)
def test_models_amount_non_numeric_is_rejected(bad: object) -> None:
    with pytest.raises(ValidationError):
        AmountLine(label="Bad", amount=bad)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_models_amount_non_finite_float_is_rejected(bad: float) -> None:
    with pytest.raises(ValidationError):
        AmountLine(label="Bad", amount=bad)


def test_models_amount_decimal_is_kept_as_is() -> None:
    line = AmountLine(label="Medical", amount=Decimal("85.00"))

    assert str(line.amount) == "85.00"


@pytest.mark.parametrize("bad", [Decimal("NaN"), Decimal("Infinity")])
def test_models_amount_non_finite_decimal_is_rejected(bad: Decimal) -> None:
    with pytest.raises(ValidationError):
        AmountLine(label="Bad", amount=bad)


@pytest.mark.parametrize("bad", [[85], {"value": 85}])
def test_models_amount_container_is_rejected(bad: object) -> None:
    with pytest.raises(ValidationError):
        AmountLine(label="Bad", amount=bad)


# --- deduction lines -------------------------------------------------------------


def test_models_deduction_keeps_verbatim_evidence() -> None:
    line = DeductionLine.model_validate(
        _deduction(
            label="DENTAL EE/SPOUSE",
            section_heading="Payroll Deductions",
            codes=[{"column": "Type", "value": "PRE"}],
            markers=["*"],
        )
    )

    assert line.label == "DENTAL EE/SPOUSE"
    assert line.section_heading == "Payroll Deductions"
    assert line.codes == (CodeValue(column="Type", value="PRE"),)
    assert line.markers == ("*",)


def test_models_deduction_without_employer_flag_is_rejected() -> None:
    values = _deduction()
    del values["in_employer_section"]

    with pytest.raises(ValidationError):
        DeductionLine.model_validate(values)


def test_models_deduction_with_empty_label_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DeductionLine.model_validate(_deduction(label="  "))


def test_models_deduction_has_no_pretax_field() -> None:
    # The model must never be able to state pre-tax status.
    assert not any("pretax" in name for name in DeductionLine.model_fields)
    with pytest.raises(ValidationError):
        DeductionLine.model_validate(_deduction(employee_pretax=True))


def test_models_code_value_column_may_be_unknown() -> None:
    assert CodeValue(column=None, value="EE").column is None


# --- paystub evidence --------------------------------------------------------------


def test_models_evidence_parses_full_record() -> None:
    evidence = PaystubEvidence.model_validate(
        _evidence(
            footnotes=[{"marker": "*", "text": "Excluded from federal taxable wages"}]
        )
    )

    assert evidence.gross == Decimal("1760")
    assert evidence.period_start == date(2026, 7, 1)
    assert evidence.deductions[0].label == "Medical"
    assert evidence.footnotes == (
        Footnote(marker="*", text="Excluded from federal taxable wages"),
    )


def test_models_evidence_missing_optional_values_stay_none() -> None:
    evidence = PaystubEvidence.model_validate(
        _evidence(gross=None, period_start=None, period_end=None, pay_date=None)
    )

    assert evidence.gross is None
    assert evidence.period_start is None


def test_models_evidence_non_iso_date_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PaystubEvidence.model_validate(_evidence(period_start="07/01/2026"))


def test_models_evidence_extra_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PaystubEvidence.model_validate(_evidence(agi=45760))


def test_models_evidence_missing_required_list_is_rejected() -> None:
    values = _evidence()
    del values["deductions"]

    with pytest.raises(ValidationError):
        PaystubEvidence.model_validate(values)


def test_models_evidence_empty_lists_are_allowed() -> None:
    evidence = PaystubEvidence.model_validate(
        _evidence(earnings=[], taxes=[], deductions=[], footnotes=[])
    )

    assert evidence.deductions == ()


def test_models_evidence_is_frozen() -> None:
    evidence = PaystubEvidence.model_validate(_evidence())

    with pytest.raises(ValidationError):
        evidence.gross = Decimal("1")  # type: ignore[misc]


def test_models_evidence_round_trips_through_json() -> None:
    evidence = PaystubEvidence.model_validate(_evidence())

    again = PaystubEvidence.model_validate_json(evidence.model_dump_json())

    assert again == evidence


# --- decisions ---------------------------------------------------------------------


def test_models_decision_values_are_stable_strings() -> None:
    assert {d.value for d in Decision} == {
        "pretax",
        "not_pretax",
        "needs_review",
        "excluded",
    }


def test_models_rule_ids_are_r1_to_r10() -> None:
    assert [r.value for r in RuleId] == [f"R{i}" for i in range(1, 11)]


def test_models_pay_frequencies_match_reference() -> None:
    assert {f.value for f in PayFrequency} == {
        "weekly",
        "biweekly",
        "semimonthly",
        "monthly",
        "quarterly",
        "annual",
        "one_time",
    }


def test_models_deduction_decision_requires_evidence_text() -> None:
    line = DeductionLine.model_validate(_deduction())

    with pytest.raises(ValidationError):
        DeductionDecision(
            line=line, decision=Decision.PRETAX, rule_id=RuleId.R4, evidence=""
        )


def test_models_deduction_decision_keeps_rule_and_evidence() -> None:
    line = DeductionLine.model_validate(_deduction())

    decided = DeductionDecision(
        line=line,
        decision=Decision.NEEDS_REVIEW,
        rule_id=RuleId.R9,
        evidence="Medical",
    )

    assert decided.rule_id is RuleId.R9
    assert decided.evidence == "Medical"
    assert decided.escalated_from is None
    assert decided.escalated_by is None


# --- checks ------------------------------------------------------------------------


def test_models_check_flag_defaults_to_stub_level_without_review() -> None:
    flag = CheckFlag(code=CheckCode.NET_MISMATCH, message="net differs")

    assert flag.deduction_index is None
    assert flag.send_to_review is False


def test_models_check_flag_rejects_negative_row_index() -> None:
    with pytest.raises(ValidationError):
        CheckFlag(code=CheckCode.NET_MISMATCH, message="x", deduction_index=-1)


def test_models_check_report_holds_flags_and_checks_not_run() -> None:
    report = CheckReport(
        flags=(CheckFlag(code=CheckCode.NET_MISMATCH, message="net differs"),),
        not_run=(CheckName.GROUNDING,),
    )

    assert report.not_run == (CheckName.GROUNDING,)

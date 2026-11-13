"""Consistency checks (architecture section 5, step 4).

Checks never change extracted values. They return flags; flags marked
`send_to_review` move that deduction's decision to `needs_review` through
`apply_review` (decisionlog DL-018), or, without a row, send the whole stub to
review. Each check is a small object, so a new check is a new class added to the list.
"""

import re
from collections.abc import Iterator, Sequence
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from paystub_agi.config import ChecksConfig
from paystub_agi.errors import InputMismatchError
from paystub_agi.matching import contains_any, tokens
from paystub_agi.models import (
    AmountLine,
    CheckCode,
    CheckFlag,
    CheckName,
    CheckReport,
    Decision,
    DeductionDecision,
    DeductionLine,
    PaystubEvidence,
    RuleId,
)

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?|\.\d+")
# Decisions based on the weakest evidence; checks may send these to review.
_WEAK_RULES = (RuleId.R9, RuleId.R10)
_ZERO = Decimal("0")


class CheckContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence: PaystubEvidence
    decisions: tuple[DeductionDecision, ...]
    document_text: str | None
    config: ChecksConfig


class Check(Protocol):
    @property
    def name(self) -> CheckName: ...

    def run(self, context: CheckContext) -> tuple[CheckFlag, ...] | None:
        """Return flags, or None when the check can't run on this stub."""
        ...


def _amounts_in(text: str) -> set[Decimal]:
    return {Decimal(match.replace(",", "")) for match in _NUMBER.findall(text)}


def _row_flags(
    code: CheckCode, message: str, rows: Iterator[int], send_to_review: bool
) -> tuple[CheckFlag, ...]:
    return tuple(
        CheckFlag(
            code=code,
            message=message,
            deduction_index=i,
            send_to_review=send_to_review,
        )
        for i in rows
    )


class GroundingCheck:
    """Every amount and every piece of text the rules use must appear in the OCR."""

    name = CheckName.GROUNDING

    def run(self, context: CheckContext) -> tuple[CheckFlag, ...] | None:
        if context.document_text is None:
            return None
        numbers = _amounts_in(context.document_text)
        words = set(tokens(context.document_text))
        evidence = context.evidence
        flags: list[CheckFlag] = []

        def amount(value: Decimal | None, what: str, row: int | None = None) -> None:
            if value is not None and abs(value) not in numbers:
                flags.append(
                    CheckFlag(
                        code=CheckCode.AMOUNT_NOT_IN_DOCUMENT,
                        message=f"{what} amount not found in document",
                        deduction_index=row,
                    )
                )

        def text(value: str | None, what: str, row: int | None = None) -> None:
            if value is not None and not set(tokens(value)) <= words:
                flags.append(
                    CheckFlag(
                        code=CheckCode.TEXT_NOT_IN_DOCUMENT,
                        message=f"{what} text not found in document",
                        deduction_index=row,
                    )
                )

        def lines(items: Sequence[AmountLine], what: str) -> None:
            for i, line in enumerate(items):
                text(line.label, f"{what}[{i}] label")
                amount(line.amount, f"{what}[{i}]")

        amount(evidence.gross, "gross")
        amount(evidence.net, "net")
        amount(evidence.federal_taxable_wages, "federal_taxable_wages")
        amount(evidence.annual_amount, "annual_amount")
        lines(evidence.earnings, "earnings")
        lines(evidence.taxes, "taxes")
        for i, row in enumerate(evidence.deductions):
            text(row.label, "deduction label", i)
            text(row.section_heading, "deduction section heading", i)
            for code in row.codes:
                text(code.column, "deduction code column", i)
                text(code.value, "deduction code", i)
            amount(row.amount, "deduction", i)
        for i, note in enumerate(evidence.footnotes):
            text(note.text, f"footnotes[{i}]")
        return tuple(flags)


class NetCheck:
    """gross - taxes - employee deductions should equal the printed net pay."""

    name = CheckName.NET

    def run(self, context: CheckContext) -> tuple[CheckFlag, ...] | None:
        evidence = context.evidence
        # Employer rows (R1, or EMP read as employer) never came out of the pay.
        paid = [
            d.line.amount
            for d in context.decisions
            if not (d.decision is Decision.EXCLUDED and d.rule_id is not RuleId.R2)
        ]
        taxes = [t.amount for t in evidence.taxes]
        values = [evidence.gross, evidence.net, *taxes, *paid]
        if evidence.gross is None or evidence.net is None or None in values:
            return None
        withheld = sum((abs(v) for v in taxes + paid if v is not None), _ZERO)
        expected = evidence.gross - withheld
        if abs(expected - evidence.net) <= context.config.net_tolerance:
            return ()
        return (
            CheckFlag(
                code=CheckCode.NET_MISMATCH,
                message=f"gross - taxes - deductions = {expected}, "
                f"printed net = {evidence.net}",
            ),
        )


class FederalTaxableWagesCheck:
    """Printed federal taxable wages should equal gross - pre-tax deductions."""

    name = CheckName.FEDERAL_TAXABLE_WAGES

    def run(self, context: CheckContext) -> tuple[CheckFlag, ...] | None:
        evidence = context.evidence
        printed, gross = evidence.federal_taxable_wages, evidence.gross
        if printed is None or gross is None:
            return None
        pretax = sum(
            (
                abs(d.line.amount)
                for d in context.decisions
                if d.decision is Decision.PRETAX and d.line.amount is not None
            ),
            _ZERO,
        )
        expected = gross - pretax
        if abs(expected - printed) <= context.config.wage_tolerance:
            return ()
        code = CheckCode.FEDERAL_TAXABLE_WAGES_MISMATCH
        message = (
            f"gross - pre-tax = {expected}, printed federal taxable wages = {printed}"
        )
        rows = (
            i
            for i, d in enumerate(context.decisions)
            if d.rule_id in _WEAK_RULES and d.decision is not Decision.NEEDS_REVIEW
        )
        return (
            CheckFlag(code=code, message=message),
            *_row_flags(code, message, rows, context.config.send_to_review),
        )


def _implied_wages(
    taxes: Sequence[AmountLine], labels: Sequence[str], rate: Decimal
) -> Decimal | None:
    matches = [t for t in taxes if contains_any(t.label, labels)]
    if len(matches) != 1 or matches[0].amount is None:
        return None
    return abs(matches[0].amount) / rate


class PayrollTaxGapCheck:
    """Social Security and Medicare wages clearly below gross hint at pre-tax rows."""

    name = CheckName.PAYROLL_TAX_GAP

    def run(self, context: CheckContext) -> tuple[CheckFlag, ...] | None:
        evidence, config = context.evidence, context.config
        gross = evidence.gross
        if gross is None:
            return None
        implied = [
            wages
            for wages in (
                _implied_wages(
                    evidence.taxes,
                    config.social_security_labels,
                    config.social_security_rate,
                ),
                _implied_wages(
                    evidence.taxes, config.medicare_labels, config.medicare_rate
                ),
            )
            if wages is not None
        ]
        if not implied:
            return None
        # Both taxes must agree, so the Social Security wage cap can't cause a flag.
        if not all(gross - wages > config.wage_tolerance for wages in implied):
            return ()
        code = CheckCode.PAYROLL_TAX_GAP
        message = (
            f"payroll taxes imply wages of {min(implied):.2f}, below gross {gross}"
        )
        rows = (
            i
            for i, d in enumerate(context.decisions)
            if d.rule_id in _WEAK_RULES
            and d.decision is Decision.NOT_PRETAX
            and contains_any(d.line.label, config.cafeteria_plan_names)
        )
        return (
            CheckFlag(code=code, message=message),
            *_row_flags(code, message, rows, config.send_to_review),
        )


class BracketsCheck:
    """A lone bracketed amount may be taxable wages or money taken out (DL-037)."""

    name = CheckName.BRACKETS

    def run(self, context: CheckContext) -> tuple[CheckFlag, ...] | None:
        evidence = context.evidence
        groups: tuple[tuple[str, Sequence[AmountLine | DeductionLine]], ...] = (
            ("earnings", evidence.earnings),
            ("taxes", evidence.taxes),
            ("deductions", evidence.deductions),
        )
        # The whole stub goes to review: what the number is, not its pre-tax status,
        # is unknown, so the business's no-review setting (DL-022) doesn't apply.
        return tuple(
            CheckFlag(
                code=CheckCode.AMOUNT_IN_BRACKETS,
                message=f"{what}[{i}] amount is printed in brackets; "
                "its meaning is unclear (Q25)",
                send_to_review=True,
            )
            for what, lines in groups
            for i, line in enumerate(lines)
            if line.in_brackets
        )


DEFAULT_CHECKS: tuple[Check, ...] = (
    GroundingCheck(),
    NetCheck(),
    FederalTaxableWagesCheck(),
    PayrollTaxGapCheck(),
    BracketsCheck(),
)


def run_checks(
    evidence: PaystubEvidence,
    decisions: Sequence[DeductionDecision],
    config: ChecksConfig,
    document_text: str | None = None,
    checks: Sequence[Check] = DEFAULT_CHECKS,
) -> CheckReport:
    if tuple(d.line for d in decisions) != evidence.deductions:
        raise InputMismatchError("decisions don't match the evidence's deduction rows")
    context = CheckContext(
        evidence=evidence,
        decisions=tuple(decisions),
        document_text=document_text,
        config=config,
    )
    flags: list[CheckFlag] = []
    not_run: list[CheckName] = []
    for check in checks:
        found = check.run(context)
        if found is None:
            not_run.append(check.name)
        else:
            flags.extend(found)
    return CheckReport(flags=tuple(flags), not_run=tuple(not_run))


def apply_review(
    decisions: Sequence[DeductionDecision], report: CheckReport
) -> tuple[DeductionDecision, ...]:
    """Move flagged decisions to needs_review, recording the original and the check."""
    reasons: dict[int, CheckCode] = {}
    for flag in report.flags:
        if flag.send_to_review and flag.deduction_index is not None:
            if flag.deduction_index >= len(decisions):
                raise InputMismatchError(
                    f"a flag points at row {flag.deduction_index}, "
                    f"but there are {len(decisions)} decisions"
                )
            reasons.setdefault(flag.deduction_index, flag.code)
    result = []
    for i, decided in enumerate(decisions):
        if i in reasons and decided.decision is not Decision.NEEDS_REVIEW:
            decided = DeductionDecision.model_validate(
                {
                    **decided.model_dump(),
                    "decision": Decision.NEEDS_REVIEW,
                    "escalated_from": decided.decision,
                    "escalated_by": reasons[i],
                }
            )
        result.append(decided)
    return tuple(result)

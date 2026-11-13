"""Pre-tax rule engine (architecture section 5, step 5).

Each rule is a small object; `classify` walks them in order and the first rule that
returns a verdict wins. Add a rule by writing a class and placing it in the list.
"""

from collections.abc import Iterable, Iterator, Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from paystub_agi.config import RulesConfig
from paystub_agi.errors import ClassificationError
from paystub_agi.matching import contains_any
from paystub_agi.models import (
    CodeValue,
    Decision,
    DeductionDecision,
    DeductionLine,
    Footnote,
    PaystubEvidence,
    RuleId,
    Text,
)


class RuleContext(BaseModel):
    """What a rule may look at besides the row itself."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    footnotes: tuple[Footnote, ...]
    config: RulesConfig


class Verdict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: Decision
    evidence: Text


class Rule(Protocol):
    @property
    def rule_id(self) -> RuleId: ...

    def apply(self, line: DeductionLine, context: RuleContext) -> Verdict | None: ...


# --- where the evidence is read from ----------------------------------------------


def _code_evidence(code: CodeValue) -> str:
    text = code.value if code.column is None else f"{code.column}: {code.value}"
    return f'code "{text}"'


def _label(line: DeductionLine) -> Iterator[tuple[str, str]]:
    yield f'label "{line.label}"', line.label


def _codes(line: DeductionLine) -> Iterator[tuple[str, str]]:
    for code in line.codes:
        yield _code_evidence(code), code.value


def _heading(line: DeductionLine) -> Iterator[tuple[str, str]]:
    if line.section_heading is not None:
        heading = line.section_heading
        yield f'section heading "{heading}"', heading


def _row(line: DeductionLine) -> Iterator[tuple[str, str]]:
    yield from _label(line)
    yield from _codes(line)


def _everywhere(line: DeductionLine) -> Iterator[tuple[str, str]]:
    yield from _row(line)
    yield from _heading(line)


def _find(sources: Iterable[tuple[str, str]], keywords: Sequence[str]) -> str | None:
    for evidence, text in sources:
        if contains_any(text, keywords) is not None:
            return evidence
    return None


def _column(
    line: DeductionLine, headers: Sequence[str], values: Sequence[str]
) -> str | None:
    """A code under a column such as "Pre-Tax" whose value is e.g. "Y" or "N"."""
    for code in line.codes:
        if contains_any(code.column, headers) and contains_any(code.value, values):
            return _code_evidence(code)
    return None


def _verdict(decision: Decision, evidence: str | None) -> Verdict | None:
    return None if evidence is None else Verdict(decision=decision, evidence=evidence)


# --- the rules, in order ------------------------------------------------------------------


class EmployerRule:
    rule_id = RuleId.R1

    def apply(self, line: DeductionLine, context: RuleContext) -> Verdict | None:
        if line.in_employer_section:
            heading = line.section_heading
            evidence = "employer section" + ("" if heading is None else f' "{heading}"')
            return Verdict(decision=Decision.EXCLUDED, evidence=evidence)
        keywords = context.config.keywords.employer_markers
        return _verdict(Decision.EXCLUDED, _find(_everywhere(line), keywords))


class TaxRule:
    rule_id = RuleId.R2

    def apply(self, line: DeductionLine, context: RuleContext) -> Verdict | None:
        keywords = context.config.keywords.tax_labels
        return _verdict(Decision.EXCLUDED, _find(_label(line), keywords))


class ExplicitPostTaxRule:
    rule_id = RuleId.R3

    def apply(self, line: DeductionLine, context: RuleContext) -> Verdict | None:
        keywords = context.config.keywords
        evidence = _find(_everywhere(line), keywords.posttax_markers) or _column(
            line, keywords.pretax_markers, keywords.column_no_values
        )
        return _verdict(Decision.NOT_PRETAX, evidence)


class ExplicitPreTaxRule:
    rule_id = RuleId.R4

    def apply(self, line: DeductionLine, context: RuleContext) -> Verdict | None:
        keywords = context.config.keywords
        evidence = _find(_everywhere(line), keywords.pretax_markers) or _column(
            line, keywords.pretax_markers, keywords.column_yes_values
        )
        return _verdict(Decision.PRETAX, evidence)


class PostTaxCategoryRule:
    rule_id = RuleId.R5

    def apply(self, line: DeductionLine, context: RuleContext) -> Verdict | None:
        keywords = context.config.keywords.posttax_categories
        return _verdict(Decision.NOT_PRETAX, _find(_label(line), keywords))


class FootnoteRule:
    rule_id = RuleId.R6

    def apply(self, line: DeductionLine, context: RuleContext) -> Verdict | None:
        config = context.config
        if config.asterisk_scope == "uniform_only" and not contains_any(
            line.label, config.keywords.uniform_labels
        ):
            return None
        for note in context.footnotes:
            if note.marker.strip() in {m.strip() for m in line.markers} and (
                contains_any(note.text, config.keywords.pretax_footnote_phrases)
            ):
                return Verdict(
                    decision=Decision.PRETAX,
                    evidence=f'footnote "{note.marker} {note.text}"',
                )
        return None


class EeRule:
    rule_id = RuleId.R7

    def apply(self, line: DeductionLine, context: RuleContext) -> Verdict | None:
        config = context.config
        evidence = _find(_row(line), config.keywords.ee_codes)
        return _verdict(Decision(config.ee_means), evidence)


class EmpRule:
    rule_id = RuleId.R8

    def apply(self, line: DeductionLine, context: RuleContext) -> Verdict | None:
        config = context.config
        if config.emp_means == "employee":
            return None
        decision = (
            Decision.EXCLUDED
            if config.emp_means == "employer"
            else Decision(config.emp_means)
        )
        return _verdict(decision, _find(_row(line), config.keywords.emp_codes))


class BenefitNameRule:
    rule_id = RuleId.R9

    def apply(self, line: DeductionLine, context: RuleContext) -> Verdict | None:
        config = context.config
        evidence = _find(_label(line), config.keywords.benefit_names)
        return _verdict(Decision(config.bare_benefit_names), evidence)


class UnclearDefaultRule:
    rule_id = RuleId.R10

    def apply(self, line: DeductionLine, context: RuleContext) -> Verdict | None:
        return Verdict(
            decision=Decision(context.config.unclear_default),
            evidence=f'label "{line.label}"',
        )


DEFAULT_RULES: tuple[Rule, ...] = (
    EmployerRule(),
    TaxRule(),
    ExplicitPostTaxRule(),
    ExplicitPreTaxRule(),
    PostTaxCategoryRule(),
    FootnoteRule(),
    EeRule(),
    EmpRule(),
    BenefitNameRule(),
    UnclearDefaultRule(),
)


def _decide(
    line: DeductionLine, context: RuleContext, rules: Sequence[Rule]
) -> DeductionDecision:
    for rule in rules:
        verdict = rule.apply(line, context)
        if verdict is not None:
            return DeductionDecision(
                line=line,
                decision=verdict.decision,
                rule_id=rule.rule_id,
                evidence=verdict.evidence,
            )
    raise ClassificationError("no rule decided a deduction; end the list with R10")


def classify(
    evidence: PaystubEvidence,
    config: RulesConfig,
    rules: Sequence[Rule] = DEFAULT_RULES,
) -> tuple[DeductionDecision, ...]:
    """Decide every deduction, in the order printed on the stub."""
    context = RuleContext(footnotes=evidence.footnotes, config=config)
    return tuple(_decide(line, context, rules) for line in evidence.deductions)

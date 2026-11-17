"""Component settings: rule behaviour, keyword lists and AGI parameters.

Infrastructure choices (model, region, credentials, paths) never belong here; the
caller supplies those (AGENTS.md section 10.4).
"""

import re
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    ValidationError,
)

from paystub_agi.errors import ConfigError
from paystub_agi.models import PayFrequency

_HAS_WORD = re.compile(r"[A-Za-z0-9]")


def _has_word(value: str) -> str:
    if not _HAS_WORD.search(value):
        raise ValueError("keyword must contain a letter or digit")
    return value


Keyword = Annotated[str, AfterValidator(_has_word)]
Keywords = tuple[Keyword, ...]

Treatment = Literal["pretax", "not_pretax", "needs_review"]


class _Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _unique(names: tuple[str, ...]) -> tuple[str, ...]:
    if len(set(names)) != len(names):
        raise ValueError("each reader may appear only once")
    return names


ReaderName = Annotated[str, Field(pattern=r"^[a-z0-9_]+$")]


class ReadingConfig(_Settings):
    """How the stub is read (decisionlog DL-034, DL-033)."""

    # Readers tried in this order until one gives a usable read. "pdfplumber" is
    # built in; every other name must be supplied by the caller.
    strategy: Annotated[
        tuple[ReaderName, ...], Field(min_length=1), AfterValidator(_unique)
    ] = ("pdfplumber", "textract")
    max_images: PositiveInt = 3
    image_dpi: Annotated[int, Field(ge=36, le=600)] = 144
    image_max_side: Annotated[int, Field(ge=100)] = 1568
    grayscale: bool = True


class ExtractionConfig(_Settings):
    """How the model is asked (DL-036). The model ID comes from the caller."""

    # auto: page images only if the caller's model accepts images.
    send_images: Literal["auto", "never"] = "auto"
    # None leaves it to the model; some models reject a temperature.
    temperature: Annotated[float, Field(ge=0)] | None = 0
    max_output_tokens: PositiveInt = 8192


class RuleKeywords(_Settings):
    """Words the rules look for. Matching is case-insensitive, on whole words."""

    employer_markers: Keywords = ("er", "err", "employer", "company paid", "co paid")
    tax_labels: Keywords = (
        "federal income tax",
        "federal withholding",
        "federal tax",
        "fed tax",
        "fed withholding",
        "fit",
        "fitw",
        "social security",
        "oasdi",
        "fica",
        "medicare",
        "state income tax",
        "state tax",
        "sit",
        "local tax",
        "city tax",
        "eit",
        "lst",
        "sdi",
        "sui",
        "suta",
        "pfl",
        "fli",
    )
    posttax_markers: Keywords = (
        "post tax",
        "posttax",
        "post",
        "after tax",
        "aftertax",
        "roth",
    )
    pretax_markers: Keywords = (
        "pre tax",
        "pretax",
        "pt",
        "prtx",
        "before tax",
        "tax deferred",
        "tax sheltered",
        "tax exempt",
        "non taxed",
        "no tax",
    )
    # Only in a code column: in a label, "pre" also matches "Pre-Pocketed" (DL-045).
    pretax_codes: Keywords = ("pre",)
    # A pre-tax heading with these words also covers other deductions (DL-045).
    mixed_heading_words: Keywords = ("other", "taxes", "withholding", "withholdings")
    posttax_categories: Keywords = (
        "garnish",
        "garnishment",
        "union dues",
        "charity",
        "charitable",
        "child support",
    )
    pretax_footnote_phrases: Keywords = (
        "pre tax",
        "pretax",
        "before tax",
        "excluded from federal taxable wages",
        "excluded from taxable wages",
        "not taxable",
        "non taxable",
        "nontaxable",
        "section 125",
        "sec 125",
        "tax exempt",
        "tax deferred",
    )
    uniform_labels: Keywords = ("uniform",)
    # Values in a column whose header is a pre-tax marker, e.g. "Pre-Tax: Y".
    column_yes_values: Keywords = ("y", "yes", "x", "true")
    column_no_values: Keywords = ("n", "no", "false")
    ee_codes: Keywords = ("ee",)
    emp_codes: Keywords = ("emp",)
    benefit_names: Keywords = (
        "401k",
        "403b",
        "457",
        "457b",
        "tsp",
        "medical",
        "health",
        "dental",
        "vision",
        "hsa",
        "fsa",
        "hdhp",
        "dependent care",
        "transit",
        "parking",
        "commuter",
    )


class RulesConfig(_Settings):
    """Settings for rules R6 to R10; defaults follow the business answers (DL-021)."""

    bare_benefit_names: Treatment = "not_pretax"
    ee_means: Treatment = "not_pretax"
    # "employee": EMP is the employee's own contribution, so later rules decide.
    emp_means: Literal["employee", "employer", "pretax", "needs_review"] = "employee"
    asterisk_scope: Literal["any", "uniform_only"] = "any"
    unclear_default: Literal["not_pretax", "needs_review"] = "not_pretax"
    keywords: RuleKeywords = RuleKeywords()


def _every_frequency(value: dict[PayFrequency, int]) -> dict[PayFrequency, int]:
    missing = [f.value for f in PayFrequency if f not in value]
    if missing:
        raise ValueError(f"missing frequencies: {', '.join(missing)}")
    return value


class AgiConfig(_Settings):
    """AGI parameters; defaults reproduce the reference `agi.py`."""

    one_time_earnings: Keywords = ("bonus", "overtime", "double time")
    # Source doc: commission alone is regular pay; next to other pay it goes in
    # the bonus column. "one_time" counts it once instead of annualising it.
    commission_earnings: Keywords = ("commission",)
    commission_with_other_pay: Literal["one_time", "regular"] = "one_time"
    # With printed federal taxable wages: "once" adds bonus/overtime once (like the
    # gross formula); "annualise" multiplies the whole figure by the periods.
    one_time_with_federal_wages: Literal["once", "annualise"] = "once"
    periods_per_year: Annotated[
        dict[PayFrequency, PositiveInt], AfterValidator(_every_frequency)
    ] = {
        PayFrequency.WEEKLY: 52,
        PayFrequency.BIWEEKLY: 26,
        PayFrequency.SEMIMONTHLY: 24,
        PayFrequency.MONTHLY: 12,
        PayFrequency.QUARTERLY: 4,
        PayFrequency.ANNUAL: 1,
        PayFrequency.ONE_TIME: 1,
    }
    default_frequency: PayFrequency | None = None


class ChecksConfig(_Settings):
    """Tolerances and labels for the consistency checks (architecture step 4)."""

    # Off: the business wants no manual review for unmarked rows (DL-022).
    send_to_review: bool = False
    net_tolerance: Annotated[Decimal, Field(ge=0)] = Decimal("0.02")
    wage_tolerance: Annotated[Decimal, Field(ge=0)] = Decimal("1.00")
    social_security_rate: Annotated[Decimal, Field(gt=0)] = Decimal("0.062")
    medicare_rate: Annotated[Decimal, Field(gt=0)] = Decimal("0.0145")
    social_security_labels: Keywords = ("social security", "oasdi", "soc sec")
    medicare_labels: Keywords = ("medicare",)
    # Benefits usually taken before Social Security/Medicare tax (Section 125).
    cafeteria_plan_names: Keywords = (
        "medical",
        "health",
        "dental",
        "vision",
        "hsa",
        "fsa",
    )


class AnalyzerConfig(_Settings):
    reading: ReadingConfig = ReadingConfig()
    extraction: ExtractionConfig = ExtractionConfig()
    rules: RulesConfig = RulesConfig()
    agi: AgiConfig = AgiConfig()
    checks: ChecksConfig = ChecksConfig()

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> AnalyzerConfig:
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise ConfigError(f"invalid configuration: {exc}") from exc

    @classmethod
    def from_yaml(cls, path: Path) -> AnalyzerConfig:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"cannot read configuration file {path}") from exc
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ConfigError(f"{path} must contain a mapping at the top level")
        return cls.from_mapping(data)

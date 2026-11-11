"""Component settings: rule behaviour, keyword lists and AGI parameters.

Infrastructure choices (model, region, credentials, paths) never belong here; the
caller supplies those (AGENTS.md section 10.4).
"""

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import AfterValidator, BaseModel, ConfigDict, PositiveInt, ValidationError

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
        "pre",
        "pt",
        "prtx",
        "before tax",
        "tax deferred",
        "tax sheltered",
        "tax exempt",
        "non taxed",
        "no tax",
    )
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
    """Settings for the disputed rules R6 to R10 (architecture section 7)."""

    bare_benefit_names: Treatment = "needs_review"
    ee_means: Treatment = "needs_review"
    emp_means: Literal["employer", "pretax", "needs_review"] = "needs_review"
    asterisk_scope: Literal["any", "uniform_only"] = "any"
    unclear_default: Literal["not_pretax", "needs_review"] = "needs_review"
    keywords: RuleKeywords = RuleKeywords()


def _every_frequency(value: dict[PayFrequency, int]) -> dict[PayFrequency, int]:
    missing = [f.value for f in PayFrequency if f not in value]
    if missing:
        raise ValueError(f"missing frequencies: {', '.join(missing)}")
    return value


class AgiConfig(_Settings):
    """AGI parameters; defaults reproduce the reference `agi.py`."""

    one_time_earnings: Keywords = ("bonus", "overtime")
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


class AnalyzerConfig(_Settings):
    rules: RulesConfig = RulesConfig()
    agi: AgiConfig = AgiConfig()

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

from decimal import Decimal
from pathlib import Path

import pytest

from paystub_agi.config import AgiConfig, AnalyzerConfig, ChecksConfig, RulesConfig
from paystub_agi.errors import ConfigError
from paystub_agi.models import PayFrequency

DEFAULT_YAML = Path(__file__).parents[2] / "config" / "default.yaml"


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "paystub.yaml"
    path.write_text(text, encoding="utf-8")
    return path


# --- defaults ------------------------------------------------------------------------


def test_config_rule_setting_defaults_follow_business_answers() -> None:
    rules = RulesConfig()

    assert rules.bare_benefit_names == "not_pretax"
    assert rules.ee_means == "not_pretax"
    assert rules.emp_means == "employee"
    assert rules.asterisk_scope == "any"
    assert rules.unclear_default == "not_pretax"


def test_config_agi_defaults_match_reference() -> None:
    agi = AgiConfig()

    assert agi.one_time_earnings == ("bonus", "overtime")
    assert agi.default_frequency is None
    assert agi.periods_per_year == {
        PayFrequency.WEEKLY: 52,
        PayFrequency.BIWEEKLY: 26,
        PayFrequency.SEMIMONTHLY: 24,
        PayFrequency.MONTHLY: 12,
        PayFrequency.QUARTERLY: 4,
        PayFrequency.ANNUAL: 1,
        PayFrequency.ONE_TIME: 1,
    }


def test_config_commission_defaults_follow_user_decision() -> None:
    agi = AgiConfig()

    assert agi.commission_earnings == ("commission",)
    assert agi.commission_with_other_pay == "one_time"
    assert agi.one_time_with_federal_wages == "once"


@pytest.mark.parametrize("value", ["once", "annualise"])
def test_config_one_time_with_federal_wages_accepts(value: str) -> None:
    config = AnalyzerConfig.from_mapping(
        {"agi": {"one_time_with_federal_wages": value}}
    )

    assert config.agi.one_time_with_federal_wages == value


def test_config_one_time_with_federal_wages_rejects_unknown() -> None:
    with pytest.raises(ConfigError, match="one_time_with_federal_wages"):
        AnalyzerConfig.from_mapping({"agi": {"one_time_with_federal_wages": "twice"}})


@pytest.mark.parametrize("value", ["one_time", "regular"])
def test_config_commission_with_other_pay_accepts(value: str) -> None:
    config = AnalyzerConfig.from_mapping({"agi": {"commission_with_other_pay": value}})

    assert config.agi.commission_with_other_pay == value


def test_config_commission_with_other_pay_rejects_unknown() -> None:
    with pytest.raises(ConfigError, match="commission_with_other_pay"):
        AnalyzerConfig.from_mapping({"agi": {"commission_with_other_pay": "bonus"}})


def test_config_default_keywords_are_not_empty() -> None:
    keywords = RulesConfig().keywords

    for name in type(keywords).model_fields:
        assert getattr(keywords, name), name


def test_config_pretax_column_values_have_defaults() -> None:
    keywords = RulesConfig().keywords

    assert keywords.column_yes_values == ("y", "yes", "x", "true")
    assert keywords.column_no_values == ("n", "no", "false")


def test_config_default_yaml_file_equals_built_in_defaults() -> None:
    assert AnalyzerConfig.from_yaml(DEFAULT_YAML) == AnalyzerConfig()


# --- every setting value ----------------------------------------------------------------


@pytest.mark.parametrize("value", ["pretax", "not_pretax", "needs_review"])
def test_config_bare_benefit_names_accepts(value: str) -> None:
    assert (
        RulesConfig.model_validate({"bare_benefit_names": value}).bare_benefit_names
        == value
    )


@pytest.mark.parametrize("value", ["pretax", "not_pretax", "needs_review"])
def test_config_ee_means_accepts(value: str) -> None:
    assert RulesConfig.model_validate({"ee_means": value}).ee_means == value


@pytest.mark.parametrize("value", ["employee", "employer", "pretax", "needs_review"])
def test_config_emp_means_accepts(value: str) -> None:
    assert RulesConfig.model_validate({"emp_means": value}).emp_means == value


@pytest.mark.parametrize("value", ["any", "uniform_only"])
def test_config_asterisk_scope_accepts(value: str) -> None:
    assert RulesConfig.model_validate({"asterisk_scope": value}).asterisk_scope == value


@pytest.mark.parametrize("value", ["not_pretax", "needs_review"])
def test_config_unclear_default_accepts(value: str) -> None:
    assert (
        RulesConfig.model_validate({"unclear_default": value}).unclear_default == value
    )


@pytest.mark.parametrize(
    ("setting", "bad"),
    [
        ("bare_benefit_names", "excluded"),
        ("ee_means", "employer"),
        ("emp_means", "not_pretax"),
        ("asterisk_scope", "none"),
        ("unclear_default", "pretax"),
    ],
)
def test_config_rule_setting_rejects_unknown_value(
    tmp_path: Path, setting: str, bad: str
) -> None:
    path = _write(tmp_path, f"rules:\n  {setting}: {bad}\n")

    with pytest.raises(ConfigError, match=setting):
        AnalyzerConfig.from_yaml(path)


# --- keywords -------------------------------------------------------------------------


def test_config_keywords_can_be_replaced() -> None:
    rules = RulesConfig.model_validate({"keywords": {"benefit_names": ["401k"]}})

    assert rules.keywords.benefit_names == ("401k",)
    assert rules.keywords.pretax_markers == RulesConfig().keywords.pretax_markers


def test_config_keyword_list_may_be_empty() -> None:
    rules = RulesConfig.model_validate({"keywords": {"posttax_categories": []}})

    assert rules.keywords.posttax_categories == ()


@pytest.mark.parametrize("bad", ["", "   ", "-/*"])
def test_config_keyword_without_letters_or_digits_is_rejected(bad: str) -> None:
    with pytest.raises(ConfigError, match="benefit_names"):
        AnalyzerConfig.from_mapping({"rules": {"keywords": {"benefit_names": [bad]}}})


def test_config_unknown_keyword_list_is_rejected() -> None:
    with pytest.raises(ConfigError, match="pretax_words"):
        AnalyzerConfig.from_mapping({"rules": {"keywords": {"pretax_words": ["pre"]}}})


# --- agi settings ---------------------------------------------------------------------


def test_config_default_frequency_accepts_frequency_name() -> None:
    config = AnalyzerConfig.from_mapping({"agi": {"default_frequency": "biweekly"}})

    assert config.agi.default_frequency is PayFrequency.BIWEEKLY


def test_config_default_frequency_rejects_unknown_name() -> None:
    with pytest.raises(ConfigError, match="default_frequency"):
        AnalyzerConfig.from_mapping({"agi": {"default_frequency": "fortnightly"}})


def test_config_periods_per_year_missing_a_frequency_is_rejected() -> None:
    periods = {"weekly": 52, "biweekly": 26}

    with pytest.raises(ConfigError, match="periods_per_year"):
        AnalyzerConfig.from_mapping({"agi": {"periods_per_year": periods}})


@pytest.mark.parametrize("bad", [0, -26])
def test_config_periods_per_year_must_be_positive(bad: int) -> None:
    periods: dict[str, int] = {
        f.value: n for f, n in AgiConfig().periods_per_year.items()
    }
    periods["biweekly"] = bad

    with pytest.raises(ConfigError, match="periods_per_year"):
        AnalyzerConfig.from_mapping({"agi": {"periods_per_year": periods}})


def test_config_one_time_earnings_may_be_empty() -> None:
    config = AnalyzerConfig.from_mapping({"agi": {"one_time_earnings": []}})

    assert config.agi.one_time_earnings == ()


# --- checks settings ----------------------------------------------------------------


def test_config_checks_defaults() -> None:
    checks = ChecksConfig()

    assert checks.send_to_review is False
    assert checks.net_tolerance == Decimal("0.02")
    assert checks.wage_tolerance == Decimal("1.00")
    assert checks.social_security_rate == Decimal("0.062")
    assert checks.medicare_rate == Decimal("0.0145")
    assert checks.social_security_labels == ("social security", "oasdi", "soc sec")
    assert checks.medicare_labels == ("medicare",)
    assert checks.cafeteria_plan_names == (
        "medical",
        "health",
        "dental",
        "vision",
        "hsa",
        "fsa",
    )


def test_config_checks_decimal_from_yaml_float_is_exact(tmp_path: Path) -> None:
    path = _write(tmp_path, "checks:\n  medicare_rate: 0.0145\n")

    assert AnalyzerConfig.from_yaml(path).checks.medicare_rate == Decimal("0.0145")


@pytest.mark.parametrize(
    "setting",
    ["net_tolerance", "wage_tolerance", "social_security_rate", "medicare_rate"],
)
@pytest.mark.parametrize("bad", [-1, "abc"])
def test_config_checks_number_must_be_non_negative(setting: str, bad: object) -> None:
    with pytest.raises(ConfigError, match=setting):
        AnalyzerConfig.from_mapping({"checks": {setting: bad}})


@pytest.mark.parametrize("setting", ["social_security_rate", "medicare_rate"])
def test_config_checks_rate_must_not_be_zero(setting: str) -> None:
    with pytest.raises(ConfigError, match=setting):
        AnalyzerConfig.from_mapping({"checks": {setting: 0}})


# --- loading ---------------------------------------------------------------------------


def test_config_from_yaml_partial_file_keeps_other_defaults(tmp_path: Path) -> None:
    path = _write(tmp_path, "rules:\n  ee_means: pretax\n")

    config = AnalyzerConfig.from_yaml(path)

    assert config.rules.ee_means == "pretax"
    assert config.rules.emp_means == "employee"
    assert config.agi == AgiConfig()


def test_config_from_yaml_empty_file_gives_defaults(tmp_path: Path) -> None:
    assert AnalyzerConfig.from_yaml(_write(tmp_path, "")) == AnalyzerConfig()


def test_config_from_yaml_missing_file_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read"):
        AnalyzerConfig.from_yaml(tmp_path / "absent.yaml")


def test_config_from_yaml_invalid_yaml_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not valid YAML"):
        AnalyzerConfig.from_yaml(_write(tmp_path, "rules: [unclosed\n"))


def test_config_from_yaml_top_level_list_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="mapping"):
        AnalyzerConfig.from_yaml(_write(tmp_path, "- rules\n"))


def test_config_from_yaml_refuses_python_object_tags(tmp_path: Path) -> None:
    path = _write(tmp_path, "rules: !!python/object/apply:os.system ['echo hi']\n")

    with pytest.raises(ConfigError, match="not valid YAML"):
        AnalyzerConfig.from_yaml(path)


def test_config_unknown_top_level_key_is_rejected() -> None:
    with pytest.raises(ConfigError, match="model_id"):
        AnalyzerConfig.from_mapping({"model_id": "anything"})


def test_config_unknown_nested_key_is_rejected() -> None:
    with pytest.raises(ConfigError, match="tax_math_as_evidence"):
        AnalyzerConfig.from_mapping({"rules": {"tax_math_as_evidence": "decide"}})


def test_config_is_frozen() -> None:
    config = AnalyzerConfig()

    with pytest.raises(ValueError):
        config.rules = RulesConfig()  # type: ignore[misc]

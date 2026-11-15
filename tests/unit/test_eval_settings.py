from pathlib import Path
from typing import Any

import pytest

from evaluation.settings import HarnessSettings
from paystub_agi.config import AnalyzerConfig
from paystub_agi.errors import ConfigError

REPO = Path(__file__).parents[2]


def _settings(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "aws": {"region": "us-east-1"},
        "s3": {"bucket": "example-bucket"},
        "models": [{"name": "opus", "model_id": "us.anthropic.claude-opus-5"}],
    }
    values.update(overrides)
    return values


def test_eval_settings_defaults() -> None:
    settings = HarnessSettings.model_validate(_settings())

    assert settings.aws.retries.mode == "adaptive"
    assert settings.aws.retries.max_attempts == 5
    assert settings.s3.stubs_prefix == "datasets/paystubs/"
    assert settings.paths.answer_keys == Path("data/answer_keys")
    assert settings.paths.paystubs == Path("data/paystubs")
    assert settings.paths.ocr_reads == Path("data/ocr_reads")
    assert settings.paths.results == Path("data/results")
    assert settings.component_config == Path("evaluation/component.yaml")
    assert (settings.textract.mode, settings.textract.staging_bucket) == ("sync", None)
    assert settings.models[0].provider == "converse"
    assert settings.disputed_stubs == ()


def test_eval_settings_async_needs_a_staging_bucket() -> None:
    with pytest.raises(ValueError, match="staging_bucket"):
        HarnessSettings.model_validate(_settings(textract={"mode": "async"}))


def test_eval_settings_async_with_bucket_is_accepted() -> None:
    textract = {"mode": "async", "staging_bucket": "staging-bucket"}

    settings = HarnessSettings.model_validate(_settings(textract=textract))

    assert settings.textract.staging_bucket == "staging-bucket"


def test_eval_settings_sync_refuses_a_staging_bucket() -> None:
    textract = {"mode": "sync", "staging_bucket": "staging-bucket"}

    with pytest.raises(ValueError, match="sync"):
        HarnessSettings.model_validate(_settings(textract=textract))


@pytest.mark.parametrize("provider", ["converse", "mantle"])
def test_eval_settings_provider_accepts(provider: str) -> None:
    models = [{"name": "gpt", "model_id": "m", "provider": provider}]

    assert HarnessSettings.model_validate(_settings(models=models)).models[0].provider


@pytest.mark.parametrize(
    "bad",
    [
        {"models": []},
        {"models": [{"name": "a", "model_id": "m"}, {"name": "a", "model_id": "n"}]},
        {"models": [{"name": "Has Space", "model_id": "m"}]},
        {"models": [{"name": "../x", "model_id": "m"}]},
        {"models": [{"name": "a", "model_id": " "}]},
        {"models": [{"name": "a", "model_id": "m", "provider": "openai"}]},
        {"aws": {"region": ""}},
        {"aws": {"region": "us-east-1", "retries": {"mode": "fast"}}},
        {"aws": {"region": "us-east-1", "retries": {"max_attempts": 0}}},
        {"s3": {"bucket": "Bad_Bucket"}},
        {"textract": {"mode": "batch"}},
        {"disputed_stubs": ["stub07"]},
        {"unknown": 1},
    ],
)
def test_eval_settings_rejects_bad_values(bad: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        HarnessSettings.model_validate(_settings(**bad))


def test_eval_settings_disputed_stubs_are_folder_and_stub() -> None:
    settings = HarnessSettings.model_validate(
        _settings(disputed_stubs=["advs_paystubs/stub_0010"])
    )

    assert settings.disputed_stubs == ("advs_paystubs/stub_0010",)


def test_eval_settings_from_yaml(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "aws: {region: us-east-1}\n"
        "s3: {bucket: example-bucket}\n"
        "models: [{name: opus, model_id: us.anthropic.claude-opus-5}]\n",
        encoding="utf-8",
    )

    assert HarnessSettings.from_yaml(path).models[0].name == "opus"


@pytest.mark.parametrize(
    "text", ["models: [unclosed\n", "- a list\n", "aws: !!python/object:os.system x\n"]
)
def test_eval_settings_from_bad_yaml_raises_config_error(
    tmp_path: Path, text: str
) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ConfigError):
        HarnessSettings.from_yaml(path)


def test_eval_settings_from_invalid_values_raises_config_error(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("aws: {region: us-east-1}\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="s3"):
        HarnessSettings.from_yaml(path)


def test_eval_settings_missing_file_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read"):
        HarnessSettings.from_yaml(tmp_path / "absent.yaml")


def test_eval_settings_example_file_is_valid() -> None:
    settings = HarnessSettings.from_yaml(REPO / "evaluation" / "config.example.yaml")

    assert [m.model_id for m in settings.models] == [
        "us.anthropic.claude-opus-5",
        "us.anthropic.claude-sonnet-5",
        "google.gemma-3-27b-it",
        "openai.gpt-oss-120b-1:0",
    ]


def test_eval_component_config_is_text_only() -> None:
    config = AnalyzerConfig.from_yaml(REPO / "evaluation" / "component.yaml")

    assert config.extraction.send_images == "never"

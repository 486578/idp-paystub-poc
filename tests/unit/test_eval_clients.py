from typing import Any

import pytest
from idp_core.exceptions import ProviderError, UnsupportedInputError
from idp_genai.service import GenAIService
from idp_ocr import TextractReader

from evaluation.clients import (
    AutoTextract,
    boto_config,
    build_genai,
    build_textract,
    textract_staging_bucket,
)
from evaluation.settings import (
    AwsSettings,
    ModelSettings,
    RetrySettings,
    TextractSettings,
)

AWS = AwsSettings(
    region="us-east-1", retries=RetrySettings(mode="adaptive", max_attempts=7)
)


class FakeSession:
    """Records the boto3 clients asked for; returns a recording Converse client."""

    def __init__(self) -> None:
        self.clients: list[tuple[str, dict[str, Any]]] = []
        self.runtime = FakeRuntime()

    def client(self, service_name: str, **kwargs: Any) -> object:
        self.clients.append((service_name, kwargs))
        return self.runtime


class FakeRuntime:
    """A bedrock-runtime stand-in that records each Converse request."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.requests.append(kwargs)
        return {
            "output": {"message": {"role": "assistant", "content": [{"text": "{}"}]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
        }


def _converse_request(model: ModelSettings) -> dict[str, Any]:
    session = FakeSession()
    build_genai(session, AWS, model).extract(
        model=model.model_id, task="Copy the gross.", schema={"type": "object"}
    )
    [request] = session.runtime.requests
    return request


def test_eval_clients_converse_forces_a_tool_by_default() -> None:
    request = _converse_request(ModelSettings(name="gemma", model_id="m"))

    assert "toolConfig" in request


def test_eval_clients_prompt_schema_method_sends_no_tool() -> None:
    model = ModelSettings(name="opus", model_id="m", schema_method="prompt")

    assert "toolConfig" not in _converse_request(model)


def test_eval_clients_retry_config_comes_from_settings() -> None:
    config = boto_config(AWS.retries)

    assert config.retries == {"mode": "adaptive", "total_max_attempts": 7}


def test_eval_clients_sync_textract_gets_no_staging_bucket() -> None:
    assert textract_staging_bucket(TextractSettings(mode="sync")) is None


def test_eval_clients_async_textract_gets_the_staging_bucket() -> None:
    settings = TextractSettings(mode="async", staging_bucket="staging")

    assert textract_staging_bucket(settings) == "staging"


def test_eval_clients_textract_reader_builds_its_own_client() -> None:
    # idp-ocr's adapter for a raw boto3 Textract client is private (pilot finding).
    reader = build_textract(AWS, TextractSettings())

    assert isinstance(reader, TextractReader)


# --- auto Textract: sync for one page, staged async otherwise (DL-051) ---------------

REQUEST: Any = "request"


class _Reader:
    capabilities = TextractReader.capabilities

    def __init__(self, name: str, error: Exception | None = None) -> None:
        self.name = name
        self.error = error
        self.requests: list[object] = []

    def read(self, request: Any) -> Any:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return f"{self.name} result"


def test_eval_clients_auto_textract_reads_one_page_with_sync() -> None:
    sync, staged = _Reader("sync"), _Reader("staged")

    result: Any = AutoTextract(sync, staged).read(REQUEST)

    assert (result, staged.requests) == ("sync result", [])


def test_eval_clients_auto_textract_stages_what_sync_refuses() -> None:
    refused = UnsupportedInputError("Multi-page input requires staging_bucket")
    sync, staged = _Reader("sync", refused), _Reader("staged")

    result: Any = AutoTextract(sync, staged).read(REQUEST)

    assert (result, staged.requests) == ("staged result", ["request"])


def test_eval_clients_auto_textract_does_not_hide_other_errors() -> None:
    sync = _Reader("sync", ProviderError("Textract failed"))
    staged = _Reader("staged")

    with pytest.raises(ProviderError):
        AutoTextract(sync, staged).read(REQUEST)
    assert staged.requests == []


def test_eval_clients_auto_textract_looks_like_the_sync_reader() -> None:
    auto = AutoTextract(_Reader("textract"), _Reader("staged"))

    assert (auto.name, auto.capabilities) == ("textract", TextractReader.capabilities)


def test_eval_clients_auto_mode_builds_auto_textract() -> None:
    settings = TextractSettings(mode="auto", staging_bucket="staging")

    assert isinstance(build_textract(AWS, settings), AutoTextract)


def test_eval_clients_converse_service_is_text_only() -> None:
    session = FakeSession()
    model = ModelSettings(name="opus", model_id="us.anthropic.claude-opus-5")

    service = build_genai(session, AWS, model)

    assert isinstance(service, GenAIService)
    assert service.capabilities.image_media_types == ()
    [(name, kwargs)] = session.clients
    assert (name, kwargs["region_name"]) == ("bedrock-runtime", "us-east-1")
    assert kwargs["config"].retries["mode"] == "adaptive"


def test_eval_clients_mantle_service_uses_the_session_not_a_client() -> None:
    session = FakeSession()
    model = ModelSettings(name="gpt", model_id="openai.gpt-oss-120b", provider="mantle")

    service = build_genai(session, AWS, model)

    assert isinstance(service, GenAIService)
    assert service.capabilities.image_media_types == ()
    assert session.clients == []

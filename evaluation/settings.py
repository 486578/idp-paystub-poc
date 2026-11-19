"""Harness settings: infrastructure choices for the evaluation (DL-041).

Region, bucket, model IDs and retries live in a YAML file that isn't committed
(`evaluation/config.yaml`); credentials come only from the AWS profile.
"""

from pathlib import Path
from typing import Annotated, Any, Literal, Self

import yaml
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    ValidationError,
    model_validator,
)

from paystub_agi.config import AnalyzerConfig
from paystub_agi.errors import ConfigError

NonBlank = Annotated[str, Field(min_length=1, pattern=r"\S")]
# Model names become folder names, so only safe characters.
FolderName = Annotated[str, Field(pattern=r"^[a-z0-9_-]+$")]
StubRef = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]+/[A-Za-z0-9_-]+$")]


class _Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RetrySettings(_Settings):
    mode: Literal["standard", "adaptive", "legacy"] = "adaptive"
    max_attempts: PositiveInt = 5


class AwsSettings(_Settings):
    region: NonBlank
    retries: RetrySettings = RetrySettings()


class S3Settings(_Settings):
    bucket: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")]
    stubs_prefix: str = "datasets/paystubs/"


class PathSettings(_Settings):
    answer_keys: Path = Path("data/answer_keys")
    paystubs: Path = Path("data/paystubs")
    ocr_reads: Path = Path("data/ocr_reads")
    results: Path = Path("data/results")


class TextractSettings(_Settings):
    """DL-035/DL-051: sync gets no staging bucket; async and auto need one."""

    # auto: sync for one page, staged async when sync refuses a multi-page PDF.
    mode: Literal["sync", "async", "auto"] = "sync"
    staging_bucket: NonBlank | None = None

    @model_validator(mode="before")
    @classmethod
    def _default_mode(cls, data: Any) -> Any:
        if isinstance(data, dict) and "mode" not in data:
            return {**data, "mode": "auto" if data.get("staging_bucket") else "sync"}
        return data

    @model_validator(mode="after")
    def _bucket_matches_mode(self) -> Self:
        if self.mode != "sync" and self.staging_bucket is None:
            raise ValueError(f"{self.mode} mode needs a staging_bucket")
        if self.mode == "sync" and self.staging_bucket is not None:
            raise ValueError("sync mode doesn't use a staging_bucket")
        return self


class ModelSettings(_Settings):
    name: FolderName
    model_id: NonBlank
    provider: Literal["converse", "mantle"] = "converse"
    # idp-genai: "tool" forces a tool call; "prompt" puts the schema in the prompt.
    schema_method: Literal["tool", "prompt"] = "tool"
    # When given (even as null), replaces the component's extraction.temperature.
    temperature: Annotated[float, Field(ge=0)] | None = None


def _unique_names(models: tuple[ModelSettings, ...]) -> tuple[ModelSettings, ...]:
    names = [m.name for m in models]
    if len(set(names)) != len(names):
        raise ValueError("model names must be unique")
    return models


class HarnessSettings(_Settings):
    aws: AwsSettings
    # Only the download command uses S3; own stub sets don't need it.
    s3: S3Settings | None = None
    paths: PathSettings = PathSettings()
    # Only what differs from config/default.yaml needs listing.
    component: AnalyzerConfig = AnalyzerConfig()
    textract: TextractSettings = TextractSettings()
    models: Annotated[
        tuple[ModelSettings, ...], Field(min_length=1), AfterValidator(_unique_names)
    ]
    # Keys known to be wrong, as "folder/stub"; reported separately (7c).
    disputed_stubs: tuple[StubRef, ...] = ()

    @classmethod
    def from_yaml(cls, path: Path) -> HarnessSettings:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"cannot read harness settings {path}") from exc
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigError(f"{path} must contain a mapping at the top level")
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise ConfigError(f"invalid harness settings: {exc}") from exc

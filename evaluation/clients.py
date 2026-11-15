"""Builds the AWS-facing parts for the harness from its settings (caller side).

Nothing here is part of the component: the component only receives these objects.
"""

from pathlib import Path
from typing import Any, Protocol

from botocore.config import Config
from idp_genai.providers.bedrock import (
    bedrock_capabilities,
    bedrock_mantle_capabilities,
)
from idp_genai.service import GenAIService
from idp_ocr import TextractReader

from evaluation.settings import (
    AwsSettings,
    ModelSettings,
    RetrySettings,
    TextractSettings,
)


class Session(Protocol):
    def client(self, service_name: str, **kwargs: Any) -> Any: ...


class S3Client(Protocol):
    def download_file(self, Bucket: str, Key: str, Filename: str) -> None: ...  # noqa: N803


def boto_config(retries: RetrySettings) -> Config:
    return Config(
        retries={"mode": retries.mode, "total_max_attempts": retries.max_attempts}
    )


def textract_staging_bucket(settings: TextractSettings) -> str | None:
    """idp-ocr goes async exactly when it gets a staging bucket (DL-035)."""
    return settings.staging_bucket if settings.mode == "async" else None


def build_textract(
    session: Session, aws: AwsSettings, settings: TextractSettings
) -> TextractReader:
    client = session.client(
        "textract", region_name=aws.region, config=boto_config(aws.retries)
    )
    return TextractReader(
        client=client,
        region=aws.region,
        staging_bucket=textract_staging_bucket(settings),
    )


def build_genai(session: Any, aws: AwsSettings, model: ModelSettings) -> GenAIService:
    """Text-only capabilities: the harness sends no page images for now (DL-041)."""
    if model.provider == "mantle":
        # Mantle signs requests with the session itself and makes no retries.
        return GenAIService.create_bedrock_mantle_service(
            region=aws.region,
            session=session,
            capabilities=bedrock_mantle_capabilities(),
        )
    client = session.client(
        "bedrock-runtime", region_name=aws.region, config=boto_config(aws.retries)
    )
    return GenAIService.create_bedrock_service(
        client=client, capabilities=bedrock_capabilities()
    )


class Boto3Downloader:
    """idp-ocr's `S3Downloader` over the caller's own S3 client."""

    def __init__(self, s3: S3Client) -> None:
        self._s3 = s3

    def download(self, bucket: str, key: str, path: Path) -> None:
        self._s3.download_file(Bucket=bucket, Key=key, Filename=str(path))

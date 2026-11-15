"""Builds the AWS-facing parts for the harness from its settings (caller side).

Nothing here is part of the component: the component only receives these objects.
"""

from typing import Any

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


def boto_config(retries: RetrySettings) -> Config:
    return Config(
        retries={"mode": retries.mode, "total_max_attempts": retries.max_attempts}
    )


def textract_staging_bucket(settings: TextractSettings) -> str | None:
    """idp-ocr goes async exactly when it gets a staging bucket (DL-035)."""
    return settings.staging_bucket if settings.mode == "async" else None


def build_textract(aws: AwsSettings, settings: TextractSettings) -> TextractReader:
    # idp-ocr wraps raw boto3 clients privately, so it builds its own (one attempt).
    return TextractReader(
        region=aws.region, staging_bucket=textract_staging_bucket(settings)
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

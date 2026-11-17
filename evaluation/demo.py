"""Demo: analyse local paystubs with one model and compare AGI with the answer keys.

uv run python -m evaluation.demo --model-id <id> --region <region>
    --stub <paystub.pdf> <answer_key.json> [--stub <pdf> <key> ...]

Prints document values, so use it only on the synthetic stubs.
"""

import argparse
from pathlib import Path

import boto3

from evaluation.answer_keys import load_answer_key
from evaluation.clients import build_genai, build_textract
from evaluation.settings import AwsSettings, ModelSettings, TextractSettings
from paystub_agi import AnalyzerConfig, PaystubAgiError, PaystubAnalyzer


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m evaluation.demo")
    parser.add_argument(
        "--stub",
        nargs=2,
        action="append",
        required=True,
        type=Path,
        metavar=("PDF", "ANSWER_KEY"),
    )
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument(
        "--provider", choices=["converse", "mantle"], default="converse"
    )
    parser.add_argument("--schema-method", choices=["tool", "prompt"], default="tool")
    parser.add_argument(
        "--temperature", type=float, help="omit to use the model's own default"
    )
    args = parser.parse_args()

    aws = AwsSettings(region=args.region)
    model = ModelSettings(
        name="demo",
        model_id=args.model_id,
        provider=args.provider,
        schema_method=args.schema_method,
    )
    config = AnalyzerConfig()
    extraction = config.extraction.model_copy(update={"temperature": args.temperature})
    # Credentials come from the usual AWS chain (e.g. AWS_PROFILE).
    analyzer = PaystubAnalyzer.create(
        config.model_copy(update={"extraction": extraction}),
        genai=build_genai(boto3.Session(region_name=aws.region), aws, model),
        model=model.model_id,
        readers={"textract": build_textract(aws, TextractSettings())},
    )

    for pdf, key_path in args.stub:
        key_agi = load_answer_key(key_path).calculated.agi
        try:
            result = analyzer.analyze(str(pdf))
        except PaystubAgiError as exc:
            print(f"{pdf.name}: failed - {exc}")
            continue
        match = "yes" if result.agi.agi == key_agi else "no"
        print(
            f"{pdf.name}: status={result.status} agi={result.agi.agi} "
            f"key_agi={key_agi} match={match}"
        )
        for d in result.decisions:
            print(
                f"  {d.line.label} | {d.line.amount} | {d.decision} | "
                f"{d.rule_id} | {d.evidence}"
            )
        for flag in result.flags:
            print(f"  flag {flag.code}: {flag.message}")


if __name__ == "__main__":
    main()

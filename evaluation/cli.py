"""Command line for the harness: `uv run python -m evaluation download|run|score`.

The functions below `main` hold the logic and are tested with fakes; `main` only
builds the real AWS clients from the harness settings. Nothing printed contains
document values: only counts, IDs and file paths.
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

import boto3
from pydantic import BaseModel, ConfigDict

from evaluation.answer_keys import load_answer_key
from evaluation.clients import boto_config, build_genai, build_textract
from evaluation.download import StubRef, answer_key_refs, download_stubs, local_stub
from evaluation.report import write_report
from evaluation.run import Analyzer, StubOutcome, run_models, save_outcome
from evaluation.score import StubScore, score_outcome
from evaluation.settings import HarnessSettings, ModelSettings
from paystub_agi import AnalyzerConfig, FileEvidenceStore, PaystubAnalyzer
from paystub_agi.errors import ConfigError


class RunSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    succeeded: int
    failed: int
    not_downloaded: tuple[str, ...]


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m evaluation")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("download", "run", "score"):
        command = commands.add_parser(name)
        command.add_argument(
            "--config", type=Path, default=Path("evaluation/config.yaml")
        )
        if name == "run":
            command.add_argument("--models", nargs="+")
            command.add_argument("--stubs", nargs="+")
            command.add_argument("--run-id")
        if name == "score":
            command.add_argument("run_id")
    return parser.parse_args(argv)


def select_models(
    settings: HarnessSettings, names: Sequence[str] | None
) -> list[ModelSettings]:
    if not names:
        return list(settings.models)
    known = {m.name: m for m in settings.models}
    unknown = [n for n in names if n not in known]
    if unknown:
        raise ConfigError(f"unknown model names: {', '.join(unknown)}")
    return [known[n] for n in names]


def select_stubs(refs: Sequence[StubRef], ids: Sequence[str] | None) -> list[StubRef]:
    if not ids:
        return list(refs)
    known = {r.id: r for r in refs}
    unknown = [i for i in ids if i not in known]
    if unknown:
        raise ConfigError(f"stubs without an answer key: {', '.join(unknown)}")
    return [known[i] for i in ids]


def component_config_for(
    config: AnalyzerConfig, model: ModelSettings
) -> AnalyzerConfig:
    """Some models reject any temperature (e.g. Opus 5), so it can be set per model."""
    if "temperature" not in model.model_fields_set:
        return config
    extraction = config.extraction.model_copy(update={"temperature": model.temperature})
    return config.model_copy(update={"extraction": extraction})


def run_command(
    models: Sequence[ModelSettings],
    refs: Sequence[StubRef],
    *,
    paystubs: Path,
    results: Path,
    run_id: str,
    analyzer_factory: Callable[[ModelSettings], Analyzer],
) -> RunSummary:
    stubs: list[tuple[StubRef, Path]] = []
    not_downloaded: list[str] = []
    for ref in refs:
        path = local_stub(paystubs, ref)
        if path is None:
            not_downloaded.append(ref.id)
        else:
            stubs.append((ref, path))
    analyzers = {m.name: analyzer_factory(m) for m in models}
    succeeded = failed = 0
    for outcome in run_models(analyzers, stubs):
        save_outcome(results, run_id, outcome)
        if outcome.result is None:
            failed += 1
        else:
            succeeded += 1
    return RunSummary(
        run_id=run_id,
        succeeded=succeeded,
        failed=failed,
        not_downloaded=tuple(not_downloaded),
    )


def load_outcomes(run: Path) -> list[StubOutcome]:
    return [
        StubOutcome.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(run.glob("*/*/*.json"))
    ]


def score_run(run: Path, keys: Path, disputed: frozenset[str]) -> list[StubScore]:
    outcomes = load_outcomes(run)
    if not outcomes:
        raise ConfigError(f"no saved outcomes in {run}")
    scores = []
    for outcome in outcomes:
        key_path = keys / f"{outcome.stub}.json"
        if not key_path.is_file():
            raise ConfigError(f"no answer key for {outcome.stub}")
        scores.append(
            score_outcome(outcome, load_answer_key(key_path), disputed=disputed)
        )
    write_report(scores, run / "report")
    return scores


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    settings = HarnessSettings.from_yaml(args.config)
    paths = settings.paths
    refs = answer_key_refs(paths.answer_keys)
    # Credentials come from the usual AWS chain (e.g. AWS_PROFILE), never from files.
    session = boto3.Session(region_name=settings.aws.region)

    if args.command == "download":
        if settings.s3 is None:
            raise ConfigError("download needs s3 settings in the harness config")
        s3 = session.client("s3", config=boto_config(settings.aws.retries))
        report = download_stubs(
            s3, settings.s3.bucket, settings.s3.stubs_prefix, refs, paths.paystubs
        )
        print(
            f"downloaded {len(report.downloaded)}, already local "
            f"{len(report.already_local)}, missing {len(report.missing)}, "
            f"ambiguous {len(report.ambiguous)}"
        )
        for ref_id in report.missing + report.ambiguous:
            print(f"  not downloaded: {ref_id}")
        return 0

    if args.command == "run":
        config = settings.component
        textract = build_textract(settings.aws, settings.textract)
        store = FileEvidenceStore(paths.ocr_reads)

        def factory(model: ModelSettings) -> Analyzer:
            return PaystubAnalyzer.create(
                component_config_for(config, model),
                genai=build_genai(session, settings.aws, model),
                model=model.model_id,
                readers={"textract": textract},
                store=store,
            )

        run_id = args.run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        summary = run_command(
            select_models(settings, args.models),
            select_stubs(refs, args.stubs),
            paystubs=paths.paystubs,
            results=paths.results,
            run_id=run_id,
            analyzer_factory=factory,
        )
        print(
            f"run {summary.run_id}: {summary.succeeded} succeeded, "
            f"{summary.failed} failed, {len(summary.not_downloaded)} not downloaded"
        )
        return 0

    scores = score_run(
        paths.results / args.run_id,
        paths.answer_keys,
        frozenset(settings.disputed_stubs),
    )
    print(
        f"scored {len(scores)} outcomes; report in {paths.results / args.run_id / 'report'}"
    )
    return 0

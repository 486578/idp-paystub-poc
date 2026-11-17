import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from evaluation.answer_keys import AnswerKey
from evaluation.cli import (
    component_config_for,
    load_outcomes,
    main,
    parse_args,
    run_command,
    score_run,
    select_models,
    select_stubs,
)
from evaluation.download import StubRef
from evaluation.run import StubOutcome
from evaluation.settings import HarnessSettings, ModelSettings
from paystub_agi.config import AnalyzerConfig
from paystub_agi.errors import ConfigError, ExtractionError
from paystub_agi.models import AgiResult, PaystubEvidence, PaystubResult, StubStatus


def _result() -> PaystubResult:
    evidence = PaystubEvidence.model_validate(
        {
            "gross": "1760.00",
            "net": "1299.56",
            "pay_frequency": None,
            "period_start": None,
            "period_end": None,
            "pay_date": None,
            "federal_taxable_wages": None,
            "annual_amount": None,
            "earnings": [],
            "taxes": [],
            "deductions": [],
            "footnotes": [],
        }
    )
    agi = AgiResult(
        agi=Decimal("45760.00"),
        agi_if_review_pretax=Decimal("45760.00"),
        pay_frequency=None,
        frequency_source=None,
        periods_per_year=26,
        method=None,
        one_time_total=Decimal(0),
        pretax_total=Decimal(0),
        review_total=Decimal(0),
        warnings=(),
    )
    return PaystubResult(
        status=StubStatus.OK,
        agi=agi,
        decisions=(),
        flags=(),
        checks_not_run=(),
        evidence=evidence,
        reader="pdfplumber",
        read_from_store=False,
    )


def _key(**overrides: Any) -> AnswerKey:
    values: dict[str, Any] = {
        "schema_version": "1",
        "stub_id": "stub_0006",
        "category": "advs_paystubs",
        "amounts": {"gross": "1760.00", "net": "1299.56"},
        "deductions": [],
        "period": {},
        "calculated": {
            "agi": "45760.00",
            "annual_gross": "45760.00",
            "pay_frequency": "biweekly",
            "periods_per_year": 26,
            "frequency_source": "period_dates",
            "method": "gross_less_pretax",
            "one_time_total": "0",
            "pretax_deductions": "0",
            "warnings": [],
        },
    }
    values.update(overrides)
    return AnswerKey.model_validate(values)


SETTINGS = HarnessSettings.model_validate(
    {
        "aws": {"region": "us-east-1"},
        "s3": {"bucket": "example-bucket"},
        "models": [
            {"name": "opus", "model_id": "us.anthropic.claude-opus-5"},
            {"name": "gpt", "model_id": "openai.gpt-oss-120b-1:0"},
        ],
    }
)
REFS = [
    StubRef(folder="advs_paystubs", stub="stub_0002"),
    StubRef(folder="advs_paystubs", stub="stub_0006"),
    StubRef(folder="generated_scanned", stub="stub01"),
]


# --- arguments and selection ---------------------------------------------------------


def test_eval_cli_parses_run_options() -> None:
    args = parse_args(
        ["run", "--config", "c.yaml", "--models", "opus", "--stubs", "a/b", "c/d"]
    )

    assert (args.command, args.config, args.models, args.stubs) == (
        "run",
        Path("c.yaml"),
        ["opus"],
        ["a/b", "c/d"],
    )


def test_eval_cli_config_defaults_to_the_harness_file() -> None:
    assert parse_args(["download"]).config == Path("evaluation/config.yaml")


def test_eval_cli_score_needs_a_run_id() -> None:
    with pytest.raises(SystemExit):
        parse_args(["score"])


def test_eval_cli_download_without_s3_settings_is_a_config_error(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "aws: {region: us-east-1}\n"
        f"paths: {{answer_keys: '{tmp_path.as_posix()}'}}\n"
        "models: [{name: opus, model_id: us.anthropic.claude-opus-5}]\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="download needs s3"):
        main(["download", "--config", str(config)])


def test_eval_cli_all_models_when_none_named() -> None:
    assert [m.name for m in select_models(SETTINGS, None)] == ["opus", "gpt"]


def test_eval_cli_named_models_only() -> None:
    assert [m.name for m in select_models(SETTINGS, ["gpt"])] == ["gpt"]


def test_eval_cli_unknown_model_is_a_config_error() -> None:
    with pytest.raises(ConfigError, match="sonnet"):
        select_models(SETTINGS, ["sonnet"])


# --- per-model temperature (pilot finding) ------------------------------------------


def test_eval_cli_model_without_temperature_keeps_the_component_setting() -> None:
    model = ModelSettings(name="gpt", model_id="m")

    config = component_config_for(AnalyzerConfig(), model)

    assert config.extraction.temperature == 0


@pytest.mark.parametrize("temperature", [None, 0.0, 0.5])
def test_eval_cli_model_temperature_overrides_the_component(
    temperature: float | None,
) -> None:
    model = ModelSettings(name="opus", model_id="m", temperature=temperature)

    config = component_config_for(AnalyzerConfig(), model)

    assert config.extraction.temperature == temperature
    assert config.extraction.max_output_tokens == 8192
    assert config.rules == AnalyzerConfig().rules


def test_eval_cli_all_stubs_when_none_named() -> None:
    assert select_stubs(REFS, None) == REFS


def test_eval_cli_named_stubs_only_in_given_order() -> None:
    chosen = select_stubs(REFS, ["generated_scanned/stub01", "advs_paystubs/stub_0002"])

    assert [r.id for r in chosen] == [
        "generated_scanned/stub01",
        "advs_paystubs/stub_0002",
    ]


def test_eval_cli_stub_without_a_key_is_a_config_error() -> None:
    with pytest.raises(ConfigError, match="stub99"):
        select_stubs(REFS, ["advs_paystubs/stub99"])


# --- run -----------------------------------------------------------------------------


class FakeAnalyzer:
    def __init__(self, fail: bool = False) -> None:
        self._fail = fail
        self.sources: list[str] = []

    def analyze(self, source: str) -> PaystubResult:
        self.sources.append(source)
        if self._fail:
            raise ExtractionError("bad", code="schema_invalid")
        return _result()


def _local(tmp_path: Path, *refs: StubRef) -> Path:
    for ref in refs:
        path = tmp_path / "paystubs" / ref.folder / f"{ref.stub}.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF")
    return tmp_path / "paystubs"


def test_eval_cli_run_saves_outcomes_and_skips_stubs_not_downloaded(
    tmp_path: Path,
) -> None:
    paystubs = _local(tmp_path, REFS[0], REFS[1])
    made: dict[str, FakeAnalyzer] = {}

    def factory(model: ModelSettings) -> FakeAnalyzer:
        made[model.name] = FakeAnalyzer(fail=model.name == "gpt")
        return made[model.name]

    summary = run_command(
        select_models(SETTINGS, None),
        REFS,
        paystubs=paystubs,
        results=tmp_path / "results",
        run_id="run-1",
        analyzer_factory=factory,
    )

    assert summary.not_downloaded == ("generated_scanned/stub01",)
    assert (summary.succeeded, summary.failed) == (2, 2)
    assert len(made["opus"].sources) == 2
    saved = sorted(
        p.relative_to(tmp_path / "results").as_posix()
        for p in (tmp_path / "results").rglob("*.json")
    )
    assert saved == [
        "run-1/gpt/advs_paystubs/stub_0002.json",
        "run-1/gpt/advs_paystubs/stub_0006.json",
        "run-1/opus/advs_paystubs/stub_0002.json",
        "run-1/opus/advs_paystubs/stub_0006.json",
    ]


# --- score a saved run ---------------------------------------------------------------


def _save(run: Path, outcome: StubOutcome) -> None:
    folder, stub = outcome.stub.split("/")
    path = run / outcome.model / folder / f"{stub}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(outcome.model_dump_json(), encoding="utf-8")


def _write_key(keys: Path, ref: StubRef, **overrides: Any) -> None:
    path = keys / ref.folder / f"{ref.stub}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_key(**overrides).model_dump_json(), encoding="utf-8")


def test_eval_cli_load_outcomes_reads_every_saved_file(tmp_path: Path) -> None:
    run = tmp_path / "run-1"
    first = StubOutcome(model="opus", stub=REFS[0].id, result=_result())
    second = StubOutcome(model="gpt", stub=REFS[1].id, error="ReadingError")
    _save(run, first)
    _save(run, second)
    (run / "report").mkdir()
    (run / "report" / "notes.json").write_text(json.dumps({}), encoding="utf-8")

    assert sorted(load_outcomes(run), key=lambda o: o.model) == [second, first]


def test_eval_cli_score_run_scores_against_the_keys(tmp_path: Path) -> None:
    run, keys = tmp_path / "run-1", tmp_path / "keys"
    _save(run, StubOutcome(model="opus", stub=REFS[1].id, result=_result()))
    _write_key(keys, REFS[1])

    [score] = score_run(run, keys, frozenset())

    assert (score.model, score.stub, score.agi_match) == ("opus", REFS[1].id, True)
    assert (run / "report" / "stubs.csv").is_file()


def test_eval_cli_score_run_without_a_key_is_a_config_error(tmp_path: Path) -> None:
    run = tmp_path / "run-1"
    _save(run, StubOutcome(model="opus", stub=REFS[1].id, result=_result()))

    with pytest.raises(ConfigError, match="stub_0006"):
        score_run(run, tmp_path / "keys", frozenset())


def test_eval_cli_score_run_of_an_empty_folder_is_a_config_error(
    tmp_path: Path,
) -> None:
    with pytest.raises(ConfigError, match="no saved outcomes"):
        score_run(tmp_path / "absent", tmp_path / "keys", frozenset())

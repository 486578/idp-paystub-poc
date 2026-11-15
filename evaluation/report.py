"""Write the scores as CSVs and a short per-model summary (architecture 7).

The files hold stub labels and amounts, so they belong in the git-ignored results folder.
"""

import csv
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from evaluation.score import StubScore

_STUB_COLUMNS = (
    "model",
    "stub",
    "status",
    "error",
    "error_code",
    "our_agi",
    "key_agi",
    "agi_match",
    "agi_difference",
    "field_mismatches",
    "rows_agree",
    "rows_disagree",
    "rows_needs_review",
    "rows_missing",
    "rows_extra",
)
_ROW_COLUMNS = (
    "model",
    "stub",
    "outcome",
    "bucket",
    "direction",
    "rule_id",
    "our_decision",
    "our_label",
    "our_amount",
    "key_type",
    "key_amount",
    "key_pretax",
)


class ModelSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str
    stubs: int
    failed: int
    agi_exact: int
    statuses: dict[str, int]
    outcomes: dict[str, int]
    buckets: dict[str, int]
    field_mismatches: dict[str, int]


def summarize(scores: Sequence[StubScore]) -> list[ModelSummary]:
    models = list(dict.fromkeys(s.model for s in scores))
    summaries = []
    for model in models:
        mine = [s for s in scores if s.model == model]
        rows = [r for s in mine for r in s.rows]
        summaries.append(
            ModelSummary(
                model=model,
                stubs=len(mine),
                failed=sum(s.status == "failed" for s in mine),
                agi_exact=sum(s.agi_match for s in mine),
                statuses=dict(Counter(s.status for s in mine)),
                outcomes=dict(Counter(r.outcome for r in rows)),
                buckets=dict(Counter(r.bucket for r in rows if r.bucket)),
                field_mismatches=dict(
                    Counter(f.name for s in mine for f in s.fields if not f.match)
                ),
            )
        )
    return summaries


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _stub_row(score: StubScore) -> dict[str, str]:
    counts = Counter(r.outcome for r in score.rows)
    values: dict[str, object] = {
        "model": score.model,
        "stub": score.stub,
        "status": score.status,
        "error": score.error,
        "error_code": score.error_code,
        "our_agi": score.our_agi,
        "key_agi": score.key_agi,
        "agi_match": score.agi_match,
        "agi_difference": score.agi_difference,
        "field_mismatches": ";".join(f.name for f in score.fields if not f.match),
        "rows_agree": counts["agree"],
        "rows_disagree": counts["disagree"],
        "rows_needs_review": counts["needs_review"],
        "rows_missing": counts["missing"],
        "rows_extra": counts["extra"],
    }
    return {k: _text(v) for k, v in values.items()}


def _write_csv(path: Path, columns: Sequence[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "none"


def write_report(scores: Sequence[StubScore], folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    _write_csv(folder / "stubs.csv", _STUB_COLUMNS, [_stub_row(s) for s in scores])
    _write_csv(
        folder / "rows.csv",
        _ROW_COLUMNS,
        [
            {"model": s.model, "stub": s.stub}
            | {c: _text(getattr(r, c)) for c in _ROW_COLUMNS[2:]}
            for s in scores
            for r in s.rows
        ],
    )
    lines = [
        "# Evaluation summary",
        "",
        "| Model | Stubs | Failed | AGI exact |",
        "|---|---|---|---|",
    ]
    summaries = summarize(scores)
    lines += [
        f"| {m.model} | {m.stubs} | {m.failed} | {m.agi_exact} |" for m in summaries
    ]
    for m in summaries:
        lines += [
            "",
            f"## {m.model}",
            f"- Status: {_counts(m.statuses)}",
            f"- Deduction rows: {_counts(m.outcomes)}",
            f"- Disagreement buckets: {_counts(m.buckets)}",
            f"- Field mismatches: {_counts(m.field_mismatches)}",
        ]
    (folder / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

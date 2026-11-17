"""Write the scores as CSVs and a short per-model summary (architecture 7).

The files hold stub labels and amounts, so they belong in the git-ignored results folder.
"""

import csv
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from evaluation.score import RowScore, StubScore
from paystub_agi.models import Decision

_OVERVIEW_COLUMNS = (
    "model",
    "stub",
    "result",
    "our_agi",
    "key_agi",
    "difference",
    "why",
)
# Only these field differences can change AGI.
_AGI_FIELDS = {
    "gross": "Gross",
    "one_time_total": "One-time pay",
    "period_start": "Period start",
    "period_end": "Period end",
}

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


def _words(decision: Decision | None) -> str:
    text = "none" if decision is None else decision.value.replace("_", " ")
    return text.replace("pretax", "pre-tax")


def _row_reason(row: RowScore) -> str | None:
    label = f'"{row.our_label}" {row.our_amount}'
    if row.outcome == "disagree":
        key = "pre-tax" if row.key_pretax else "not pre-tax"
        return f"{label}: ours {_words(row.our_decision)} ({row.rule_id}), key {key}"
    if row.outcome == "needs_review":
        return f"{label}: sent to review"
    if row.outcome == "missing" and row.key_pretax:
        return f"Missing pre-tax deduction: key {row.key_type} {row.key_amount}"
    if row.outcome == "extra" and row.our_decision is Decision.PRETAX:
        return f"Extra row counted pre-tax: {label}"
    return None


def explain(score: StubScore) -> tuple[str, str]:
    """The result in one word, and the likely cause of an AGI difference in plain words."""
    if score.status == "failed":
        code = f" ({score.error_code})" if score.error_code else ""
        return "failed", f"{score.error}{code}"
    if score.our_agi is None and score.key_agi is None:
        return "both_empty", "Neither we nor the key have an AGI"
    if score.agi_match:
        return "match", ""
    reasons = [r for r in map(_row_reason, score.rows) if r]
    reasons += [
        f"{_AGI_FIELDS[f.name]} differs: ours {f.ours or 'none'}, key {f.key or 'none'}"
        for f in score.fields
        if not f.match and f.name in _AGI_FIELDS
    ]
    if score.agi_method == "federal_taxable_wages":
        reasons.append("Ours starts from the printed federal taxable wages")
    if score.our_agi is None:
        reasons.insert(0, f"We have no AGI (status {score.status})")
    return "mismatch", "; ".join(reasons) or "No row or field difference found"


def _overview_row(score: StubScore) -> dict[str, str]:
    result, why = explain(score)
    values: dict[str, object] = {
        "model": score.model,
        "stub": score.stub,
        "result": result,
        "our_agi": score.our_agi,
        "key_agi": score.key_agi,
        "difference": score.agi_difference,
        "why": why,
    }
    return {k: _text(v) for k, v in values.items()}


def _cell(value: str) -> str:
    return value.replace("|", "\\|")


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
    overview = [_overview_row(s) for s in scores]
    _write_csv(folder / "overview.csv", _OVERVIEW_COLUMNS, overview)
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
        mine = [r for r in overview if r["model"] == m.model]
        off = [r for r in mine if r["result"] == "mismatch"]
        if off:
            lines += [
                "",
                "### AGI mismatches",
                "",
                "| Stub | Our AGI | Key AGI | Difference | Why |",
                "|---|---|---|---|---|",
            ]
            lines += [
                f"| {r['stub']} | {r['our_agi']} | {r['key_agi']} | {r['difference']} "
                f"| {_cell(r['why'])} |"
                for r in off
            ]
        failed = [r for r in mine if r["result"] == "failed"]
        if failed:
            lines += ["", "### Failed", "", "| Stub | Error |", "|---|---|"]
            lines += [f"| {r['stub']} | {_cell(r['why'])} |" for r in failed]
    (folder / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

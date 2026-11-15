"""Run each model over each stub; record failures and keep going (DL-040, DL-041).

Only the component's own errors are recorded as failures. Anything else (e.g.
expired credentials) stops the run, because every later stub would fail the same way.
"""

import re
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from evaluation.download import StubRef
from paystub_agi.errors import PaystubAgiError
from paystub_agi.models import PaystubResult

_RUN_ID = re.compile(r"[A-Za-z0-9_-]+")


class Analyzer(Protocol):
    def analyze(self, source: str) -> PaystubResult: ...


class StubOutcome(BaseModel):
    """One model on one stub: a result, or the error that stopped it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Both become folder names when saved.
    model: str = Field(pattern=r"^[a-z0-9_-]+$")
    stub: str = Field(pattern=r"^[A-Za-z0-9_-]+/[A-Za-z0-9_-]+$")
    result: PaystubResult | None = None
    error: str | None = None
    error_code: str | None = None
    message: str | None = None

    @model_validator(mode="after")
    def _result_or_error(self) -> Self:
        if (self.result is None) == (self.error is None):
            raise ValueError("an outcome has either a result or an error")
        return self


def run_models(
    analyzers: Mapping[str, Analyzer], stubs: Sequence[tuple[StubRef, Path]]
) -> Iterator[StubOutcome]:
    for model, analyzer in analyzers.items():
        for ref, path in stubs:
            try:
                result = analyzer.analyze(str(path))
            except PaystubAgiError as exc:
                yield StubOutcome(
                    model=model,
                    stub=ref.id,
                    error=type(exc).__name__,
                    error_code=getattr(exc, "code", None),
                    message=str(exc),
                )
                continue
            yield StubOutcome(model=model, stub=ref.id, result=result)


def save_outcome(results: Path, run_id: str, outcome: StubOutcome) -> Path:
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("a run id may only contain letters, digits, '_' and '-'")
    folder, _, stub = outcome.stub.partition("/")
    path = results / run_id / outcome.model / folder / f"{stub}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(outcome.model_dump_json(indent=2), encoding="utf-8")
    return path

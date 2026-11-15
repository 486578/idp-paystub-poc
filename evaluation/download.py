"""Download the stub files that have an answer key, once, into a local folder.

S3 layout: <prefix><folder>/<stub>.<ext>; local copy: <paystubs>/<folder>/<stub>.<ext>.
"""

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

SUPPORTED = (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff")
_SAFE = r"^[A-Za-z0-9_-]+$"


class StubRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # Safe characters only, because both become local path parts.
    folder: str = Field(pattern=_SAFE)
    stub: str = Field(pattern=_SAFE)

    @property
    def id(self) -> str:
        return f"{self.folder}/{self.stub}"


class DownloadReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    downloaded: tuple[str, ...]
    already_local: tuple[str, ...]
    missing: tuple[str, ...]
    ambiguous: tuple[str, ...]


class S3Client(Protocol):
    def list_objects_v2(self, **kwargs: Any) -> dict[str, Any]: ...

    def download_file(self, Bucket: str, Key: str, Filename: str) -> None: ...  # noqa: N803


def answer_key_refs(keys_folder: Path) -> list[StubRef]:
    return sorted(
        (
            StubRef(folder=p.parent.name, stub=p.stem)
            for p in keys_folder.glob("*/*.json")
        ),
        key=lambda ref: ref.id,
    )


def local_stub(paystubs: Path, ref: StubRef) -> Path | None:
    for ext in SUPPORTED:
        path = paystubs / ref.folder / f"{ref.stub}{ext}"
        if path.is_file():
            return path
    return None


def _listing(s3: S3Client, bucket: str, prefix: str) -> Iterator[str]:
    token: dict[str, str] = {}
    while True:
        reply = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, **token)
        yield from (item["Key"] for item in reply.get("Contents", []))
        if not reply.get("IsTruncated"):
            return
        token = {"ContinuationToken": reply["NextContinuationToken"]}


def download_stubs(
    s3: S3Client,
    bucket: str,
    prefix: str,
    refs: Sequence[StubRef],
    paystubs: Path,
) -> DownloadReport:
    wanted = {ref.id: ref for ref in refs}
    found: dict[str, list[str]] = {ref_id: [] for ref_id in wanted}
    for key in _listing(s3, bucket, prefix):
        rest = Path(key[len(prefix) :])
        ref_id = f"{rest.parent.as_posix()}/{rest.stem}"
        if rest.suffix.lower() in SUPPORTED and ref_id in found:
            found[ref_id].append(key)
    downloaded, already, missing, ambiguous = [], [], [], []
    for ref_id, keys in found.items():
        ref = wanted[ref_id]
        if local_stub(paystubs, ref) is not None:
            already.append(ref_id)
        elif not keys:
            missing.append(ref_id)
        elif len(keys) > 1:
            ambiguous.append(ref_id)
        else:
            target = paystubs / ref.folder / f"{ref.stub}{Path(keys[0]).suffix.lower()}"
            target.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(Bucket=bucket, Key=keys[0], Filename=str(target))
            downloaded.append(ref_id)
    return DownloadReport(
        downloaded=tuple(downloaded),
        already_local=tuple(already),
        missing=tuple(missing),
        ambiguous=tuple(ambiguous),
    )

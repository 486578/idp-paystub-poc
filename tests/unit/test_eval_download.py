from pathlib import Path
from typing import Any

import pytest

from evaluation.download import (
    StubRef,
    answer_key_refs,
    download_stubs,
    local_stub,
)

PREFIX = "datasets/pay_stubs/paystubs/"


class FakeS3:
    """list_objects_v2 in pages of `page_size`; download_file writes the key."""

    def __init__(self, keys: list[str], page_size: int = 1000) -> None:
        self._keys = keys
        self._page_size = page_size
        self.listed: list[dict[str, Any]] = []
        self.downloads: list[str] = []

    def list_objects_v2(self, **kwargs: Any) -> dict[str, Any]:
        self.listed.append(kwargs)
        start = int(kwargs.get("ContinuationToken", "0"))
        page = [k for k in self._keys if k.startswith(kwargs["Prefix"])][
            start : start + self._page_size
        ]
        end = start + len(page)
        more = end < len([k for k in self._keys if k.startswith(kwargs["Prefix"])])
        reply: dict[str, Any] = {
            "Contents": [{"Key": k} for k in page],
            "IsTruncated": more,
        }
        if more:
            reply["NextContinuationToken"] = str(end)
        return reply

    def download_file(self, Bucket: str, Key: str, Filename: str) -> None:  # noqa: N803
        self.downloads.append(Key)
        Path(Filename).write_bytes(Key.encode())


def _keys(tmp_path: Path, *refs: str) -> Path:
    folder = tmp_path / "answer_keys"
    for ref in refs:
        path = folder / f"{ref}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
    return folder


def test_eval_download_answer_key_refs_are_sorted_folder_and_stub(
    tmp_path: Path,
) -> None:
    keys = _keys(tmp_path, "generated_scanned/stub02", "advs_paystubs/stub_0006")
    (keys / "advs_paystubs" / "notes.txt").write_text("x", encoding="utf-8")

    assert answer_key_refs(keys) == [
        StubRef(folder="advs_paystubs", stub="stub_0006"),
        StubRef(folder="generated_scanned", stub="stub02"),
    ]


def test_eval_download_stub_ref_id() -> None:
    assert StubRef(folder="advs_paystubs", stub="stub_0006").id == (
        "advs_paystubs/stub_0006"
    )


def test_eval_download_gets_only_stubs_with_a_key(tmp_path: Path) -> None:
    refs = [StubRef(folder="advs_paystubs", stub="stub_0006")]
    s3 = FakeS3(
        [
            PREFIX + "advs_paystubs/stub_0006.pdf",
            PREFIX + "advs_paystubs/stub_9999.pdf",
        ]
    )

    report = download_stubs(s3, "bucket", PREFIX, refs, tmp_path / "paystubs")

    assert s3.downloads == [PREFIX + "advs_paystubs/stub_0006.pdf"]
    assert report.downloaded == ("advs_paystubs/stub_0006",)
    assert (tmp_path / "paystubs" / "advs_paystubs" / "stub_0006.pdf").is_file()


def test_eval_download_skips_stubs_already_local(tmp_path: Path) -> None:
    local = tmp_path / "paystubs" / "advs_paystubs" / "stub_0006.pdf"
    local.parent.mkdir(parents=True)
    local.write_bytes(b"%PDF")
    s3 = FakeS3([PREFIX + "advs_paystubs/stub_0006.pdf"])
    refs = [StubRef(folder="advs_paystubs", stub="stub_0006")]

    report = download_stubs(s3, "bucket", PREFIX, refs, tmp_path / "paystubs")

    assert s3.downloads == []
    assert report.already_local == ("advs_paystubs/stub_0006",)


def test_eval_download_reports_keys_without_a_stub_file(tmp_path: Path) -> None:
    refs = [StubRef(folder="generated_scanned", stub="stub01")]

    report = download_stubs(FakeS3([]), "bucket", PREFIX, refs, tmp_path)

    assert report.missing == ("generated_scanned/stub01",)


@pytest.mark.parametrize("ext", [".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"])
def test_eval_download_accepts_supported_file_types(tmp_path: Path, ext: str) -> None:
    s3 = FakeS3([PREFIX + f"generated_scanned/stub01{ext}"])
    refs = [StubRef(folder="generated_scanned", stub="stub01")]

    download_stubs(s3, "bucket", PREFIX, refs, tmp_path)

    assert (tmp_path / "generated_scanned" / f"stub01{ext}").is_file()


def test_eval_download_ignores_other_file_types_and_deeper_paths(
    tmp_path: Path,
) -> None:
    s3 = FakeS3(
        [
            PREFIX + "generated_scanned/stub01.json",
            PREFIX + "generated_scanned/old/stub01.pdf",
        ]
    )
    refs = [StubRef(folder="generated_scanned", stub="stub01")]

    report = download_stubs(s3, "bucket", PREFIX, refs, tmp_path)

    assert (s3.downloads, report.missing) == ([], ("generated_scanned/stub01",))


def test_eval_download_two_files_for_one_stub_is_ambiguous(tmp_path: Path) -> None:
    s3 = FakeS3(
        [
            PREFIX + "generated_scanned/stub01.pdf",
            PREFIX + "generated_scanned/stub01.png",
        ]
    )
    refs = [StubRef(folder="generated_scanned", stub="stub01")]

    report = download_stubs(s3, "bucket", PREFIX, refs, tmp_path)

    assert (s3.downloads, report.ambiguous) == ([], ("generated_scanned/stub01",))


def test_eval_download_reads_every_page_of_the_listing(tmp_path: Path) -> None:
    keys = [PREFIX + f"generated_scanned/stub{n:02}.pdf" for n in range(1, 6)]
    refs = [StubRef(folder="generated_scanned", stub=f"stub{n:02}") for n in (1, 5)]
    s3 = FakeS3(keys, page_size=2)

    report = download_stubs(s3, "bucket", PREFIX, refs, tmp_path)

    assert len(s3.listed) == 3
    assert report.downloaded == ("generated_scanned/stub01", "generated_scanned/stub05")


def test_eval_download_local_stub_finds_the_file(tmp_path: Path) -> None:
    path = tmp_path / "generated_scanned" / "stub01.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"png")

    ref = StubRef(folder="generated_scanned", stub="stub01")

    assert local_stub(tmp_path, ref) == path
    assert local_stub(tmp_path, StubRef(folder="x", stub="y")) is None

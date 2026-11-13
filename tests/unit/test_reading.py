from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

import pytest
from idp_core.exceptions import InvalidInputError, UnsupportedInputError
from idp_core.models import (
    BoundingBox,
    CallMetrics,
    Document,
    Line,
    Page,
    PageLayout,
    ReaderCapabilities,
    ReaderResult,
    ReadRequest,
    ReadResult,
    Table,
    TableCell,
    Word,
)
from idp_ocr import PageImage as LibraryPageImage
from idp_ocr import S3Downloader

from paystub_agi.config import ReadingConfig
from paystub_agi.errors import ConfigError, ReadingError
from paystub_agi.reading import IdpOcrStubReader, document_text

# --- building idp-core evidence by hand ---------------------------------------------


def _box(left: float, top: float, right: float, bottom: float) -> BoundingBox:
    return BoundingBox(left=left, top=top, right=right, bottom=bottom)


def _word(text: str, left: float, top: float, page: int = 1) -> Word:
    return Word(
        text=text,
        bbox=_box(left, top, left + 40.0, top + 10.0),
        page_number=page,
    )


def _page(
    number: int = 1,
    words: Sequence[Word] = (),
    lines: Sequence[Line] = (),
    tables: Sequence[Table] = (),
) -> Page:
    layout = (
        PageLayout(lines=tuple(lines), tables=tuple(tables))
        if (lines or tables)
        else None
    )
    return Page(
        page_number=number,
        width=612.0,
        height=792.0,
        words=tuple(words),
        layout=layout,
    )


def _line(*words: Word) -> Line:
    return Line(
        page_number=words[0].page_number,
        bbox=_box(words[0].bbox.left, words[0].bbox.top, 600.0, words[0].bbox.bottom),
        words=words,
    )


def _cell(row: int, column: int, text: str, header: bool = False) -> TableCell:
    return TableCell(
        row=row,
        column=column,
        text=text,
        bbox=_box(10.0 * column, 10.0 * row, 10.0 * column + 9.0, 10.0 * row + 9.0),
        is_header=header,
    )


def _table(rows: int, columns: int, cells: Sequence[TableCell], page: int = 1) -> Table:
    return Table(
        page_number=page,
        bbox=_box(0.0, 0.0, 300.0, 300.0),
        rows=rows,
        columns=columns,
        cells=tuple(cells),
    )


def _document(*pages: Page, document_id: str = "doc") -> Document:
    return Document(document_id=document_id, pages=pages)


# --- document_text ---------------------------------------------------------------------


def test_reading_text_keeps_ocr_lines_in_order() -> None:
    page = _page(
        lines=[
            _line(_word("Gross", 10.0, 100.0), _word("Pay", 60.0, 100.0)),
            _line(_word("Net", 10.0, 120.0), _word("Pay", 60.0, 120.0)),
        ]
    )

    assert document_text(_document(page)) == "--- Page 1 ---\nGross Pay\nNet Pay"


def test_reading_text_groups_words_into_lines_when_no_lines_given() -> None:
    page = _page(
        words=[
            _word("Pay", 60.0, 101.0),
            _word("Net", 10.0, 120.0),
            _word("Gross", 10.0, 100.0),
            _word("Pay", 60.0, 120.0),
        ]
    )

    assert document_text(_document(page)) == "--- Page 1 ---\nGross Pay\nNet Pay"


def test_reading_text_writes_tables_as_grids_with_header_first() -> None:
    table = _table(
        2,
        2,
        [
            _cell(2, 1, "Medical"),
            _cell(1, 1, "Deduction", header=True),
            _cell(1, 2, "Current", header=True),
            _cell(2, 2, "85.00"),
        ],
    )
    page = _page(words=[_word("Deductions", 10.0, 50.0)], tables=[table])

    assert document_text(_document(page)) == (
        "--- Page 1 ---\n"
        "Deductions\n"
        "[Table 1]\n"
        "| Deduction | Current |\n"
        "| Medical | 85.00 |"
    )


def test_reading_text_leaves_missing_table_cells_empty() -> None:
    table = _table(1, 3, [_cell(1, 1, "Medical"), _cell(1, 3, "85.00")])

    text = document_text(_document(_page(tables=[table])))

    assert text.endswith("| Medical |  | 85.00 |")


def test_reading_text_keeps_pages_in_order() -> None:
    first = _page(1, words=[_word("One", 10.0, 10.0)])
    second = _page(2, words=[_word("Two", 10.0, 10.0, page=2)])

    assert document_text(_document(first, second)) == (
        "--- Page 1 ---\nOne\n--- Page 2 ---\nTwo"
    )


def test_reading_text_of_empty_page_is_just_the_page_header() -> None:
    assert document_text(_document(_page())) == "--- Page 1 ---"


def test_reading_text_of_document_without_pages_is_empty() -> None:
    assert document_text(_document()) == ""


# --- stand-in readers --------------------------------------------------------------------


class _FakeReader:
    """Implements idp-core's Reader protocol with a fixed outcome."""

    capabilities = ReaderCapabilities(
        media_types=("application/pdf",), features=("words", "tables")
    )

    def __init__(
        self,
        name: str,
        *,
        status: Literal["succeeded", "partial", "failed"] = "succeeded",
        words: Sequence[str] = ("Pay",),
    ) -> None:
        self.name = name
        self._status = status
        self._words = words
        self.calls = 0

    def read(self, request: ReadRequest) -> ReaderResult:
        self.calls += 1
        words = tuple(
            _word(text, 10.0 + 50.0 * i, 10.0) for i, text in enumerate(self._words)
        )
        pages = (_page(1, words=words),) if self._status != "failed" else ()
        document = Document(document_id=request.context.document_id, pages=pages)
        error: Literal["no_evidence", "incomplete_read"] | None = None
        if self._status == "failed":
            error = "no_evidence"
        elif self._status == "partial":
            error = "incomplete_read"
        return ReaderResult(
            reader=self.name,
            result=ReadResult(status=self._status, document=document, error_code=error),
            metrics=CallMetrics(context=request.context, duration_ms=0.0),
        )


class _FakeRenderer:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        path: Path,
        pages: Sequence[int] | None = None,
        *,
        dpi: int,
        max_side: int,
        grayscale: bool,
    ) -> tuple[LibraryPageImage, ...]:
        self.calls.append(
            {
                "path": path,
                "pages": tuple(pages or ()),
                "dpi": dpi,
                "max_side": max_side,
                "grayscale": grayscale,
            }
        )
        return tuple(LibraryPageImage(n, "image/png", b"png") for n in pages or ())


class _FakeDownloader:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def download(self, bucket: str, key: str, path: Path) -> None:
        self.calls.append((bucket, key))
        path.write_bytes(b"%PDF-1.4")


class _RecordingDownloader:
    def __init__(self) -> None:
        self.paths: list[Path] = []

    def download(self, bucket: str, key: str, path: Path) -> None:
        self.paths.append(path)


class _FailingDownloader:
    def download(self, bucket: str, key: str, path: Path) -> None:
        raise InvalidInputError("could not download")


@pytest.fixture()
def pdf(tmp_path: Path) -> Path:
    path = tmp_path / "stub.pdf"
    path.write_bytes(b"%PDF-1.4")
    return path


def _reader(
    strategy: Sequence[str] = ("pdfplumber", "textract"),
    *,
    readers: Mapping[str, _FakeReader] | None = None,
    renderer: _FakeRenderer | None = None,
    downloader: S3Downloader | None = None,
    **config: Any,
) -> IdpOcrStubReader:
    supplied = readers if readers is not None else {n: _FakeReader(n) for n in strategy}
    return IdpOcrStubReader(
        ReadingConfig.model_validate({"strategy": list(strategy), **config}),
        readers=supplied,
        renderer=renderer or _FakeRenderer(),
        downloader=downloader,
    )


# --- strategy: readers in the order listed -----------------------------------------


def test_reading_stops_at_the_first_good_read(pdf: Path) -> None:
    textract = _FakeReader("textract")
    readers = {"pdfplumber": _FakeReader("pdfplumber"), "textract": textract}

    stub = _reader(readers=readers).read(str(pdf), images=False)

    assert stub.reader == "pdfplumber"
    assert textract.calls == 0


def test_reading_falls_back_when_a_read_is_incomplete(pdf: Path) -> None:
    readers = {
        "pdfplumber": _FakeReader("pdfplumber", status="partial"),
        "textract": _FakeReader("textract"),
    }

    stub = _reader(readers=readers).read(str(pdf), images=False)

    assert stub.reader == "textract"


def test_reading_three_readers_are_tried_in_listed_order(pdf: Path) -> None:
    readers = {
        "pdfplumber": _FakeReader("pdfplumber", status="partial"),
        "textract": _FakeReader("textract", status="failed"),
        "other_ocr": _FakeReader("other_ocr"),
    }

    stub = _reader(("pdfplumber", "textract", "other_ocr"), readers=readers).read(
        str(pdf), images=False
    )

    assert stub.reader == "other_ocr"
    assert [r.calls for r in readers.values()] == [1, 1, 1]


def test_reading_list_order_decides_which_reader_goes_first(pdf: Path) -> None:
    readers = {
        "pdfplumber": _FakeReader("pdfplumber"),
        "textract": _FakeReader("textract"),
    }

    stub = _reader(("textract", "pdfplumber"), readers=readers).read(
        str(pdf), images=False
    )

    assert (stub.reader, readers["pdfplumber"].calls) == ("textract", 0)


def test_reading_supplied_readers_not_listed_never_run(pdf: Path) -> None:
    readers = {
        "pdfplumber": _FakeReader("pdfplumber"),
        "textract": _FakeReader("textract"),
    }

    stub = _reader(("pdfplumber",), readers=readers).read(str(pdf), images=False)

    assert (stub.reader, readers["textract"].calls) == ("pdfplumber", 0)


def test_reading_free_reader_only_raises_on_a_scan_instead_of_paying(
    pdf: Path,
) -> None:
    readers = {"pdfplumber": _FakeReader("pdfplumber", status="partial")}

    with pytest.raises(ReadingError, match="incomplete_read") as error:
        _reader(("pdfplumber",), readers=readers).read(str(pdf), images=False)

    assert error.value.code == "incomplete_read"


def test_reading_listed_reader_not_supplied_is_a_config_error() -> None:
    with pytest.raises(ConfigError, match="textract"):
        _reader(("pdfplumber", "textract"), readers={})


def test_reading_pdfplumber_is_built_in_when_not_supplied() -> None:
    config = ReadingConfig(strategy=("pdfplumber",))

    IdpOcrStubReader(config)


def test_reading_every_reader_failing_raises_with_code(pdf: Path) -> None:
    readers = {
        "pdfplumber": _FakeReader("pdfplumber", status="failed"),
        "textract": _FakeReader("textract", status="failed"),
    }

    with pytest.raises(ReadingError) as error:
        _reader(readers=readers).read(str(pdf), images=False)

    assert error.value.code == "no_evidence"


# --- result content -----------------------------------------------------------------------


def test_reading_result_holds_document_and_text(pdf: Path) -> None:
    readers = {
        "pdfplumber": _FakeReader("pdfplumber", words=("Gross", "Pay")),
        "textract": _FakeReader("textract"),
    }

    stub = _reader(readers=readers).read(str(pdf), images=False)

    assert stub.text == "--- Page 1 ---\nGross Pay"
    assert [p.page_number for p in stub.document.pages] == [1]


def test_reading_without_images_does_not_render(pdf: Path) -> None:
    renderer = _FakeRenderer()

    stub = _reader(renderer=renderer).read(str(pdf), images=False)

    assert (stub.images, renderer.calls) == ((), [])


def test_reading_with_images_renders_with_configured_settings(pdf: Path) -> None:
    renderer = _FakeRenderer()
    reader = _reader(
        renderer=renderer,
        image_dpi=200,
        image_max_side=1000,
        grayscale=False,
    )

    stub = reader.read(str(pdf), images=True)

    assert renderer.calls == [
        {"path": pdf, "pages": (1,), "dpi": 200, "max_side": 1000, "grayscale": False}
    ]
    assert [(i.page_number, i.media_type, i.data) for i in stub.images] == [
        (1, "image/png", b"png")
    ]


class _ThreePageReader(_FakeReader):
    def read(self, request: ReadRequest) -> ReaderResult:
        result = super().read(request)
        pages = tuple(
            _page(n, words=[_word("Pay", 10.0, 10.0, page=n)]) for n in (1, 2, 3)
        )
        document = Document(document_id=request.context.document_id, pages=pages)
        return result.model_copy(
            update={"result": ReadResult(status="succeeded", document=document)}
        )


def test_reading_renders_at_most_max_images_pages(pdf: Path) -> None:
    renderer = _FakeRenderer()
    reader = _reader(
        readers={
            "pdfplumber": _ThreePageReader("pdfplumber"),
            "textract": _FakeReader("textract"),
        },
        renderer=renderer,
        max_images=2,
    )

    reader.read(str(pdf), images=True)

    assert renderer.calls[0]["pages"] == (1, 2)


# --- sources -------------------------------------------------------------------------------


def test_reading_missing_local_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ReadingError, match="not found"):
        _reader().read(str(tmp_path / "absent.pdf"), images=False)


def test_reading_s3_source_is_downloaded_then_read(tmp_path: Path) -> None:
    downloader = _FakeDownloader()
    renderer = _FakeRenderer()
    reader = _reader(downloader=downloader, renderer=renderer)

    stub = reader.read("s3://my-bucket/stubs/stub_0006.pdf", images=True)

    assert downloader.calls == [("my-bucket", "stubs/stub_0006.pdf")]
    assert stub.reader == "pdfplumber"
    rendered = renderer.calls[0]["path"]
    assert rendered.suffix == ".pdf"
    assert not rendered.exists()


@pytest.mark.parametrize("key", ["stubs/..", "..", "a/../../evil.pdf"])
def test_reading_s3_key_cannot_choose_where_the_file_is_written(
    tmp_path: Path, key: str
) -> None:
    downloader = _RecordingDownloader()
    reader = _reader(downloader=downloader)

    try:
        reader.read(f"s3://bucket/{key}", images=False)
    except ReadingError:
        pass

    written = downloader.paths[0]
    assert written.name.startswith("paystub")
    assert ".." not in written.parts


def test_reading_s3_download_library_error_is_wrapped() -> None:
    reader = _reader(downloader=_FailingDownloader())

    with pytest.raises(ReadingError) as error:
        reader.read("s3://bucket/stub.pdf", images=False)

    assert isinstance(error.value.__cause__, InvalidInputError)


def test_reading_s3_source_without_downloader_raises() -> None:
    with pytest.raises(ReadingError, match="downloader"):
        _reader().read("s3://my-bucket/stub.pdf", images=False)


@pytest.mark.parametrize(
    "source", ["s3://", "s3://bucket", "s3://bucket/", "s3:///key"]
)
def test_reading_malformed_s3_uri_raises(source: str) -> None:
    with pytest.raises(ReadingError, match="s3://bucket/key"):
        _reader(downloader=_FakeDownloader()).read(source, images=False)


def test_reading_library_error_is_wrapped(tmp_path: Path) -> None:
    path = tmp_path / "stub.docx"
    path.write_bytes(b"x")

    with pytest.raises(ReadingError) as error:
        _reader().read(str(path), images=False)

    assert isinstance(error.value.__cause__, UnsupportedInputError)


# --- config -------------------------------------------------------------------------------


def test_reading_config_defaults() -> None:
    config = ReadingConfig()

    assert (
        config.strategy,
        config.max_images,
        config.image_dpi,
        config.image_max_side,
        config.grayscale,
    ) == (("pdfplumber", "textract"), 3, 144, 1568, True)


def test_reading_config_strategy_accepts_any_number_of_names() -> None:
    names = ("pdfplumber", "textract", "other_ocr")

    assert ReadingConfig(strategy=names).strategy == names


@pytest.mark.parametrize(
    "bad",
    [
        {"strategy": []},
        {"strategy": "pdfplumber"},
        {"strategy": ["textract", "textract"]},
        {"strategy": ["Textract!"]},
        {"strategy": [""]},
        {"max_images": 0},
        {"image_dpi": 35},
        {"image_dpi": 601},
        {"image_max_side": 99},
    ],
)
def test_reading_config_rejects_bad_values(bad: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        ReadingConfig.model_validate(bad)

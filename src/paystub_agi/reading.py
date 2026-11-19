"""Read a paystub with idp-ocr (architecture section 5, step 2).

Produces the OCR document, a plain-text rendering for the model and the grounding
check, and page images only when asked. Nothing here interprets the content.
"""

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Literal, Protocol

from idp_core.contracts import Reader
from idp_core.exceptions import IdpError, UnsupportedInputError
from idp_core.models import (
    Document,
    Page,
    ReaderCapabilities,
    ReaderResult,
    ReadRequest,
    Table,
    Word,
)
from idp_ocr import PageImage as LibraryPageImage
from idp_ocr import PdfPlumberReader, S3Downloader, read_document, render_pages
from pydantic import BaseModel, ConfigDict, Field, PositiveInt

from paystub_agi.config import ReadingConfig
from paystub_agi.errors import ConfigError, ReadingError

# Only what the free digital reader supports; asking for more would skip it.
_FEATURES: tuple[Literal["words", "tables"], ...] = ("words", "tables")
_S3 = "s3://"
# Free, local readers the component can build itself; paid ones come from the caller.
_BUILT_IN: dict[str, Callable[[], Reader]] = {"pdfplumber": PdfPlumberReader}


class PageImage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    page_number: PositiveInt
    media_type: str
    data: bytes = Field(repr=False)


class ReadStub(BaseModel):
    """Everything later steps need from the read. Never log `text` or `images`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(repr=False)
    reader: str
    # Page numbers read, so page images can be rendered again later.
    pages: tuple[PositiveInt, ...]
    images: tuple[PageImage, ...] = Field(repr=False)


class StubReader(Protocol):
    def local_copy(self, source: str) -> AbstractContextManager[Path]: ...

    def read_file(self, path: Path, *, images: bool) -> ReadStub: ...

    def render(self, path: Path, pages: Sequence[int]) -> tuple[PageImage, ...]: ...


class AutoTextractReader:
    """Sync Textract first; the staged (async, S3) reader only for what sync refuses.

    The caller builds both readers, e.g. `TextractReader(region=...)` and
    `TextractReader(region=..., staging_bucket=...)` (DL-051).
    """

    def __init__(self, sync: Reader, staged: Reader) -> None:
        self._sync = sync
        self._staged = staged

    @property
    def name(self) -> str:
        return str(getattr(self._sync, "name", "textract"))

    @property
    def capabilities(self) -> ReaderCapabilities:
        return self._sync.capabilities

    def read(self, request: ReadRequest) -> ReaderResult:
        try:
            return self._sync.read(request)
        except UnsupportedInputError:
            # Sync refuses multi-page PDFs before calling AWS.
            return self._staged.read(request)


class Renderer(Protocol):
    def __call__(
        self,
        path: Path,
        pages: Sequence[int] | None = None,
        *,
        dpi: int,
        max_side: int,
        grayscale: bool,
    ) -> tuple[LibraryPageImage, ...]: ...


# --- text ----------------------------------------------------------------------------


def _grouped_lines(words: Sequence[Word]) -> list[str]:
    """Words on the same height form a line, read left to right."""
    lines: list[list[Word]] = []
    for word in sorted(words, key=lambda w: (w.bbox.top, w.bbox.left)):
        middle = (word.bbox.top + word.bbox.bottom) / 2
        if lines and lines[-1][0].bbox.top <= middle <= lines[-1][0].bbox.bottom:
            lines[-1].append(word)
        else:
            lines.append([word])
    return [
        " ".join(w.text for w in sorted(line, key=lambda w: w.bbox.left))
        for line in lines
    ]


def _page_lines(page: Page) -> list[str]:
    if page.layout is not None and page.layout.lines:
        return [" ".join(w.text for w in line.words) for line in page.layout.lines]
    return _grouped_lines(page.words)


def _table_rows(table: Table) -> list[str]:
    grid = {(cell.row, cell.column): cell.text for cell in table.cells}
    return [
        "| "
        + " | ".join(
            grid.get((row, column), "") for column in range(1, table.columns + 1)
        )
        + " |"
        for row in range(1, table.rows + 1)
    ]


def document_text(document: Document) -> str:
    """Plain text in reading order: each page's lines, then its tables as grids."""
    parts: list[str] = []
    tables = 0
    for page in document.pages:
        parts.append(f"--- Page {page.page_number} ---")
        parts.extend(_page_lines(page))
        for table in page.layout.tables if page.layout is not None else ():
            tables += 1
            parts.append(f"[Table {tables}]")
            parts.extend(_table_rows(table))
    return "\n".join(parts)


# --- reading -----------------------------------------------------------------------


def _s3_location(source: str) -> tuple[str, str]:
    bucket, _, key = source[len(_S3) :].partition("/")
    if not bucket or not key:
        raise ReadingError("an S3 source must look like s3://bucket/key")
    return bucket, key


def _local_name(key: str) -> str:
    # Only the extension comes from the key, so the key can't choose the location.
    suffix = PurePosixPath(key).suffix.lower()
    return "paystub" + (suffix if suffix[1:].isalnum() else "")


class IdpOcrStubReader:
    """Reads with idp-ocr. The caller supplies the readers by name and any downloader."""

    def __init__(
        self,
        config: ReadingConfig,
        *,
        readers: Mapping[str, Reader] | None = None,
        downloader: S3Downloader | None = None,
        renderer: Renderer = render_pages,
    ) -> None:
        supplied = dict(readers or {})
        missing = [
            n for n in config.strategy if n not in supplied and n not in _BUILT_IN
        ]
        if missing:
            raise ConfigError(
                "reading strategy lists readers that weren't supplied: "
                + ", ".join(missing)
            )
        self._readers = tuple(
            supplied[name] if name in supplied else _BUILT_IN[name]()
            for name in config.strategy
        )
        self._config = config
        self._downloader = downloader
        self._renderer = renderer

    def read(self, source: str, *, images: bool) -> ReadStub:
        with self.local_copy(source) as path:
            return self.read_file(path, images=images)

    @contextmanager
    def local_copy(self, source: str) -> Iterator[Path]:
        """A local path to the stub; an S3 file is downloaded and deleted afterwards."""
        if source.startswith(_S3):
            bucket, key = _s3_location(source)
            if self._downloader is None:
                raise ReadingError("reading from S3 needs an S3 downloader")
            with TemporaryDirectory() as folder:
                path = Path(folder) / _local_name(key)
                try:
                    self._downloader.download(bucket, key, path)
                except IdpError as exc:
                    raise ReadingError("could not download the paystub") from exc
                yield path
            return
        path = Path(source)
        if not path.is_file():
            raise ReadingError("paystub file not found")
        yield path

    def read_file(self, path: Path, *, images: bool) -> ReadStub:
        try:
            outcome = read_document(
                path, auto=False, readers=self._readers, features=_FEATURES
            )
        except IdpError as exc:
            raise ReadingError("the OCR library could not read the paystub") from exc
        if outcome.status != "accepted" or outcome.accepted is None:
            raise ReadingError(
                f"no reader produced usable text ({outcome.error_code})",
                code=outcome.error_code,
            )
        document = outcome.accepted.result.document
        pages = tuple(page.page_number for page in document.pages)
        return ReadStub(
            text=document_text(document),
            reader=outcome.accepted.reader,
            pages=pages,
            images=self.render(path, pages) if images else (),
        )

    def render(self, path: Path, pages: Sequence[int]) -> tuple[PageImage, ...]:
        """Page images of the given pages, at most `max_images` of them."""
        try:
            rendered = self._renderer(
                path,
                list(pages)[: self._config.max_images],
                dpi=self._config.image_dpi,
                max_side=self._config.image_max_side,
                grayscale=self._config.grayscale,
            )
        except IdpError as exc:
            raise ReadingError("could not render page images") from exc
        return tuple(
            PageImage(page_number=i.page_number, media_type=i.media_type, data=i.data)
            for i in rendered
        )

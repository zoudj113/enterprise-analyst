"""
PDF text extraction engine with dual-backend support.

Uses pdfplumber as default (better for Chinese text) with
PyPDF2 as fallback. Handles Windows encoding issues and
memory-efficient chunked extraction for large files.
"""

import io
import sys
from pathlib import Path
from typing import Iterator

from .models import ExtractionBackend, PageInfo


class ChinesePDFExtractor:
    """Extracts text from Chinese financial PDFs with proper encoding."""

    def __init__(
        self,
        pdf_path: str | Path,
        backend: ExtractionBackend = ExtractionBackend.PDFPLUMBER,
    ):
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {self.pdf_path}")
        self.backend = backend
        self._page_count: int | None = None

    def _ensure_encoding(self):
        """Fix stdout encoding for Chinese text on Windows consoles."""
        if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
            try:
                sys.stdout = io.TextIOWrapper(
                    sys.stdout.buffer, encoding='utf-8', errors='replace'
                )
            except (AttributeError, ValueError):
                pass  # already wrapped or not a tty

    # ── Public API ─────────────────────────────────────────────────────

    def get_page_count(self) -> int:
        """Return total number of pages in the PDF."""
        if self._page_count is not None:
            return self._page_count
        total = _get_page_count(self.pdf_path, self.backend)
        self._page_count = total
        return total

    def extract_pages(self, page_numbers: list[int]) -> list[PageInfo]:
        """Extract text from specific pages (1-based). Returns list of PageInfo."""
        return _extract_pages(self.pdf_path, page_numbers, self.backend)

    def extract_range(self, start: int, end: int) -> list[PageInfo]:
        """Extract a contiguous page range (1-based, inclusive)."""
        return self.extract_pages(list(range(start, end + 1)))

    def extract_all(self) -> list[PageInfo]:
        """Extract all pages from the PDF."""
        total = self.get_page_count()
        return self.extract_pages(list(range(1, total + 1)))

    def extract_chunked(
        self,
        chunk_size: int = 50,
        start: int = 1,
        end: int | None = None,
    ) -> Iterator[list[PageInfo]]:
        """
        Memory-efficient chunked extraction for large PDFs.

        Yields lists of PageInfo in chunks of chunk_size pages.
        Re-opens the PDF for each chunk to avoid memory bloat.
        """
        total = self.get_page_count()
        end = end or total
        end = min(end, total)

        for chunk_start in range(start, end + 1, chunk_size):
            chunk_end = min(chunk_start + chunk_size - 1, end)
            yield self.extract_pages(list(range(chunk_start, chunk_end + 1)))

    # ── Static helpers ──────────────────────────────────────────────────

    @staticmethod
    def count_digits(text: str) -> int:
        """Count digit characters in text (heuristic for financial data pages)."""
        return sum(c.isdigit() for c in text)

    @staticmethod
    def count_numbers(text: str) -> int:
        """Count number-like tokens in text."""
        from .keywords import NUMBER_PATTERN
        return len(NUMBER_PATTERN.findall(text))


# ── Backend-specific implementation ────────────────────────────────────


def _get_page_count(pdf_path: Path, backend: ExtractionBackend) -> int:
    if backend == ExtractionBackend.PDFPLUMBER:
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            return len(pdf.pages)
    else:
        import PyPDF2
        reader = PyPDF2.PdfReader(str(pdf_path))
        return len(reader.pages)


def _extract_pages(
    pdf_path: Path,
    page_numbers: list[int],
    backend: ExtractionBackend,
) -> list[PageInfo]:
    """Core extraction logic dispatched by backend."""
    if backend == ExtractionBackend.PDFPLUMBER:
        return _extract_with_pdfplumber(pdf_path, page_numbers)
    else:
        return _extract_with_pypdf2(pdf_path, page_numbers)


def _extract_with_pdfplumber(pdf_path: Path, page_numbers: list[int]) -> list[PageInfo]:
    import pdfplumber

    results: list[PageInfo] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for pn in page_numbers:
            if pn < 1 or pn > len(pdf.pages):
                continue
            text = pdf.pages[pn - 1].extract_text() or ""
            results.append(PageInfo(
                page_number=pn,
                text=text,
                char_count=len(text),
                digit_count=sum(c.isdigit() for c in text),
            ))
    return results


def _extract_with_pypdf2(pdf_path: Path, page_numbers: list[int]) -> list[PageInfo]:
    import PyPDF2

    reader = PyPDF2.PdfReader(str(pdf_path))
    results: list[PageInfo] = []
    for pn in page_numbers:
        if pn < 1 or pn > len(reader.pages):
            continue
        text = reader.pages[pn - 1].extract_text() or ""
        results.append(PageInfo(
            page_number=pn,
            text=text,
            char_count=len(text),
            digit_count=sum(c.isdigit() for c in text),
        ))
    return results

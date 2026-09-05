"""Render one page of a PDF original to a PNG file.

pypdfium2 draws the page (imported lazily, like in ``extract``); the PNG is
encoded here with ``zlib`` and ``struct`` so no imaging library is needed.
"""

import struct
import zlib
from pathlib import Path

from bmc_toolkit.spec.extract import _require_pypdfium2
from bmc_toolkit.spec.library import atomic_write_bytes

DEFAULT_SCALE = 2.0  # times 72 dpi


def write_png(path: Path, width: int, height: int, rows: list[bytes]) -> None:
    """Write 8-bit RGB rows (``width * 3`` bytes each) as a PNG."""
    if len(rows) != height or any(len(r) != width * 3 for r in rows):
        raise ValueError("rows do not match width and height")

    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(kind + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    raw = b"".join(b"\x00" + r for r in rows)  # filter type 0 per scanline
    png = b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
            chunk(b"IDAT", zlib.compress(raw, 6)),
            chunk(b"IEND", b""),
        ]
    )
    atomic_write_bytes(path, png)  # two Sessions rendering one page cannot collide


def _rgb_rows(bitmap) -> list[bytes]:
    """RGB rows from a pypdfium2 bitmap rendered with ``rev_byteorder``."""
    channels = bitmap.n_channels
    if channels not in (3, 4):
        raise ValueError(f"unexpected bitmap format {bitmap.mode!r}")
    data = bytes(bitmap.buffer)
    width, height, stride = bitmap.width, bitmap.height, bitmap.stride
    rows = []
    for y in range(height):
        row = data[y * stride : y * stride + width * channels]
        if channels == 4:
            rgb = bytearray(width * 3)
            rgb[0::3] = row[0::4]
            rgb[1::3] = row[1::4]
            rgb[2::3] = row[2::4]
            row = bytes(rgb)
        rows.append(row)
    return rows


def render_page(
    pdf_path: Path, page: int, out: Path, scale: float = DEFAULT_SCALE
) -> Path:
    """Render physical page ``page`` (1-based) of ``pdf_path`` into ``out``."""
    pdfium = _require_pypdfium2()
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        if not 1 <= page <= len(pdf):
            raise ValueError(f"page {page} is outside 1-{len(pdf)}")
        bitmap = pdf[page - 1].render(scale=scale, rev_byteorder=True)
    finally:
        pdf.close()  # or Windows keeps the original locked
    out.parent.mkdir(parents=True, exist_ok=True)
    write_png(out, bitmap.width, bitmap.height, _rgb_rows(bitmap))
    return out

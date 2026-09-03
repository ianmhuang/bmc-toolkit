"""Write small PDFs for tests with the standard library only.

Each page is a list of items in PDF points, origin bottom-left:

    (x, y, text) or (x, y, text, size)    text in Helvetica (base-14, so no
                                          embedding)
    ("line", x0, y0, x1, y1)              a stroked line
    ("rect", x, y, w, h)                  a stroked rectangle
    ("fill", x, y, w, h[, gray])          a filled rectangle (black, or the
                                          grey level 0..1): a thin one is a
                                          table rule the way Word draws it, a
                                          large light one a shaded cell
    ("curve", x0, y0, x1, y1, x2, y2, x3, y3)   a stroked Bezier curve
    ("image", x, y, w, h)                 a 2x2 grey raster image scaled to w x h
    ("form", x, y, w, h)                  a form XObject (a diagonal line across a
                                          100 x 100 box) scaled to w x h

Optional bookmarks become a PDF outline. Enough for the extractor's geometry
rules and figure detection; not a general PDF writer.
"""

from pathlib import Path

PAGE_W = 612
PAGE_H = 792
DEFAULT_SIZE = 10


def _escape(text: str) -> bytes:
    raw = text.encode("latin-1", "replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _content(items) -> bytes:
    draw = []
    text_ops = [b"BT"]
    for item in items:
        if isinstance(item[0], str):
            kind = item[0]
            if kind == "line":
                draw.append(b"%.2f %.2f m %.2f %.2f l S" % tuple(item[1:5]))
            elif kind == "rect":
                draw.append(b"%.2f %.2f %.2f %.2f re S" % tuple(item[1:5]))
            elif kind == "fill":
                gray = item[5] if len(item) > 5 else 0.0
                draw.append(b"q %.3f g %.2f %.2f %.2f %.2f re f Q" % (gray, *item[1:5]))
            elif kind == "curve":
                draw.append(
                    b"%.2f %.2f m %.2f %.2f %.2f %.2f %.2f %.2f c S" % tuple(item[1:9])
                )
            elif kind == "image":
                x, y, w, h = item[1:5]
                draw.append(b"q %.2f 0 0 %.2f %.2f %.2f cm /Im1 Do Q" % (w, h, x, y))
            elif kind == "form":
                x, y, w, h = item[1:5]
                draw.append(
                    b"q %.4f 0 0 %.4f %.2f %.2f cm /Fm1 Do Q" % (w / 100, h / 100, x, y)
                )
            else:
                raise ValueError(f"unknown item kind {kind!r}")
            continue
        x, y, text = item[:3]
        size = item[3] if len(item) > 3 else DEFAULT_SIZE
        text_ops.append(
            b"/F1 %d Tf 1 0 0 1 %.2f %.2f Tm (%s) Tj" % (size, x, y, _escape(text))
        )
    text_ops.append(b"ET")
    return b"\n".join(draw + text_ops)


def write_pdf(path: Path, pages, bookmarks=None) -> Path:
    """Write ``pages`` (list of item lists) to ``path``.

    ``bookmarks`` is a list of ``(level, title, page_index)`` in document
    order; levels nest by being greater than the previous entry's level.
    """
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)  # 1-based object number

    catalog_no = add(b"")  # placeholder, filled at the end
    pages_no = add(b"")
    font_no = add(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        b"/Encoding /WinAnsiEncoding >>"
    )
    image_no = add(
        b"<< /Type /XObject /Subtype /Image /Width 2 /Height 2 "
        b"/ColorSpace /DeviceGray /BitsPerComponent 8 /Length 4 >>\nstream\n"
        b"\x40\x80\x80\x40\nendstream"
    )
    form_stream = b"0 0 m 100 100 l S"
    form_no = add(
        b"<< /Type /XObject /Subtype /Form /BBox [0 0 100 100] /Length %d >>\n"
        b"stream\n" % len(form_stream) + form_stream + b"\nendstream"
    )
    page_nos = []
    for items in pages:
        stream = _content(items)
        content_no = add(
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
        )
        page_no = add(
            b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] "
            b"/Resources << /Font << /F1 %d 0 R >> "
            b"/XObject << /Im1 %d 0 R /Fm1 %d 0 R >> >> /Contents %d 0 R >>"
            % (pages_no, PAGE_W, PAGE_H, font_no, image_no, form_no, content_no)
        )
        page_nos.append(page_no)
    kids = b" ".join(b"%d 0 R" % n for n in page_nos)
    objects[pages_no - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        kids,
        len(page_nos),
    )

    outlines_ref = b""
    if bookmarks:
        outlines_no = add(b"")
        item_nos = [add(b"") for _ in bookmarks]
        # Build the tree: parent = nearest previous entry with a smaller level.
        parents = []
        for i, (level, _, _) in enumerate(bookmarks):  # noqa: B007
            parent = outlines_no
            for j in range(i - 1, -1, -1):
                if bookmarks[j][0] < level:
                    parent = item_nos[j]
                    break
            parents.append(parent)
        children: dict[int, list[int]] = {}
        for i, parent in enumerate(parents):
            children.setdefault(parent, []).append(i)
        for i, (_level, title, page_index) in enumerate(bookmarks):
            sibs = children[parents[i]]
            pos = sibs.index(i)
            parts = [
                b"<< /Title (%s) /Parent %d 0 R /Dest [%d 0 R /XYZ 0 %d 0]"
                % (_escape(title), parents[i], page_nos[page_index], PAGE_H)
            ]
            if pos > 0:
                parts.append(b"/Prev %d 0 R" % item_nos[sibs[pos - 1]])
            if pos < len(sibs) - 1:
                parts.append(b"/Next %d 0 R" % item_nos[sibs[pos + 1]])
            kids_i = children.get(item_nos[i], [])
            if kids_i:
                parts.append(
                    b"/First %d 0 R /Last %d 0 R /Count %d"
                    % (item_nos[kids_i[0]], item_nos[kids_i[-1]], len(kids_i))
                )
            parts.append(b">>")
            objects[item_nos[i] - 1] = b" ".join(parts)
        top = children[outlines_no]
        objects[outlines_no - 1] = (
            b"<< /Type /Outlines /First %d 0 R /Last %d 0 R /Count %d >>"
            % (item_nos[top[0]], item_nos[top[-1]], len(bookmarks))
        )
        outlines_ref = b" /Outlines %d 0 R /PageMode /UseOutlines" % outlines_no

    objects[catalog_no - 1] = b"<< /Type /Catalog /Pages %d 0 R%s >>" % (
        pages_no,
        outlines_ref,
    )

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        catalog_no,
        xref,
    )
    Path(path).write_bytes(bytes(out))
    return Path(path)


def numbered_page(first: int, lines, x_number=37.0, x_text=72.0, top=720.0, step=14.0):
    """A DMTF-style page: a margin number before each text line."""
    items = []
    y = top
    n = first
    for text in lines:
        items.append((x_number, y, str(n)))
        if text:
            items.append((x_text, y, text))
        y -= step
        n += 1
    return items


def plain_page(lines, x_text=72.0, top=720.0, step=14.0):
    return [(x_text, top - i * step, text) for i, text in enumerate(lines)]

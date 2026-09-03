"""Turn a PDF original into an Extract, an Outline and a Line Map.

Text comes from pypdfium2 character boxes (imported lazily). Characters are
grouped into lines by baseline, lines are laid out on a character grid whose
unit is the page's median glyph width, so table columns keep their positions
across rows. Printed line numbers (DMTF documents) are recognised purely by
geometry and moved from the text into the Line Map. The Outline comes from
PDF bookmarks, or from the contents pages when a document has none.

Files written next to the original::

    extract.txt    "=== page N ===" then the page's lines, for every page
    outline.json   [{"level": int, "title": str, "page": int}, ...]; an entry
                   carries "approximate": true when it came from a contents
                   page whose printed-to-physical page offset could not be
                   confirmed (extract.json then has page_offset null)
    linemap.json   {"pages": {"N": {"first": a, "last": b, "lines": {"i": n}}}}
                   where N is the physical page and i is the 0-based index of
                   the line within that page's block of the Extract, counting
                   from the first line after the "=== page N ===" marker
    extract.json   run metadata, see ExtractResult.to_meta()

Requires pypdfium2 5.x (its bookmark API: ``get_toc`` items with
``get_dest()``/``get_title()``); 4.x is refused with a clear ImportError.
"""

import json
import re
import statistics
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

EXTRACTOR_VERSION = 2  # 2: space markers and line joining by overlap
PAGE_MARKER = "=== page {n} ==="
EXTRACT_NAME = "extract.txt"
OUTLINE_NAME = "outline.json"
LINEMAP_NAME = "linemap.json"
META_NAME = "extract.json"

# Geometry thresholds, in multiples of the page's unit (median glyph width).
SEGMENT_GAP = 1.0  # a wider gap starts a new segment (table cell, column)
WORD_GAP = 0.22  # a wider gap inside a segment is a word space
STREAM_NEIGHBOUR = 0.6  # of glyph height: how close a stream predecessor must be
BASELINE_TOL = 0.45  # of the glyph height: stream neighbours share a baseline
LINE_OVERLAP = 0.5  # of the smaller glyph height: vertical overlap that joins a line
NUMBER_BAND_PT = 3.0  # line numbers share an edge within this many points
MIN_NUMBERED_LINES = 5
NUMBER_MARGIN = 0.15  # the number column lies within this fraction of the width

_CONTENTS_LINE = re.compile(
    r"^\s*(?P<num>\d+(?:\.\d+)*)\.?\s+(?P<title>\S.*?)\s*"
    r"(?:(?:\.\s*){2,}|\s{3,})\s*(?P<page>\d{1,4})\s*$"
)
_INT = re.compile(r"(?<![\w.])(\d{1,4})(?![\w.])")


@dataclass
class Segment:
    x0: float
    x1: float
    text: str


@dataclass
class Line:
    y0: float
    x0: float
    segments: list[Segment]
    number: int | None = None  # printed line number, once detected


@dataclass
class PageText:
    index: int  # 0-based physical page
    lines: list[Line]
    unit: float
    left: float
    width: float = 612.0
    numbered: bool = False


@dataclass
class ExtractResult:
    pages: int
    seconds: float
    outline: list[dict]
    outline_source: str  # bookmarks | contents | none
    linemap: dict
    numbered_pages: int
    page_offset: int | None = None
    text: str = field(default="", repr=False)

    def to_meta(self) -> dict:
        return {
            "extractor_version": EXTRACTOR_VERSION,
            "pages": self.pages,
            "seconds": round(self.seconds, 2),
            "line_numbers": self.numbered_pages > 0,
            "line_numbered_pages": self.numbered_pages,
            "outline_source": self.outline_source,
            "outline_entries": len(self.outline),
            "page_offset": self.page_offset,
        }


# --------------------------------------------------------------- page text


def _page_chars(textpage) -> list[tuple[float, float, float, float, str]]:
    """(x0, y0, x1, y1, char) for every printable character on the page.

    A space that pdfium reports between two glyphs is kept as a marker
    (``" "``) attached to the following glyph: some fonts' advance boxes
    overlap the space (an ``f`` after ``s``), so the geometric gap alone
    would glue the words. pdfium also invents a space wherever the content
    stream jumps (to draw a margin line number between the two halves of
    "I2C"), so the marker is kept only when the glyph before the space in
    stream order is also the glyph's left neighbour on the page.
    """
    text = textpage.get_text_range()
    count = textpage.count_chars()
    if len(text) != count:
        # Surrogate pairs or an odd encoding broke index alignment; keep the
        # page readable without layout rather than misplacing every glyph.
        return []
    out = []
    pending_space = False
    prev = None  # box of the previous printable glyph in stream order
    for i, ch in enumerate(text):
        if ch in "\r\n":
            pending_space = False
            continue
        if ch.isspace():
            pending_space = True
            continue
        # loose = the glyph's advance box, not its ink: consistent baselines
        # for descenders and no fake gaps after narrow letters.
        x0, y0, x1, y1 = textpage.get_charbox(i, loose=True)
        if x1 <= x0 or y1 <= y0:
            continue
        marked = (
            pending_space
            and prev is not None
            and _stream_neighbours(prev, (x0, y0, x1, y1))
        )
        out.append((x0, y0, x1, y1, (" " + ch) if marked else ch))
        pending_space = False
        prev = (x0, y0, x1, y1)
    return out


def _stream_neighbours(prev, box) -> bool:
    """True when ``box`` sits right after ``prev`` on the same baseline."""
    height = max(box[3] - box[1], prev[3] - prev[1], 1.0)
    same_line = abs(box[1] - prev[1]) < BASELINE_TOL * height
    return same_line and abs(box[0] - prev[2]) < STREAM_NEIGHBOUR * height


def _group_lines(chars, unit: float) -> list[Line]:
    if not chars:
        return []
    ordered = sorted(chars, key=lambda c: (-c[1], c[0]))
    groups: list[list] = []
    refs: list[tuple] = []  # the tallest box of each group: its line extent
    for c in ordered:
        if groups and _same_line(refs[-1], c):
            groups[-1].append(c)
            if c[3] - c[1] > refs[-1][3] - refs[-1][1]:
                refs[-1] = c
        else:
            groups.append([c])
            refs.append(c)
    lines = []
    for g in groups:
        g.sort(key=lambda c: c[0])
        segments: list[Segment] = []
        cur: list = []
        for c in g:
            if cur:
                gap = c[0] - cur[-1][2]
                if gap > SEGMENT_GAP * unit:
                    segments.append(_segment(cur, unit))
                    cur = []
            cur.append(c)
        if cur:
            segments.append(_segment(cur, unit))
        lines.append(Line(y0=g[0][1], x0=segments[0].x0, segments=segments))
    return lines


def _same_line(ref, c) -> bool:
    """Same line when the boxes overlap vertically by half the smaller height.

    Catches superscripts and subscripts (a small "2" riding high in "I2C")
    without merging adjacent lines of body text.
    """
    overlap = min(ref[3], c[3]) - max(ref[1], c[1])
    smaller = min(ref[3] - ref[1], c[3] - c[1])
    return overlap >= LINE_OVERLAP * smaller


def _segment(chars, unit: float) -> Segment:
    parts = [chars[0][4].lstrip(" ")]
    for prev, c in zip(chars, chars[1:], strict=False):
        if c[4].startswith(" ") or c[0] - prev[2] > WORD_GAP * unit:
            parts.append(" ")
        parts.append(c[4].lstrip(" "))
    return Segment(chars[0][0], chars[-1][2], "".join(parts))


def page_text(textpage, index: int, width: float = 612.0) -> PageText:
    chars = _page_chars(textpage)
    if not chars:
        # Fallback: pdfium's own line breaks, no layout.
        raw = textpage.get_text_range().replace("\r\n", "\n")
        lines = [
            Line(0.0, 0.0, [Segment(0.0, 0.0, ln.strip())])
            for ln in raw.split("\n")
            if ln.strip()
        ]
        return PageText(index, lines, 1.0, 0.0, width)
    unit = statistics.median(c[2] - c[0] for c in chars) or 1.0
    lines = _group_lines(chars, unit)
    left = min(ln.x0 for ln in lines) if lines else 0.0
    return PageText(index, lines, unit, left, width)


# ------------------------------------------------------------ line numbers


def detect_line_numbers(page: PageText, previous_last: int | None) -> bool:
    """Mark ``page`` as line-numbered when its left margin carries a number column.

    DMTF documents number every line (older releases) or every paragraph
    (newer ones), always in the margin left of the body text. The rules are
    geometric only: at least MIN_NUMBERED_LINES integers sharing a left or a
    right edge, strictly increasing down the page, inside the left
    NUMBER_MARGIN of the page, left of where the other lines start, and
    continuing the previous numbered page's count. Sets ``Line.number`` on the
    numbered lines and returns True; leaves the page untouched otherwise.
    """
    text_lines = [ln for ln in page.lines if ln.segments]
    cands = []
    for ln in text_lines:
        first = ln.segments[0]
        if first.text.isdigit():
            cands.append((ln, int(first.text), first.x0, first.x1))
    if not cands:
        return False
    best: list = []
    for edge in (2, 3):  # align on x0 or on x1 (right-aligned numbers)
        anchor = Counter(round(c[edge]) for c in cands).most_common(1)[0][0]
        members = [c for c in cands if abs(c[edge] - anchor) <= NUMBER_BAND_PT]
        if len(members) > len(best):
            best = members
    numbers = [n for _, n, _, _ in best]
    # A short run is accepted only when it continues the previous page
    # exactly (figure pages carry one or two numbered lines).
    continues = previous_last is not None and numbers[0] == previous_last + 1
    if len(best) < MIN_NUMBERED_LINES and not continues:
        return False
    if any(b != a + 1 for a, b in zip(numbers, numbers[1:], strict=False)):
        return False  # DMTF numbering never skips; tables and lists do
    band_right = max(x1 for _, _, _, x1 in best)
    if band_right > NUMBER_MARGIN * page.width:
        return False
    chosen = {id(ln) for ln, _, _, _ in best}
    others = [ln.x0 for ln in text_lines if id(ln) not in chosen]
    if others and min(others) <= band_right + NUMBER_BAND_PT:
        return False  # something else starts as far left: not a margin column
    body = [ln.segments[1].x0 for ln, _, _, _ in best if len(ln.segments) > 1]
    if body and min(body) <= band_right + NUMBER_BAND_PT:
        return False
    if previous_last is not None and numbers[0] <= previous_last:
        return False
    for ln, n, _, _ in best:
        ln.number = n
        ln.segments = ln.segments[1:]
    page.numbered = True
    page.left = min((s.x0 for ln in page.lines for s in ln.segments), default=page.left)
    return True


# ------------------------------------------------------------------ layout


def render_page(page: PageText) -> list[str]:
    """Lay the page's lines out on a character grid."""
    out = []
    for ln in page.lines:
        buf: list[str] = []
        for seg in ln.segments:
            col = round((seg.x0 - page.left) / page.unit)
            if buf:
                col = max(col, len(buf) + 1)
            buf.extend(" " * (col - len(buf)))
            buf.extend(seg.text)
        out.append("".join(buf).rstrip())
    return out


# ----------------------------------------------------------------- outline


def outline_from_bookmarks(pdf) -> list[dict]:
    entries = []
    for bm in pdf.get_toc():
        dest = bm.get_dest()
        if dest is None:
            continue
        try:
            index = dest.get_index()
        except Exception:  # noqa: BLE001 - pdfium raises on broken dests
            continue
        if index is None:
            continue
        title = re.sub(r"\s+", " ", bm.get_title()).strip()
        entries.append({"level": bm.level, "title": title, "page": index + 1})
    return entries


def parse_contents(pages_text: list[list[str]]) -> list[dict]:
    """Contents-page entries as {level, title, printed} from page texts."""
    entries = []
    limit = max(5, min(60, len(pages_text) // 4 + 5))
    for lines in pages_text[:limit]:
        found = []
        for ln in lines:
            m = _CONTENTS_LINE.match(ln)
            if not m:
                continue
            title = re.sub(r"\s+", " ", m.group("title")).rstrip(" .")
            if not re.search(r"[A-Za-z]", title):
                continue
            if re.match(r"^\d+(\.\d+)*\.?\s", title):
                continue  # "35 1.2. Title": a stray number swallowed the section
            num = m.group("num")
            found.append(
                {
                    "level": num.count("."),
                    "title": f"{num} {title}",
                    "printed": int(m.group("page")),
                }
            )
        if len(found) >= 8:
            entries.extend(found)
    return entries


def find_page_offset(pages_text: list[list[str]]) -> int | None:
    """physical - printed, from page numbers in headers and footers."""
    n = len(pages_text)
    votes: Counter = Counter()
    for i in range(n // 4, n):
        edge = pages_text[i][:2] + pages_text[i][-3:]
        seen = set()
        for ln in edge:
            for m in _INT.finditer(ln):
                v = int(m.group(1))
                if 1 <= v <= n + 50:
                    seen.add(v)
        for v in seen:
            votes[(i + 1) - v] += 1
    if not votes:
        return None
    offset, count = votes.most_common(1)[0]
    if count < 3:
        return None
    return offset


# ------------------------------------------------------------------- driver


def _require_pypdfium2():
    import pypdfium2 as pdfium  # lazy: optional at runtime

    version = getattr(pdfium, "PYPDFIUM_INFO", None)
    major = getattr(version, "major", None)
    if major is None:
        raw = getattr(pdfium, "V_PYPDFIUM2", None) or getattr(pdfium, "__version__", "")
        try:
            major = int(str(raw).split(".")[0])
        except ValueError:
            major = None
    if major is not None and major < 5:
        raise ImportError(
            f"pypdfium2 {major}.x found; version 5 or newer is required "
            "(pip install --upgrade pypdfium2)"
        )
    return pdfium


def extract_pdf(path: Path) -> ExtractResult:
    pdfium = _require_pypdfium2()

    started = time.perf_counter()
    pdf = pdfium.PdfDocument(str(path))
    count = len(pdf)
    chunks: list[str] = []
    pages_lines: list[list[str]] = []
    linemap: dict = {}
    numbered = 0
    previous_last: int | None = None
    for i in range(count):
        pdf_page = pdf[i]
        page = page_text(pdf_page.get_textpage(), i, pdf_page.get_size()[0])
        if detect_line_numbers(page, previous_last):
            numbered += 1
            nums = {}
            for li, ln in enumerate(page.lines):
                if ln.number is not None:
                    nums[str(li)] = ln.number
            values = list(nums.values())
            linemap[str(i + 1)] = {
                "first": values[0],
                "last": values[-1],
                "lines": nums,
            }
            previous_last = values[-1]
        lines = render_page(page)
        pages_lines.append(lines)
        chunks.append(PAGE_MARKER.format(n=i + 1))
        chunks.extend(lines)
    outline = outline_from_bookmarks(pdf)
    source = "bookmarks" if outline else "none"
    offset = None
    if not outline:
        parsed = parse_contents(pages_lines)
        if parsed:
            offset = find_page_offset(pages_lines)
            shift = offset or 0
            for e in parsed:
                page_no = e["printed"] + shift
                if 1 <= page_no <= count:
                    entry = {"level": e["level"], "title": e["title"], "page": page_no}
                    if offset is None:
                        entry["approximate"] = True  # printed page taken as physical
                    outline.append(entry)
            source = "contents" if outline else "none"
    text = "\n".join(chunks) + "\n"
    return ExtractResult(
        pages=count,
        seconds=time.perf_counter() - started,
        outline=outline,
        outline_source=source,
        linemap={"pages": linemap},
        numbered_pages=numbered,
        page_offset=offset,
        text=text,
    )


def write_result(vdir: Path, result: ExtractResult) -> None:
    def dump(name: str, data) -> None:
        with open(vdir / name, "w", encoding="utf-8", newline="") as fh:
            json.dump(data, fh, indent=1, ensure_ascii=False)
            fh.write("\n")

    # The meta file is what marks an extraction as current, so it goes away
    # first and comes back last: a failure in between leaves nothing that
    # is_current() would believe.
    meta_path = vdir / META_NAME
    if meta_path.exists():
        meta_path.unlink()
    with open(vdir / EXTRACT_NAME, "w", encoding="utf-8", newline="") as fh:
        fh.write(result.text)
    dump(OUTLINE_NAME, result.outline)
    linemap_path = vdir / LINEMAP_NAME
    if result.numbered_pages:
        dump(LINEMAP_NAME, result.linemap)
    elif linemap_path.exists():
        linemap_path.unlink()
    dump(META_NAME, result.to_meta())


def read_meta(vdir: Path) -> dict | None:
    path = vdir / META_NAME
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def is_current(vdir: Path) -> bool:
    meta = read_meta(vdir)
    return (
        bool(meta)
        and meta.get("extractor_version") == EXTRACTOR_VERSION
        and (vdir / EXTRACT_NAME).is_file()
    )


def remove_derived(vdir: Path) -> None:
    for name in (EXTRACT_NAME, OUTLINE_NAME, LINEMAP_NAME, META_NAME):
        p = vdir / name
        if p.exists():
            p.unlink()

"""Turn a PDF original into an Extract, an Outline and a Line Map.

Text comes from pypdfium2 character boxes (imported lazily). Characters are
grouped into lines by baseline, lines are laid out on a character grid whose
unit is the page's median glyph width, so table columns keep their positions
across rows. Printed line numbers (DMTF documents) are recognised purely by
geometry and moved from the text into the Line Map. The Outline comes from
PDF bookmarks, or from the contents pages when a document has none, or when
its bookmarks are only Word anchors (``Ref_DSP0236``, ``OLE_LINK1``) or two
or more of them all point at one page of a longer document.

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
    figures.json   {"pages": {"N": {"regions": [[x0, y0, x1, y1], ...],
                   "lines": [i, ...]}}} for every page that holds a figure:
                   raster images and vector drawings (paths with a diagonal
                   or curved segment) clustered with the paths that overlap
                   them, in PDF points with the origin bottom-left, plus the
                   indices (as in linemap.json) of the Extract lines lying
                   inside a region. Box-only diagrams (axis-aligned rules and
                   rectangles, like a table) are not figures here.
    extract.json   run metadata, see ExtractResult.to_meta()

Requires pypdfium2 5.x (its bookmark API: ``get_toc`` items with
``get_dest()``/``get_title()``); 4.x is refused with a clear ImportError.
"""

import bisect
import json
import re
import shutil
import statistics
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from bmc_toolkit.spec.library import (
    SCHEMAS_DIRNAME,
    atomic_write_json,
    atomic_write_text,
)
from bmc_toolkit.spec.tables import remove_store

EXTRACTOR_VERSION = 4  # 4: stacked same-size glyphs are two lines; anchor bookmarks
PAGE_MARKER = "=== page {n} ==="
EXTRACT_NAME = "extract.txt"
OUTLINE_NAME = "outline.json"
LINEMAP_NAME = "linemap.json"
FIGURES_NAME = "figures.json"
META_NAME = "extract.json"
RENDERS_DIRNAME = "renders"

# Figure detection, in PDF points.
DIAGONAL_PT = 2.0  # a segment moving more than this in both x and y is diagonal
CORNER_PT = 8.0  # a curve spanning no more than this is a rounded corner, not a shape
FIGURE_GAP_PT = 12.0  # drawings closer than this belong to one figure
MIN_FIGURE_PT = 36.0  # a figure is at least this long ...
MIN_FIGURE_SIDE_PT = 18.0  # ... and this wide: bullets, braces and arrows are not
MIN_IMAGE_PT = 36.0  # a raster image smaller than this either way is a logo or icon
MAX_RULE_FRACTION = 0.5  # an axis-aligned path covering more of the page is a backdrop

# Geometry thresholds, in multiples of the page's unit (median glyph width).
SEGMENT_GAP = 1.0  # a wider gap starts a new segment (table cell, column)
WORD_GAP = 0.22  # a wider gap inside a segment is a word space
STREAM_NEIGHBOUR = 0.6  # of glyph height: how close a stream predecessor must be
BASELINE_TOL = 0.45  # of the glyph height: stream neighbours share a baseline
LINE_OVERLAP = 0.5  # of the smaller glyph height: vertical overlap that joins a line
STACKED = 0.2  # of the narrower glyph width: horizontal overlap that stacks two glyphs
SIZE_TOL = 0.02  # of the glyph height: boxes this close in height are one size
NUMBER_BAND_PT = 3.0  # line numbers share an edge within this many points
MIN_NUMBERED_LINES = 5
NUMBER_MARGIN = 0.15  # the number column lies within this fraction of the width

_CONTENTS_LINE = re.compile(
    r"^\s*(?P<num>\d+(?:\.\d+)*)\.?\s+(?P<title>\S.*?)\s*"
    r"(?:(?:\.\s*){2,}|\s{3,})\s*(?P<page>\d{1,4})\s*$"
)
_INT = re.compile(r"(?<![\w.])(\d{1,4})(?![\w.])")
_ANCHOR = re.compile(r"^\S*_\S*$")  # a Word anchor name: one token, an underscore


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
    figures: dict = field(default_factory=lambda: {"pages": {}})
    figure_errors: int = 0  # pages whose figure pass failed
    text: str = field(default="", repr=False)

    @property
    def figure_pages(self) -> int:
        return len(self.figures.get("pages", {}))

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
            "figure_pages": self.figure_pages,
            "figure_errors": self.figure_errors,
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
    groups: list[_LineGroup] = []
    for run in _baseline_runs(ordered):
        # A baseline run joins whole or not at all: the leading glyphs of a
        # lower line that starts further left than the upper one have
        # nothing over them, but the glyphs after them do.
        if groups and all(groups[-1].accepts(c) for c in run):
            for c in run:
                groups[-1].add(c)
        else:
            groups.append(_LineGroup(run[0]))
            for c in run[1:]:
                groups[-1].add(c)
    lines = []
    for group in groups:
        g = group.chars
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


def _baseline_runs(ordered) -> list[list]:
    """Consecutive boxes of one baseline and one glyph height, in x order:
    the glyphs of one line set in one size, as they come out of the sort."""
    runs: list[list] = []
    for c in ordered:
        if runs:
            prev = runs[-1][-1]
            height = c[3] - c[1]
            same_baseline = abs(c[1] - prev[1]) < 0.05
            same_height = abs(height - (prev[3] - prev[1])) <= SIZE_TOL * height
            if same_baseline and same_height:
                runs[-1].append(c)
                continue
        runs.append([c])
    return runs


def _same_line(ref, c) -> bool:
    """Same line when the boxes overlap vertically by half the smaller height.

    Catches superscripts and subscripts (a small "2" riding high in "I2C")
    without merging adjacent lines of body text.
    """
    overlap = min(ref[3], c[3]) - max(ref[1], c[1])
    smaller = min(ref[3] - ref[1], c[3] - c[1])
    return overlap >= LINE_OVERLAP * smaller


class _SizeRun:
    """The boxes of one glyph height in a line group, searchable by x."""

    def __init__(self, first) -> None:
        self.height = first[3] - first[1]
        self._x0s: list[float] = []
        self._boxes: list[tuple] = []
        self._widest = 0.0
        self.add(first)

    def add(self, c) -> None:
        i = bisect.bisect_right(self._x0s, c[0])
        self._x0s.insert(i, c[0])
        self._boxes.insert(i, c)
        self._widest = max(self._widest, c[2] - c[0])

    def stacked_on(self, c):
        """The box already in the group that the incoming ``c`` is stacked
        on, or None. Boxes come top-down, so a box found here lies above
        ``c``, over it horizontally by more than STACKED of the narrower
        width. Touching or kerned neighbours ("I" before a raised "2", "V"
        before a lowered "DD") do not count."""
        width = c[2] - c[0]
        i = bisect.bisect_left(self._x0s, c[2])
        while i > 0 and self._x0s[i - 1] > c[0] - self._widest:
            i -= 1
            b = self._boxes[i]
            overlap = min(b[2], c[2]) - max(b[0], c[0])
            if overlap > STACKED * min(width, b[2] - b[0]):
                return b
        return None


class _LineGroup:
    """The boxes of one line while it is being built.

    A box joins when it overlaps the group's tallest box by half the
    smaller height (``_same_line``; the tallest box is a fixed anchor, so a
    staircase of slightly offset labels cannot pull the line down step by
    step) and when it is not stacked on a box of its own size: glyphs of
    one size on one line share a baseline, so a same-size box lying under
    another one without overlapping it by half is the next line. The second
    rule keeps two body lines apart when a large glyph in another column (a
    monospace value beside a two-line comment cell) overlaps both by more
    than half their height and becomes the anchor; ``_group_lines`` applies
    it to a whole baseline run at once. Super- and subscripts sit beside
    their neighbours, not over them, so they join whether or not they are
    smaller.
    """

    def __init__(self, first) -> None:
        self.chars = [first]
        self.ref = first  # the tallest box so far
        self._sizes: list[_SizeRun] = []  # one per glyph height
        self._index(first)

    def accepts(self, c) -> bool:
        if not _same_line(self.ref, c):
            return False
        run = self._run(c[3] - c[1])
        above = run.stacked_on(c) if run is not None else None
        return above is None or _same_line(above, c)

    def add(self, c) -> None:
        self.chars.append(c)
        if c[3] - c[1] > self.ref[3] - self.ref[1]:
            self.ref = c
        self._index(c)

    def _run(self, height: float):
        """The run of this glyph height, within SIZE_TOL: one font size
        gives one height, but rounding it would split a size at a boundary."""
        for run in self._sizes:
            if abs(run.height - height) <= SIZE_TOL * height:
                return run
        return None

    def _index(self, c) -> None:
        run = self._run(c[3] - c[1])
        if run is None:
            self._sizes.append(_SizeRun(c))
        else:
            run.add(c)


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
    """Bookmark entries, without the Word cross-reference anchors.

    Word exports every bookmark of the document, and a bookmark placed on a
    reference (``Ref_DSP0236``, ``OLE_LINK1``) is not a heading: a single
    token with an underscore is dropped. A heading keeps its spaces.
    """
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
        if _ANCHOR.match(title):
            continue
        entries.append({"level": bm.level, "title": title, "page": index + 1})
    return entries


def bookmarks_usable(entries: list[dict], page_count: int) -> bool:
    """False when the bookmarks are no Outline: none, or two or more that
    all land on one page of a longer document (leftover anchors without an
    underscore, "Mark2", "SMBus"). A single bookmark, or the bookmarks of
    a one-page document, cannot be judged and are kept."""
    if not entries:
        return False
    if len(entries) == 1 or page_count <= 1:
        return True
    return len({e["page"] for e in entries}) > 1


def is_contents_line(text: str) -> bool:
    """Whether a line reads as a contents entry: a section number, a title,
    dot leaders or a wide gap, then a page number. Such a line names a
    section without being its heading."""
    return _CONTENTS_LINE.match(text) is not None


def parse_contents(pages_text: list[list[str]]) -> list[dict]:
    """Contents-page entries as {level, title, printed} from page texts.

    An entry repeating an earlier one (same title, same printed page) is
    kept once: some documents carry their contents twice. Repeats still
    count towards recognising a page as a contents page.
    """
    entries = []
    seen: set[tuple[str, int]] = set()
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
            printed = int(m.group("page"))
            found.append(
                {"level": num.count("."), "title": f"{num} {title}", "printed": printed}
            )
        if len(found) >= 8:
            for e in found:
                key = (e["title"], e["printed"])
                if key not in seen:
                    seen.add(key)
                    entries.append(e)
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


# ----------------------------------------------------------------- figures

Box = tuple[float, float, float, float]  # x0, y0, x1, y1; origin bottom-left


def _apply(matrix, x: float, y: float) -> tuple[float, float]:
    return (
        matrix.a * x + matrix.c * y + matrix.e,
        matrix.b * x + matrix.d * y + matrix.f,
    )


def _containers(obj) -> list:
    """Form objects enclosing ``obj``, innermost first."""
    chain = []
    c = obj.container  # AttributeError on a pypdfium2 without it: counted
    while c is not None:  # as a figure error, never a silent wrong box
        chain.append(c)
        c = c.container
    return chain


def _to_page(points, containers) -> list[tuple[float, float]]:
    """Points in an object's space mapped through its enclosing forms."""
    for form in containers:
        m = form.get_matrix()
        points = [_apply(m, x, y) for x, y in points]
    return points


def _bounding(points) -> Box:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _object_box(obj, containers) -> Box:
    """The object's bounds in page coordinates.

    pdfium reports the bounds of an object nested in a form XObject in the
    form's own space, so the corners go through the form matrices.
    """
    x0, y0, x1, y1 = obj.get_bounds()
    if not containers:
        return (x0, y0, x1, y1)
    corners = [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
    return _bounding(_to_page(corners, containers))


def _path_is_drawing(obj, raw, containers) -> bool:
    """True when the path has a diagonal line or a curve larger than a corner.

    Segment points are in the path's own space; the object matrix and the
    enclosing form matrices are applied so a rotated rule stays a rule. A
    Bezier segment comes as three points; the curve counts by the distance
    from its start to its end, so the rounded corners of a code-span
    background or a table cell do not make a drawing, while arcs, circles
    and callouts do.
    """
    import ctypes  # local: only the figure pass needs it

    count = raw.FPDFPath_CountSegments(obj.raw)
    if count <= 0:
        return False
    matrix = obj.get_matrix()
    x = ctypes.c_float()
    y = ctypes.c_float()
    prev = None  # last point of the previous segment, page space
    bezier = 0  # control points seen in the current curve
    anchor = None  # where the current curve started
    for i in range(count):
        seg = raw.FPDFPath_GetPathSegment(obj.raw, i)
        kind = raw.FPDFPathSegment_GetType(seg)
        if not raw.FPDFPathSegment_GetPoint(seg, ctypes.byref(x), ctypes.byref(y)):
            continue
        pt = _to_page([_apply(matrix, x.value, y.value)], containers)[0]
        if kind == raw.FPDF_SEGMENT_BEZIERTO:
            if bezier == 0:
                anchor = prev
            bezier += 1
            if bezier == 3:
                bezier = 0
                if anchor is None:
                    return True
                if max(abs(pt[0] - anchor[0]), abs(pt[1] - anchor[1])) > CORNER_PT:
                    return True
                prev = pt
            continue
        bezier = 0
        if kind == raw.FPDF_SEGMENT_LINETO and prev is not None:
            dx = abs(pt[0] - prev[0])
            dy = abs(pt[1] - prev[1])
            if dx > DIAGONAL_PT and dy > DIAGONAL_PT:
                return True
        prev = pt
    return False


def _near(a: Box, b: Box, gap: float) -> bool:
    return (
        a[0] <= b[2] + gap
        and b[0] <= a[2] + gap
        and a[1] <= b[3] + gap
        and b[1] <= a[3] + gap
    )


def _union(a: Box, b: Box) -> Box:
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _merge(boxes: list[Box], gap: float) -> list[Box]:
    """Join boxes transitively while any two lie within ``gap`` of each other."""
    regions = list(boxes)
    changed = True
    while changed:
        changed = False
        out: list[Box] = []
        for box in regions:
            for i, r in enumerate(out):
                if _near(r, box, gap):
                    out[i] = _union(r, box)
                    changed = True
                    break
            else:
                out.append(box)
        regions = out
    return regions


def figure_regions(seeds: list[Box], rules: list[Box], page_area: float) -> list[Box]:
    """Figure boxes from drawing seeds and the axis-aligned paths around them.

    Seeds within FIGURE_GAP_PT of each other form one region; every
    axis-aligned path that overlaps a region joins it, repeatedly, so the
    boxes and connectors of a diagram end up in the region even when only
    its arrowheads are diagonal. Backdrops (a rectangle covering more than
    MAX_RULE_FRACTION of the page) never join. Regions shorter than
    MIN_FIGURE_PT or narrower than MIN_FIGURE_SIDE_PT are icons, bullets or
    braces and are dropped.
    """
    regions = _merge(seeds, FIGURE_GAP_PT)
    if not regions:
        return []
    limit = MAX_RULE_FRACTION * page_area
    rules = [r for r in rules if (r[2] - r[0]) * (r[3] - r[1]) <= limit]
    changed = True
    while changed:
        changed = False
        for rule in rules:
            for i, region in enumerate(regions):
                if _near(region, rule, 0.0) and _union(region, rule) != region:
                    regions[i] = _union(region, rule)
                    changed = True
        regions = _merge(regions, 0.0)
    return [
        r
        for r in regions
        if max(r[2] - r[0], r[3] - r[1]) >= MIN_FIGURE_PT
        and min(r[2] - r[0], r[3] - r[1]) >= MIN_FIGURE_SIDE_PT
    ]


def page_figures(pdf_page, raw) -> list[Box]:
    """Figure regions of one pypdfium2 page, in page coordinates."""
    seeds: list[Box] = []
    rules: list[Box] = []
    for obj in pdf_page.get_objects():
        if obj.type == raw.FPDF_PAGEOBJ_IMAGE:
            box = _object_box(obj, _containers(obj))
            if min(box[2] - box[0], box[3] - box[1]) >= MIN_IMAGE_PT:
                seeds.append(box)  # a header logo or an inline icon is not one
        elif obj.type == raw.FPDF_PAGEOBJ_PATH:
            containers = _containers(obj)
            box = _object_box(obj, containers)
            if _path_is_drawing(obj, raw, containers):
                seeds.append(box)
            else:
                rules.append(box)
    width, height = pdf_page.get_size()
    return figure_regions(seeds, rules, width * height)


def lines_in_regions(page: PageText, regions: list[Box]) -> list[int]:
    """Indices of the page's lines whose baseline lies inside a region."""
    out = []
    for i, ln in enumerate(page.lines):
        if not ln.segments:
            continue
        x0 = ln.segments[0].x0
        x1 = ln.segments[-1].x1
        for r in regions:
            if r[1] <= ln.y0 <= r[3] and x0 < r[2] and x1 > r[0]:
                out.append(i)
                break
    return out


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
    import pypdfium2.raw as raw  # lazy, with the package above

    started = time.perf_counter()
    pdf = pdfium.PdfDocument(str(path))
    try:
        return _extract_open(pdf, raw, started)
    finally:
        pdf.close()  # or Windows keeps the original locked


def _extract_open(pdf, raw, started: float) -> ExtractResult:
    count = len(pdf)
    chunks: list[str] = []
    pages_lines: list[list[str]] = []
    linemap: dict = {}
    figures: dict = {}
    figure_errors = 0
    numbered = 0
    previous_last: int | None = None
    for i in range(count):
        pdf_page = pdf[i]
        page = page_text(pdf_page.get_textpage(), i, pdf_page.get_size()[0])
        try:
            regions = page_figures(pdf_page, raw)
        except Exception:  # noqa: BLE001 - a page object pdfium chokes on
            regions = []  # loses figure marks on this page, never the text
            figure_errors += 1
        if regions:
            figures[str(i + 1)] = {
                "regions": [[round(v, 1) for v in r] for r in regions],
                "lines": lines_in_regions(page, regions),
            }
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
    if not bookmarks_usable(outline, count):
        outline = []
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
        figures={"pages": figures},
        figure_errors=figure_errors,
        text=text,
    )


def write_result(vdir: Path, result: ExtractResult) -> None:
    def dump(name: str, data) -> None:
        atomic_write_json(vdir / name, data, indent=1, ensure_ascii=False)

    # The meta file is what marks an extraction as current, so it goes away
    # first and comes back last: a failure in between leaves nothing that
    # is_current() would believe. The caller holds the directory's lock.
    meta_path = vdir / META_NAME
    if meta_path.exists():
        meta_path.unlink()
    atomic_write_text(vdir / EXTRACT_NAME, result.text)
    dump(OUTLINE_NAME, result.outline)
    linemap_path = vdir / LINEMAP_NAME
    if result.numbered_pages:
        dump(LINEMAP_NAME, result.linemap)
    elif linemap_path.exists():
        linemap_path.unlink()
    figures_path = vdir / FIGURES_NAME
    if result.figure_pages:
        dump(FIGURES_NAME, result.figures)
    elif figures_path.exists():
        figures_path.unlink()
    remove_store(vdir)  # tables carry section labels: read them anew
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
    for name in (EXTRACT_NAME, OUTLINE_NAME, LINEMAP_NAME, FIGURES_NAME, META_NAME):
        p = vdir / name
        if p.exists():
            p.unlink()
    remove_store(vdir)
    for dirname in (RENDERS_DIRNAME, SCHEMAS_DIRNAME):
        tree = vdir / dirname
        if tree.is_dir():
            shutil.rmtree(tree)

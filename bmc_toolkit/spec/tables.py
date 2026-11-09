"""Logical Tables: tables read from the PDF on demand, joined across pages
and stored next to the Extract.

A specification table is drawn in one of two ways. Word output (Intel,
older DMTF, NVMe) and most other producers draw ruling lines: thin filled
rectangles or stroked lines. Only those rules define the cells of a
``ruled`` table; the shaded backgrounds of header cells are ignored, so a
header stays one row and the border rectangles do not turn into phantom
columns. DMTF's current PDFs (made from Markdown) draw no rules at all:
every cell is a filled box, and the boxes tile the table edge to edge. A
``cells`` table is read from those boxes: at least two rows of at least two
boxes, rows touching, the outer edges matching from row to row; each box's
edges become the cell edges, so a merged cell stays one cell. Boxes that
lie inside a ruled table (its shaded header) are not a second table. Some
producers stroke rules as path objects that pdfplumber files as curves
(DMTF's Redfish guides draw the rows a page break cut off that way, and a
few tables whole); where neither kind of table was found, the thin curves
count as rules too, and a table read from them that overlaps one already
found is dropped, so the tables found without them never change. A
cells table has no rule that could show its last row on a page to be
complete, and an empty first cell is how it groups rows under one name, so
a continuation's first row is taken as the rest of a row the page break
cut only when its first cell and at least one other cell are empty (the
cells whose text ended before the break); a ruled table joins it when the
part before it is open-bottomed.
pdfplumber does the cell geometry and the text inside each cell; it is
imported inside the functions that open a PDF. Upright text in a cell
breaks into words at gaps of ``WORD_GAP_PT``, below pdfplumber's default of
3 pt: DMTF draws a hyperlink as its own run with no space character on
either side, about 2.1 pt from its neighbours. A cell holding rotated text
keeps the default. The text lines around a table (its caption, the lines
a section lookup reads) follow the same rule character by character:
DSP0274 sets a heading's number about 2 pt from its title.

A box diagram inside a figure (a packet or register layout, a ladder
diagram, a timing grid) is read as a table too. When no caption lies in
the 40 pt above a table, the caption of the figure it is drawn in names
it: the first ``Figure N ...`` line within 200 pt below it (DMTF, SMBus),
else the nearest within 200 pt above it (IPMI). The search stops at a line
mentioning ``Table N``, and a caption with another table between it and
this one, or (below) a table starting right under it, belongs to that
other table. Values read from such a grid are checked against the page
with ``render``.

A table that is the last body content of its page continues on the next
page when that page's first body content is a table with the same column
edges, or with the same left and right edges and inner edges that are a
subset of the other's; under a caption repeated from the page before (or
the two before) only the left and right edges must match. A table drawn
inside another's box (nested in a cell) does not count as body content
here. Running headers, footers and page numbers (lines repeated at the same
height on a neighbouring page) are not body content. A header row that a
continuation page repeats, with or without "(continued)", is dropped.

``tables.json`` in the version directory::

    {"tables_version": 8,
     "pages_done": [N, ...],          pages whose tables are all stored:
                                      the pages asked for and every page
                                      a table found there runs onto
     "tables": [{"first": a, "last": b, "index": k, "caption": str | null,
                 "section": str | null, "drawn": "ruled" | "cells",
                 "columns": [x, ...],
                 "parts": [[page, index, x0, top, x1, bottom], ...],
                 "rows": [[cell, ...], ...],
                 "row_pages": [page, ...]}, ...]}

``index`` is the table's 1-based position on its first page, ``columns``
the x positions of the column edges of all its parts (the first part's
edges, then those of later parts more than 6 pt from any taken; each row
is put on them), ``rows[0]`` the header,
``row_pages[i]`` the page ``rows[i]`` starts on (so a very long table can
be printed one page at a time).
Coordinates are PDF points with the origin top-left, as pdfplumber reports
them. ``section`` is the Outline entry in force where the table starts on
its first page: the caller is handed the body lines of that page, those
above the table first (``TableStart``), and names the entry. A store of
another version is read again: version 1 had no ``drawn`` and no cells
tables, versions up to 4 took the section from the first line holding the
caption's words, or the page top without a caption, version 5 named no
table by its figure's caption, version 6 joined words less than 3 pt apart
with no space character between them, version 7 did so in the lines
around a table.
"""

import json
import re
import textwrap
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bmc_toolkit.spec.library import atomic_write_json

TABLES_VERSION = 13
TABLES_NAME = "tables.json"

RULED = "ruled"
CELLS = "cells"
DRAWN_LABEL = {RULED: "ruled", CELLS: "cells (no ruling lines)"}

RULE_PT = 2.5  # a rectangle or line thinner than this is a ruling line
SNAP_X_PT = 6.0  # vertical rules closer than this are one column edge
SNAP_Y_PT = 4.0  # horizontal rules closer than this are one row edge
COLUMN_TOL_PT = 6.0  # column edges of two parts match within this
CAPTION_GAP_PT = 40.0  # the caption lies at most this far above the table
FIGURE_GAP_PT = 200.0  # a figure's caption lies at most this far from its boxes
LINE_TOL_PT = 2.0  # words this close vertically form one text line
FURNITURE_TOL_PT = 3.0  # a running header or footer repeats at this height
BODY_GAP_PT = 1.0  # text this close to a rule is inside the table, not around it
CELL_WIDTH = 60  # grid columns wrap beyond this many characters
WORD_GAP_PT = 1.75  # upright characters this far apart are separate words

_CAPTION = re.compile(r"^(?:\d{1,5}\s+)?(?P<text>(?:Table|Figure)\b.*)$", re.IGNORECASE)
# "Figure", an id (B-1, 6-2, 3.4), an optional separator, then a title: not
# "Figure 3 shows ...", "Figure 101." or "Figure 223Figure 223)."
_FIGURE_CAPTION = re.compile(
    r"^(?:\d{1,5}\s+)?(?P<text>Figure\s+[A-Z]?-?\d+(?:[-.]\d+)*(?!\d)\s*"
    r"[:,.–—-]?\s*(?P<title>\S.*))$"
)
# a table's id: a number as wide as extract.py's (6-2, A.1, G-1, AA-1), or
# a Roman numeral (any case) or an upper-case single letter before
# whitespace, a separator or the end ("Table II - ...", "table ii - ...",
# "Table A: ..."; not "Table I/O", "table a, b")
_ID = (
    r"(?:(?:[A-Z]{1,2}[.-]?)?\d+(?:[-.]\d+)*(?!\d)"
    r"|(?:[IVXL]+|(?-i:[A-Z]))(?=\s|[:,.–—-]|$))"
)
# the same shape for "Table": not "Table 3 lists ..." or "Table 31 and ..."
_TABLE_CAPTION = re.compile(
    r"^(?:\d{1,5}\s+)?(?P<text>Table\s+" + _ID + r"\s*"
    r"[:,.–—-]?\s*(?P<title>\S.*))$",
    re.IGNORECASE,
)
# "Table" in any case and an id; not "table." or "Table of contents"
_TABLE_ID = re.compile(r"Table\s+" + _ID, re.IGNORECASE)
_TABLE_MENTION = re.compile(r"\bTable\s+[A-Z]?-?\d", re.IGNORECASE)
_CONTINUED = re.compile(r"\s*\((?:continued|cont\.?)\)\s*", re.IGNORECASE)
_DIGITS = re.compile(r"\d+")


class TableError(Exception):
    """A PDF could not be read for tables."""


@dataclass(frozen=True)
class TextLine:
    top: float
    bottom: float
    x0: float
    text: str


@dataclass
class PageTable:
    """One table as it stands on one page."""

    page: int
    index: int  # 0-based, top to bottom on the page
    bbox: tuple[float, float, float, float]  # x0, top, x1, bottom
    columns: list[float]  # x of the column edges, one more than the columns
    rows: list[list[str]]
    open_bottom: bool = False  # no rule under the last row: the page break cut it
    # (a cells table has no rule to look for: every continued part counts as open)
    drawn: str = RULED  # RULED or CELLS

    @property
    def top(self) -> float:
        return self.bbox[1]

    @property
    def bottom(self) -> float:
        return self.bbox[3]


@dataclass(frozen=True)
class TableStart:
    """What a section lookup is given for a table: the body lines of its
    first page, the ``above`` lines over the table first, each group top
    to bottom."""

    lines: list[str]
    above: int


@dataclass
class PageInfo:
    number: int
    tables: list[PageTable]
    lines: list[TextLine]


@dataclass
class LogicalTable:
    first: int
    last: int
    index: int  # 1-based position on the first page
    caption: str | None
    section: str | None
    columns: list[float]
    parts: list[list[float]]  # [page, index, x0, top, x1, bottom] per page
    rows: list[list[str]]
    drawn: str = RULED
    row_pages: list[int] | None = None  # the page each row starts on

    @property
    def header(self) -> list[str]:
        return self.rows[0] if self.rows else []

    def rows_on(self, page: int) -> list[int]:
        """Indices of the rows that start on ``page`` (every row when the
        store predates ``row_pages``)."""
        if not self.row_pages or len(self.row_pages) != len(self.rows):
            return list(range(len(self.rows)))
        return [i for i, p in enumerate(self.row_pages) if p == page]

    @property
    def width(self) -> int:
        return max((len(r) for r in self.rows), default=0)

    def covers(self, page: int) -> bool:
        return self.first <= page <= self.last

    def part_on(self, page: int) -> list[float] | None:
        for part in self.parts:
            if int(part[0]) == page:
                return part
        return None

    def to_dict(self) -> dict:
        return {
            "first": self.first,
            "last": self.last,
            "index": self.index,
            "caption": self.caption,
            "section": self.section,
            "drawn": self.drawn,
            "columns": self.columns,
            "parts": self.parts,
            "rows": self.rows,
            "row_pages": self.row_pages,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LogicalTable":
        return cls(
            first=int(data["first"]),
            last=int(data["last"]),
            index=int(data["index"]),
            caption=data.get("caption"),
            section=data.get("section"),
            columns=[float(x) for x in data.get("columns", [])],
            parts=[list(p) for p in data.get("parts", [])],
            rows=[[str(c) for c in row] for row in data.get("rows", [])],
            drawn=str(data.get("drawn", RULED)),
            row_pages=(
                [int(p) for p in data["row_pages"]]
                if isinstance(data.get("row_pages"), list)
                else None
            ),
        )


# ------------------------------------------------------------ reading


def _require_pdfplumber():
    try:
        import pdfplumber
    except ImportError as exc:
        raise ImportError("pdfplumber is not installed") from exc
    return pdfplumber


def _is_rule(obj) -> tuple[bool, bool]:
    """(horizontal, vertical): whether a rect or line object is a thin rule."""
    w = obj["x1"] - obj["x0"]
    h = obj["bottom"] - obj["top"]
    return (h <= RULE_PT < w, w <= RULE_PT < h)


def page_rules(page) -> tuple[list, list]:
    """The page's horizontal and vertical ruling lines: thin rects and lines."""
    horizontal, vertical = [], []
    for obj in list(page.rects) + list(page.lines):
        is_h, is_v = _is_rule(obj)
        if is_h:
            horizontal.append(obj)
        elif is_v:
            vertical.append(obj)
    return horizontal, vertical


def _cell_text(text) -> str:
    return "\n".join(ln.strip() for ln in (text or "").split("\n")).strip()


def _in_box(char: dict, box) -> bool:
    """pdfplumber's own test: the character's centre is inside the box."""
    x0, top, x1, bottom = box
    h_mid = (char["x0"] + char["x1"]) / 2
    v_mid = (char["top"] + char["bottom"]) / 2
    return x0 <= h_mid < x1 and top <= v_mid < bottom


def _extract(table) -> list[list[str | None]]:
    """``table.extract()`` with the word gap set per cell: WORD_GAP_PT when
    every character in the cell is upright, pdfplumber's default otherwise
    (in a box diagram's rotated labels a narrow gap is not a word break)."""
    from pdfplumber import utils

    rows = []
    for row in table.rows:
        row_chars = [c for c in table.page.chars if _in_box(c, row.bbox)]
        cells = []
        for cell in row.cells:
            if cell is None:
                cells.append(None)
                continue
            chars = [c for c in row_chars if _in_box(c, cell)]
            if not chars:
                cells.append("")
            elif all(c["upright"] for c in chars):
                cells.append(utils.extract_text(chars, x_tolerance=WORD_GAP_PT))
            else:
                cells.append(utils.extract_text(chars))
        rows.append(cells)
    return rows


def _closing_rules(horizontal: list, vertical: list) -> list[dict]:
    """Horizontal rules that close the top and the bottom of every run of
    vertical rules that lacks one: a table cut by the page break has no
    border on the cut side, and pdfplumber needs a closed cell."""
    runs: list[list[float]] = []  # [top, bottom, x0, x1]
    for v in sorted(vertical, key=lambda o: o["top"]):
        for run in runs:
            if v["top"] <= run[1] + SNAP_Y_PT and v["bottom"] >= run[0] - SNAP_Y_PT:
                run[0] = min(run[0], v["top"])
                run[1] = max(run[1], v["bottom"])
                run[2] = min(run[2], v["x0"])
                run[3] = max(run[3], v["x1"])
                break
        else:
            runs.append([v["top"], v["bottom"], v["x0"], v["x1"]])
    tops = [h["top"] for h in horizontal]
    extra = []
    for top, bottom, x0, x1 in runs:
        for y in (top, bottom):
            if not any(abs(y - t) <= SNAP_Y_PT for t in tops):
                extra.append(
                    {
                        "object_type": "line",
                        "x0": x0,
                        "x1": x1,
                        "top": y,
                        "bottom": y,
                        "width": x1 - x0,
                        "height": 0.0,
                    }
                )
    return extra


def page_tables(page, number: int) -> list[PageTable]:
    """The tables on a pdfplumber page, top to bottom: ruled tables first,
    then tables drawn as tiled cell boxes outside them, then tables whose
    rules are drawn as path curves outside both."""
    drawn, vertical = page_rules(page)
    found = _ruled_tables(page, number, drawn, vertical)
    boxes = page_boxes(page)
    boxes = [b for b in boxes if not any(_inside(b, t.bbox) for t in found)]
    found += _cell_tables(page, number, boxes)
    found += _curve_tables(page, number, drawn, vertical, found)
    found.sort(key=lambda t: t.top)
    for i, t in enumerate(found):
        t.index = i
    return found


def _settings(horizontal: list, vertical: list) -> dict:
    return {
        "vertical_strategy": "explicit",
        "horizontal_strategy": "explicit",
        "explicit_vertical_lines": vertical,
        "explicit_horizontal_lines": horizontal,
        "snap_x_tolerance": SNAP_X_PT,
        "snap_y_tolerance": SNAP_Y_PT,
        "join_x_tolerance": SNAP_X_PT,
        "join_y_tolerance": SNAP_Y_PT,
        "intersection_x_tolerance": SNAP_X_PT,
        "intersection_y_tolerance": SNAP_Y_PT,
    }


def _tables_from(page, number: int, settings: dict, drawn_as: str) -> list[PageTable]:
    """PageTables for every table pdfplumber finds with ``settings``."""
    found = []
    for table in page.find_tables(settings):
        rows = [[_cell_text(c) for c in row] for row in _extract(table)]
        if not rows:
            continue
        columns = sorted({round(c[0], 1) for row in table.rows for c in row.cells if c})
        columns.append(round(table.bbox[2], 1))
        if len(columns) < 3 and len(rows) < 2:
            continue  # a framed block of text, not a table
        if not any(cell for row in rows for cell in row):
            continue
        found.append(
            PageTable(
                page=number,
                index=0,
                bbox=tuple(float(v) for v in table.bbox),
                columns=columns,
                rows=rows,
                drawn=drawn_as,
            )
        )
    return found


def _ruled_tables(page, number: int, drawn: list, vertical: list) -> list[PageTable]:
    if len(vertical) < 2:  # an underline or a bar, not a grid
        return []
    horizontal = drawn + _closing_rules(drawn, vertical)
    if len(horizontal) < 2:  # pdfplumber wants two explicit lines each way
        return []
    found = _tables_from(page, number, _settings(horizontal, vertical), RULED)
    for t in found:
        t.open_bottom = not any(abs(h["top"] - t.bottom) <= SNAP_Y_PT for h in drawn)
    return found


def _curve_rules(page) -> tuple[list, list]:
    """The page's horizontal and vertical rules drawn as path curves: a
    stroked path whose box is thin one way (a straight Bezier segment, a
    polyline along one edge). Boxes, diagonals and arcs are not rules."""
    horizontal, vertical = [], []
    for obj in page.curves:
        is_h, is_v = _is_rule(obj)
        if is_h:
            horizontal.append(obj)
        elif is_v:
            vertical.append(obj)
    return horizontal, vertical


def _overlaps(a: tuple, b: tuple) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _curve_tables(
    page, number: int, drawn: list, vertical: list, found: list[PageTable]
) -> list[PageTable]:
    """Ruled tables read where no table was found, from the rules there
    with the curve rules added. Some producers stroke a table's rules, or
    only the rows a page break cut off, as path curves; reading curves as
    rules everywhere would redraw tables found today (a cells table whose
    boxes carry curve borders, a curve grid that splits a ruled table's
    columns), so curves only fill in. A table from them that overlaps one
    found already is dropped."""
    curve_h, curve_v = _curve_rules(page)
    if not curve_h and not curve_v:
        return []
    horizontal = [
        o for o in drawn + curve_h if not any(_inside(o, t.bbox) for t in found)
    ]
    vertical = [
        o for o in vertical + curve_v if not any(_inside(o, t.bbox) for t in found)
    ]
    # _ruled_tables closes the runs of these rules again, so a stray drawn
    # vertical rule beside a found table may get closing rules here that
    # the first pass did not give it
    extra = [
        t
        for t in _ruled_tables(page, number, horizontal, vertical)
        if not any(_overlaps(t.bbox, f.bbox) for f in found)
    ]
    return extra


# ------------------------------------------------------ cell boxes


def page_boxes(page) -> list[dict]:
    """The page's filled rectangles that are not ruling lines."""
    out = []
    for obj in page.rects:
        if not obj.get("fill", True):
            continue
        if obj["x1"] - obj["x0"] > RULE_PT and obj["bottom"] - obj["top"] > RULE_PT:
            out.append(obj)
    return out


def _inside(box: dict, bbox: tuple[float, float, float, float]) -> bool:
    x0, top, x1, bottom = bbox
    return (
        box["x0"] >= x0 - SNAP_X_PT
        and box["x1"] <= x1 + SNAP_X_PT
        and box["top"] >= top - SNAP_Y_PT
        and box["bottom"] <= bottom + SNAP_Y_PT
    )


def _box_rows(boxes: list[dict]) -> list[list[dict]]:
    """Boxes grouped into rows: the same top and bottom, sorted left to
    right, each row split where two neighbours do not touch."""
    bands: list[list[dict]] = []
    for box in sorted(boxes, key=lambda b: (b["top"], b["x0"])):
        for band in bands:
            first = band[0]
            if (
                abs(box["top"] - first["top"]) <= SNAP_Y_PT
                and abs(box["bottom"] - first["bottom"]) <= SNAP_Y_PT
            ):
                band.append(box)
                break
        else:
            bands.append([box])
    rows = []
    for band in bands:
        band.sort(key=lambda b: b["x0"])
        run = [band[0]]
        for box in band[1:]:
            if abs(box["x0"] - run[-1]["x1"]) <= SNAP_X_PT:
                run.append(box)
            else:
                rows.append(run)
                run = [box]
        rows.append(run)
    rows.sort(key=lambda r: (r[0]["top"], r[0]["x0"]))
    return rows


def box_grids(boxes: list[dict]) -> list[list[list[dict]]]:
    """Runs of touching box rows that make a table: consecutive rows whose
    outer edges match and that touch vertically, at least two rows, the
    first and the last of them with at least two boxes each."""
    grids: list[list[list[dict]]] = []
    for row in _box_rows(boxes):
        x0, x1 = row[0]["x0"], row[-1]["x1"]
        for grid in grids:
            last = grid[-1]
            if (
                abs(row[0]["top"] - last[-1]["bottom"]) <= SNAP_Y_PT
                and abs(x0 - last[0]["x0"]) <= COLUMN_TOL_PT
                and abs(x1 - last[-1]["x1"]) <= COLUMN_TOL_PT
            ):
                grid.append(row)
                break
        else:
            grids.append([row])
    out = []
    for grid in grids:
        while grid and len(grid[0]) < 2:
            grid = grid[1:]
        while grid and len(grid[-1]) < 2:
            grid = grid[:-1]
        if len(grid) >= 2:
            out.append(grid)
    return out


def _edge(x0: float, top: float, x1: float, bottom: float) -> dict:
    return {
        "object_type": "line",
        "x0": x0,
        "x1": x1,
        "top": top,
        "bottom": bottom,
        "width": x1 - x0,
        "height": bottom - top,
    }


def _cell_tables(page, number: int, boxes: list[dict]) -> list[PageTable]:
    """Tables drawn as tiled boxes: every box's four edges are the cell
    edges, so pdfplumber sees each box as one cell, merged cells included."""
    horizontal, vertical = [], []
    for grid in box_grids(boxes):
        for row in grid:
            for b in row:
                horizontal.append(_edge(b["x0"], b["top"], b["x1"], b["top"]))
                horizontal.append(_edge(b["x0"], b["bottom"], b["x1"], b["bottom"]))
                vertical.append(_edge(b["x0"], b["top"], b["x0"], b["bottom"]))
                vertical.append(_edge(b["x1"], b["top"], b["x1"], b["bottom"]))
    if not horizontal:
        return []
    return _tables_from(page, number, _settings(horizontal, vertical), CELLS)


def _words(page) -> list[dict]:
    """The page's words with the gap rule ``_extract`` applies to a cell,
    taken here per character: upright characters break at WORD_GAP_PT, the
    others at pdfplumber's default."""
    upright = page.filter(
        lambda o: o.get("object_type") == "char" and o.get("upright", True)
    )
    turned = page.filter(
        lambda o: o.get("object_type") == "char" and not o.get("upright", True)
    )
    return upright.extract_words(x_tolerance=WORD_GAP_PT) + turned.extract_words()


def page_lines(page) -> list[TextLine]:
    """The page's words grouped into text lines, top to bottom."""
    words = sorted(_words(page), key=lambda w: (w["top"], w["x0"]))
    lines: list[TextLine] = []
    group: list[dict] = []

    def flush() -> None:
        if not group:
            return
        group.sort(key=lambda w: w["x0"])
        lines.append(
            TextLine(
                top=min(w["top"] for w in group),
                bottom=max(w["bottom"] for w in group),
                x0=group[0]["x0"],
                text=" ".join(w["text"] for w in group),
            )
        )

    for w in words:
        if group and abs(w["top"] - group[0]["top"]) > LINE_TOL_PT:
            flush()
            group = []
        group.append(w)
    flush()
    return lines


class Reader:
    """A PDF opened for tables; pages are read once and kept as PageInfo."""

    def __init__(self, path: Path):
        pdfplumber = _require_pdfplumber()
        try:
            self._pdf = pdfplumber.open(str(path))
        except Exception as exc:  # pdfminer raises its own hierarchy
            raise TableError(f"cannot open {path}: {exc}") from exc
        self._pages: dict[int, PageInfo] = {}

    def __enter__(self) -> "Reader":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._pdf.close()

    @property
    def page_count(self) -> int:
        return len(self._pdf.pages)

    def page(self, number: int) -> PageInfo:
        info = self._pages.get(number)
        if info is None:
            page = self._pdf.pages[number - 1]
            try:
                info = PageInfo(number, page_tables(page, number), page_lines(page))
            except Exception as exc:  # noqa: BLE001 - pdfminer's own hierarchy
                raise TableError(f"cannot read page {number}: {exc}") from exc
            finally:
                page.close()
            self._pages[number] = info
        return info

    # ------------------------------------------------ page furniture

    def furniture(self, number: int) -> set[int]:
        """Indices of the page's lines that are running headers, footers or
        page numbers: the same words (digits aside, order aside, since facing
        pages mirror their layout) at the same height on one of the two
        pages before or after. A caption-like line with a table right
        under it is not: NVMe repeats a figure's caption at the top of
        each page the figure runs over."""
        info = self.page(number)
        tops: dict[str, list[float]] = {}
        for n in (number - 2, number - 1, number + 1, number + 2):
            if 1 <= n <= self.page_count:
                for other in self.page(n).lines:
                    tops.setdefault(_furniture_key(other.text), []).append(other.top)
        out = set()
        for i, line in enumerate(info.lines):
            if _captions_a_table(info, line):
                continue
            for top in tops.get(_furniture_key(line.text), ()):
                if abs(top - line.top) <= FURNITURE_TOL_PT:
                    out.add(i)
                    break
        return out

    def body_lines(self, number: int) -> list[TextLine]:
        info = self.page(number)
        skip = self.furniture(number)
        return [ln for i, ln in enumerate(info.lines) if i not in skip]

    def body_below(self, table: PageTable) -> bool:
        return any(
            ln.top > table.bottom - BODY_GAP_PT for ln in self.body_lines(table.page)
        )

    def caption(self, table: PageTable) -> str | None:
        """The nearest body line within CAPTION_GAP_PT above the table that
        reads like a caption, past lines that do not (IPMI draws its column
        names between caption and rules, PMBus a note) but not past another
        table; else the caption of the figure the table is drawn in; else a
        `Table` caption ending within CAPTION_GAP_PT above
        (_caption_to_line_bottom); else a `Table` caption ending the page
        before (_caption_on_page_before)."""
        above = sorted(
            (
                ln
                for ln in self.body_lines(table.page)
                if ln.bottom < table.top + BODY_GAP_PT
                and ln.top >= table.top - CAPTION_GAP_PT
            ),
            key=lambda ln: -ln.top,
        )
        for i, line in enumerate(above):
            m = _CAPTION.match(line.text.strip())
            if not m or self._table_between(table, line.bottom, table.top):
                continue
            text = m.group("text").strip()
            # past the nearest line, a Figure line must pass the figure
            # rule's prose filter ("Figure 3 shows ..." is not a caption)
            if i and text[:6].lower() == "figure" and figure_caption(line.text) is None:
                continue
            return text
        return (
            self._figure_caption(table)
            or self._caption_to_line_bottom(table)
            or self._caption_on_page_before(table)
        )

    def _caption_to_line_bottom(self, table: PageTable) -> str | None:
        """The nearest `Table` caption whose bottom, not top, lies within
        CAPTION_GAP_PT above the table, with no other table between (PMBus
        Table 31: its top lies 47 pt up, past two note lines). Only a
        `Table` line: measuring to the bottom for every caption took a
        prose line starting "Figure 24 —" over DSP0274's own caption."""
        above = sorted(
            (
                ln
                for ln in self.body_lines(table.page)
                if ln.bottom < table.top + BODY_GAP_PT
                and ln.bottom >= table.top - CAPTION_GAP_PT
            ),
            key=lambda ln: -ln.top,
        )
        for line in above:
            text = _table_caption(line.text)
            if text and not self._table_between(table, line.bottom, table.top):
                return text
        return None

    def _caption_on_page_before(self, table: PageTable) -> str | None:
        """A table that starts its page with no body line above it takes the
        last body line of the page before when that line is a `Table`
        caption below every table there (IPMI and DSP2058 leave a caption
        at the foot of a page when the table does not fit). A `Figure`
        line is not taken: SMBus puts a figure's caption under its
        drawing."""
        if table.index != 0 or table.page == 1:
            return None
        if any(
            ln.bottom < table.top + BODY_GAP_PT for ln in self.body_lines(table.page)
        ):
            return None
        body = self.body_lines(table.page - 1)
        if not body:
            return None
        last = max(body, key=lambda ln: ln.top)
        if any(
            last.top <= t.bottom - BODY_GAP_PT for t in self.page(table.page - 1).tables
        ):
            return None
        m = _CAPTION.match(last.text.strip())
        # "Table" in any case, then an id: not a wrapped "table." or
        # "table below:" ending a sentence (PR #118 F2)
        if not m or not _TABLE_ID.match(m.group("text")):
            return None
        return m.group("text").strip()

    def _figure_caption(self, table: PageTable) -> str | None:
        """A Figure caption within FIGURE_GAP_PT of the table: the first one
        below it, else the nearest above it. Box diagrams read as tables
        have their caption under the figure (DMTF, SMBus) or over it
        (IPMI). A caption with a table right under it names that table
        (NVMe captions its tables "Figure N" above them), and one with
        another table between is not this table's."""
        lines = self.body_lines(table.page)
        below = sorted(
            (
                ln
                for ln in lines
                if table.bottom - BODY_GAP_PT < ln.top <= table.bottom + FIGURE_GAP_PT
            ),
            key=lambda ln: ln.top,
        )
        line = _first_figure_caption(below)
        if (
            line is not None
            and not self._table_between(table, table.bottom, line.top)
            and not self._table_under(table, line)
        ):
            return figure_caption(line.text)
        above = sorted(
            (
                ln
                for ln in lines
                if ln.bottom < table.top + BODY_GAP_PT
                and ln.top >= table.top - FIGURE_GAP_PT
            ),
            key=lambda ln: -ln.top,
        )
        line = _first_figure_caption(above)
        if line is not None and not self._table_between(table, line.bottom, table.top):
            return figure_caption(line.text)
        return None

    def _table_between(self, table: PageTable, top: float, bottom: float) -> bool:
        return any(
            t is not table and t.top < bottom and t.bottom > top
            for t in self.page(table.page).tables
        )

    def _table_under(self, table: PageTable, line: TextLine) -> bool:
        return any(
            t is not table and line.bottom < t.top <= line.bottom + CAPTION_GAP_PT
            for t in self.page(table.page).tables
        )

    # ------------------------------------------------- continuation

    def outer_tables(self, number: int) -> list[PageTable]:
        """The page's tables less those nested in another table's cells
        (NVMe draws a Value/Definition table inside a field's cell)."""
        tables = self.page(number).tables
        return [t for t in tables if not any(_nested_in(t, o) for o in tables)]

    def continues(self, a: PageTable, b: PageTable) -> bool:
        """True when table ``b`` (first on its page) carries on table ``a``
        (last on the page before), nested tables aside. The column edges
        match, or one part's are a subset of the other's; under a repeated
        caption only the outer frame must match (an NVMe figure's inner
        columns change with what its cells hold)."""
        if b.page != a.page + 1:
            return False
        before, after = self.outer_tables(a.page), self.outer_tables(b.page)
        if not before or before[-1] is not a or not after or after[0] is not b:
            return False
        if self.body_below(a):
            return False
        above = [
            ln for ln in self.body_lines(b.page) if ln.bottom < b.top + BODY_GAP_PT
        ]
        if not (
            columns_match(a.columns, b.columns)
            or _columns_subset(a.columns, b.columns)
            or (above and _frame_match(a.columns, b.columns))
        ):
            return False
        # a caption repeated from the page before, or one of the two before
        # that (a page the table fills from its top has no room for the
        # caption: NVMe Figure 338), does not stop the join; any other
        # line, a new caption among them, does. Only a line that captions a
        # table there counts as a caption to repeat.
        repeats = {
            _caption_key(ln.text)
            for n in range(max(1, a.page - 2), a.page + 1)
            for ln in self.page(n).lines
            if _captions_a_table(self.page(n), ln)
        }
        return all(
            _CAPTION.match(ln.text.strip()) and _caption_key(ln.text) in repeats
            for ln in above
        )

    def logical_tables(
        self,
        number: int,
        section_of: Callable[[int, TableStart], str | None] | None = None,
    ) -> list[LogicalTable]:
        """Every Logical Table that touches the page, top to bottom."""
        return self.read_page(number, section_of)[0]

    def read_page(
        self,
        number: int,
        section_of: Callable[[int, TableStart], str | None] | None = None,
    ) -> tuple[list[LogicalTable], list[LogicalTable], list[int]]:
        """(the Logical Tables touching the page, top to bottom; every
        Logical Table assembled on the way; the pages whose tables are all
        among them).

        A table found from the page may run onto other pages; those pages'
        remaining tables are assembled too, so a later call for any of them
        can be answered from the store."""
        found: dict[tuple[int, int], LogicalTable] = {}
        done: set[int] = set()
        pending = [number]
        while pending:
            page = pending.pop()
            if page in done:
                continue
            done.add(page)
            for table in self.page(page).tables:
                if any(_holds(lt, table) for lt in found.values()):
                    continue
                lt = self._walk(table, section_of)
                found[(lt.first, lt.index)] = lt
                pending.extend(
                    int(part[0]) for part in lt.parts if int(part[0]) not in done
                )
        on_page = [t for t in found.values() if t.covers(number)]
        return sort_on_page(on_page, number), list(found.values()), sorted(done)

    def _walk(self, table: PageTable, section_of) -> LogicalTable:
        parts = [table]
        cur = table
        while cur.page > 1:
            prev = self.outer_tables(cur.page - 1)
            if not prev or not self.continues(prev[-1], cur):
                break
            cur = prev[-1]
            parts.insert(0, cur)
        cur = table
        while cur.page < self.page_count:
            nxt = self.outer_tables(cur.page + 1)
            if not nxt or not self.continues(cur, nxt[0]):
                break
            cur = nxt[0]
            parts.append(cur)
        return self._assemble(parts, section_of)

    def _assemble(self, parts: list[PageTable], section_of) -> LogicalTable:
        first = parts[0]
        # the parts' rows on one column set: the union of their edges
        columns = union_columns([p.columns for p in parts])
        rows: list[list[str]] = [
            spread_row(r, first.columns, columns) for r in first.rows
        ]
        row_pages = [first.page] * len(rows)
        previous = first
        for part in parts[1:]:
            spread = [spread_row(r, part.columns, columns) for r in part.rows]
            more = drop_repeated_header(rows, spread)
            more = drop_repeated_header(rows, more)  # a "(continued)" sub-header too
            if len(more) == len(spread) and len(part.columns) == len(first.columns):
                # inner edges moved (a frame join): the header as drawn
                own = drop_repeated_header(first.rows, part.rows)
                own = drop_repeated_header(first.rows, own)
                more = spread[len(part.rows) - len(own) :]
            # the cut-row checks read the row as drawn, not the empty cells
            # spread_row adds for the edges a cell spans
            drawn = part.rows[len(part.rows) - len(more)] if more else []
            if previous.drawn == CELLS:
                cut = bool(more) and _is_partial_row(drawn)
            else:
                cut = previous.open_bottom
            if more and rows and cut and _is_cut_row(drawn):
                rows[-1] = join_cells(rows[-1], more[0])
                more = more[1:]
            rows.extend(more)
            row_pages.extend([part.page] * len(more))
            previous = part
        caption = self.caption(first)
        section = None
        if section_of:  # the entry in force where the table starts
            body = sorted(self.body_lines(first.page), key=lambda ln: ln.top)
            above = [ln for ln in body if ln.bottom < first.top + BODY_GAP_PT]
            rest = [ln for ln in body if ln not in above]
            start = TableStart([ln.text for ln in above + rest], len(above))
            section = section_of(first.page, start)
        return LogicalTable(
            first=first.page,
            last=parts[-1].page,
            index=first.index + 1,
            caption=caption,
            section=section,
            columns=columns,
            parts=[[p.page, p.index, *[round(v, 1) for v in p.bbox]] for p in parts],
            rows=rows,
            drawn=first.drawn,
            row_pages=row_pages,
        )


def figure_caption(text: str) -> str | None:
    """The caption in a line that reads like a Figure caption, without a
    margin line number; None for prose that starts with "Figure"."""
    m = _FIGURE_CAPTION.match(text.strip())
    if not m:
        return None
    title = m.group("title")
    if title[0].islower() or title.startswith(("Figure", ")")):
        return None
    if not any(c.isalpha() for c in title):
        return None
    return m.group("text").strip()


def _table_caption(text: str) -> str | None:
    """The caption in a line that reads like a Table caption, without a
    margin line number; None for prose that starts with "Table": "Table 3
    lists ...", "Table 12, Table 13 and ...", "Table 3 (above) ..."."""
    m = _TABLE_CAPTION.match(text.strip())
    if not m:
        return None
    title = m.group("title")
    if title[0].islower() or _TABLE_ID.match(title):
        return None
    if title[0] in "()" and not _CONTINUED.fullmatch(title):
        return None
    if not any(c.isalpha() for c in title):
        return None
    return m.group("text").strip()


def _first_figure_caption(lines: list[TextLine]) -> TextLine | None:
    """The first of ``lines`` that is a Figure caption; None when a line
    mentioning a table comes first (that caption names the table)."""
    for ln in lines:
        if _TABLE_MENTION.search(ln.text):
            return None
        if figure_caption(ln.text):
            return ln
    return None


def _holds(table: LogicalTable, part: PageTable) -> bool:
    return any(int(p[0]) == part.page and int(p[1]) == part.index for p in table.parts)


def _furniture_key(text: str) -> str:
    return " ".join(sorted(_DIGITS.sub("", text).lower().split()))


def _caption_key(text: str) -> str:
    """A caption line without its margin line number, spacing aside."""
    m = _CAPTION.match(text.strip())
    return " ".join((m.group("text") if m else text).split())


def _captions_a_table(info: PageInfo, line: TextLine) -> bool:
    """True when ``line`` reads like a caption and a table on its page
    starts within CAPTION_GAP_PT under it (the caption rule's window)."""
    if not _CAPTION.match(line.text.strip()):
        return False
    return any(
        line.bottom < t.top + BODY_GAP_PT and line.top >= t.top - CAPTION_GAP_PT
        for t in info.tables
    )


def columns_match(a: list[float], b: list[float]) -> bool:
    if len(a) != len(b):
        return False
    return all(abs(x - y) <= COLUMN_TOL_PT for x, y in zip(a, b, strict=True))


def _frame_match(a: list[float], b: list[float]) -> bool:
    """The two parts' left and right edges match."""
    return abs(a[0] - b[0]) <= COLUMN_TOL_PT and abs(a[-1] - b[-1]) <= COLUMN_TOL_PT


def _columns_subset(a: list[float], b: list[float]) -> bool:
    """The frames match and every edge of the part with fewer lies on an
    edge of the other (a column split on some pages only)."""
    if not _frame_match(a, b):
        return False
    fewer, more = (a, b) if len(a) <= len(b) else (b, a)
    return all(any(abs(x - y) <= COLUMN_TOL_PT for y in more) for x in fewer)


def _nested_in(table: PageTable, other: PageTable) -> bool:
    """True when ``table`` lies inside ``other``'s box, in one of its cells."""
    if table is other:
        return False
    (x0, top, x1, bottom), (ox0, otop, ox1, obottom) = table.bbox, other.bbox
    inside = (
        ox0 - BODY_GAP_PT <= x0
        and otop - BODY_GAP_PT <= top
        and x1 <= ox1 + BODY_GAP_PT
        and bottom <= obottom + BODY_GAP_PT
    )
    return inside and (x1 - x0) * (bottom - top) < (ox1 - ox0) * (obottom - otop)


def union_columns(parts: list[list[float]]) -> list[float]:
    """The column edges of all parts, the first part's first; an edge
    within COLUMN_TOL_PT of one already taken is that edge."""
    edges = list(parts[0])
    for columns in parts[1:]:
        for x in columns:
            if all(abs(x - e) > COLUMN_TOL_PT for e in edges):
                edges.append(x)
    return sorted(edges)


def spread_row(row: list[str], edges: list[float], union: list[float]) -> list[str]:
    """A part's row on the union of the column edges, empty cells over the
    edges a cell spans. The cells are placed in order, one to a union edge:
    each under the first free edge within COLUMN_TOL_PT of its left edge,
    else the nearest free one. A part whose edges match the union within
    COLUMN_TOL_PT keeps its row as it is."""
    width = len(union) - 1
    if len(row) != len(edges) - 1 or columns_match(edges, union):
        return row + [""] * (width - len(row))
    if len(row) > width:  # edges closer than COLUMN_TOL_PT are one in the union
        return row
    out = [""] * width
    j = -1
    for i, cell in enumerate(row):
        free = range(j + 1, width - (len(row) - i) + 1)  # room for the rest
        near = [k for k in free if abs(union[k] - edges[i]) <= COLUMN_TOL_PT]
        j = near[0] if near else min(free, key=lambda k: abs(union[k] - edges[i]))
        out[j] = cell
    return out


def _row_key(row: list[str]) -> tuple[str, ...]:
    return tuple(" ".join(_CONTINUED.sub(" ", c).split()).lower() for c in row)


def drop_repeated_header(
    so_far: list[list[str]], rows: list[list[str]]
) -> list[list[str]]:
    """``rows`` without its first row when that row repeats the table's
    header, or carries "(continued)" and repeats an earlier row (a
    sub-header). A body row that merely looks like an earlier one stays."""
    if not rows or not so_far:
        return rows
    key = _row_key(rows[0])
    if key == _row_key(so_far[0]):
        return rows[1:]
    marked = any(_CONTINUED.search(c) for c in rows[0])
    if marked and key in {_row_key(r) for r in so_far}:
        return rows[1:]
    return rows


def _is_cut_row(row: list[str]) -> bool:
    """A continuation page's first row with an empty first cell may be the
    rest of a row the page break cut; the caller also checks that the part
    before it had no rule under its last row."""
    return bool(row) and not row[0].strip() and any(c.strip() for c in row)


def _is_partial_row(row: list[str]) -> bool:
    """A cells table has no rule to show a row cut, and an empty first cell
    alone is how it groups rows: a continuation row is the rest of a cut
    one only when another cell is empty too (the cells whose text ended
    before the page break)."""
    return any(not c.strip() for c in row[1:])


def join_cells(a: list[str], b: list[str]) -> list[str]:
    width = max(len(a), len(b))
    a = a + [""] * (width - len(a))
    b = b + [""] * (width - len(b))
    return [
        "\n".join(part for part in (x, y) if part) for x, y in zip(a, b, strict=True)
    ]


# --------------------------------------------------------------- store


def _read_store(vdir: Path) -> dict:
    path = vdir / TABLES_NAME
    if not path.is_file():
        return {"tables_version": TABLES_VERSION, "pages_done": [], "tables": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict) or data.get("tables_version") != TABLES_VERSION:
        return {"tables_version": TABLES_VERSION, "pages_done": [], "tables": []}
    data.setdefault("pages_done", [])
    data.setdefault("tables", [])
    return data


def stored_for_page(vdir: Path, page: int) -> list[LogicalTable] | None:
    """The stored Logical Tables touching the page, or None when the page
    has not been read yet (a stored table may cross a page whose other
    tables were never extracted)."""
    data = _read_store(vdir)
    if page not in data["pages_done"]:
        return None
    tables = [LogicalTable.from_dict(t) for t in data["tables"]]
    return sort_on_page([t for t in tables if t.covers(page)], page)


def store(vdir: Path, pages, tables: list[LogicalTable]) -> Path:
    """Record the tables found while reading ``pages`` (one number or a
    list); a table already stored for the same first page and index is
    replaced. The store is re-read here and written atomically; the caller
    holds the version directory's lock, so two Sessions that read different
    pages both keep their tables."""
    if isinstance(pages, int):
        pages = [pages]
    data = _read_store(vdir)
    keep = []
    new_keys = {(t.first, t.index) for t in tables}
    for entry in data["tables"]:
        if (int(entry["first"]), int(entry["index"])) not in new_keys:
            keep.append(entry)
    keep.extend(t.to_dict() for t in tables)
    keep.sort(key=lambda e: (e["first"], e["index"]))
    data["tables"] = keep
    done = set(data["pages_done"])
    done.update(int(p) for p in pages)
    data["pages_done"] = sorted(done)
    path = vdir / TABLES_NAME
    atomic_write_json(path, data, indent=1, ensure_ascii=False)
    return path


def sort_on_page(tables: list[LogicalTable], page: int) -> list[LogicalTable]:
    """Tables in the order they appear on the page."""

    def key(t: LogicalTable):
        part = t.part_on(page)
        return (part[3] if part else 0.0, t.first, t.index)

    return sorted(tables, key=key)


def remove_store(vdir: Path) -> None:
    path = vdir / TABLES_NAME
    if path.exists():
        path.unlink()


# ---------------------------------------------------------- formatting


def _cell_lines(cell: str) -> list[str]:
    out = []
    for ln in cell.split("\n"):
        ln = ln.strip()
        if len(ln) <= CELL_WIDTH:
            out.append(ln)
        else:
            out.extend(textwrap.wrap(ln, CELL_WIDTH) or [""])
    return out or [""]


def format_table(table: LogicalTable, only: list[int] | None = None) -> list[str]:
    """The table as a text grid: columns padded and joined with `` | ``,
    one physical line per cell line, a rule after the header and after
    every row that has a multi-line cell. ``only`` keeps the header and
    the rows with those indices."""
    width = table.width
    rows = table.rows
    if only is not None:
        wanted = {i for i in only if 0 < i < len(rows)}
        rows = rows[:1] + [r for i, r in enumerate(rows) if i in wanted]
    grid = [[_cell_lines(c) for c in row] + [[""]] * (width - len(row)) for row in rows]
    widths = [0] * width
    for row in grid:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], max(len(ln) for ln in cell))
    rule = "-+-".join("-" * w for w in widths)
    out = []
    for r, row in enumerate(grid):
        height = max(len(cell) for cell in row)
        for k in range(height):
            cells = [
                (cell[k] if k < len(cell) else "").ljust(widths[i])
                for i, cell in enumerate(row)
            ]
            out.append(" | ".join(cells).rstrip())
        if r == 0 or height > 1:
            out.append(rule)
    return out


def describe(table: LogicalTable) -> str:
    """The ``table:`` line: caption, how it is drawn, page range, size."""
    pages = (
        f"page {table.first}"
        if table.first == table.last
        else f"pages {table.first}-{table.last}"
    )
    cols = table.width
    rows = len(table.rows)
    drawn = DRAWN_LABEL.get(table.drawn, table.drawn)
    return (
        f"table: {table.caption or '-'} | {drawn} | {pages} | {cols} column{_s(cols)}"
        f" | {rows} row{_s(rows)}"
    )


def _s(count: int) -> str:
    return "" if count == 1 else "s"


__all__ = [
    "CELLS",
    "DRAWN_LABEL",
    "RULED",
    "TABLES_NAME",
    "TABLES_VERSION",
    "LogicalTable",
    "PageTable",
    "Reader",
    "TableError",
    "TableStart",
    "TextLine",
    "box_grids",
    "columns_match",
    "describe",
    "drop_repeated_header",
    "format_table",
    "join_cells",
    "page_boxes",
    "page_lines",
    "page_rules",
    "page_tables",
    "remove_store",
    "sort_on_page",
    "store",
    "stored_for_page",
]

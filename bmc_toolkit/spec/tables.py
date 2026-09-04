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
lie inside a ruled table (its shaded header) are not a second table. A
cells table has no rule that could show its last row on a page to be
complete, so a continuation whose first row has an empty first cell is
taken as the rest of a row the page break cut, as for an open-bottomed
ruled table.
pdfplumber does the cell geometry and the text inside each cell; it is
imported inside the functions that open a PDF.

A table that is the last body content of its page continues on the next
page when that page's first body content is a table with the same column
edges. Running headers, footers and page numbers (lines repeated at the same
height on a neighbouring page) are not body content. A header row that a
continuation page repeats, with or without "(continued)", is dropped.

``tables.json`` in the version directory::

    {"tables_version": 2,
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
the x positions of the column edges on that page, ``rows[0]`` the header,
``row_pages[i]`` the page ``rows[i]`` starts on (so a very long table can
be printed one page at a time).
Coordinates are PDF points with the origin top-left, as pdfplumber reports
them. Version 1 stores (no ``drawn``, no cells tables) are read again.
"""

import json
import re
import textwrap
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

TABLES_VERSION = 2
TABLES_NAME = "tables.json"

RULED = "ruled"
CELLS = "cells"
DRAWN_LABEL = {RULED: "ruled", CELLS: "cells (no ruling lines)"}

RULE_PT = 2.5  # a rectangle or line thinner than this is a ruling line
SNAP_X_PT = 6.0  # vertical rules closer than this are one column edge
SNAP_Y_PT = 4.0  # horizontal rules closer than this are one row edge
COLUMN_TOL_PT = 6.0  # column edges of two parts match within this
CAPTION_GAP_PT = 40.0  # the caption lies at most this far above the table
LINE_TOL_PT = 2.0  # words this close vertically form one text line
FURNITURE_TOL_PT = 3.0  # a running header or footer repeats at this height
BODY_GAP_PT = 1.0  # text this close to a rule is inside the table, not around it
CELL_WIDTH = 60  # grid columns wrap beyond this many characters

_CAPTION = re.compile(r"^(?:\d{1,5}\s+)?(?P<text>(?:Table|Figure)\b.*)$", re.IGNORECASE)
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
    then tables drawn as tiled cell boxes outside them."""
    drawn, vertical = page_rules(page)
    found = _ruled_tables(page, number, drawn, vertical)
    boxes = page_boxes(page)
    boxes = [b for b in boxes if not any(_inside(b, t.bbox) for t in found)]
    found += _cell_tables(page, number, boxes)
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
        rows = [[_cell_text(c) for c in row] for row in table.extract()]
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


def page_lines(page) -> list[TextLine]:
    """The page's words grouped into text lines, top to bottom."""
    words = sorted(page.extract_words(), key=lambda w: (w["top"], w["x0"]))
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
        pages before or after."""
        info = self.page(number)
        tops: dict[str, list[float]] = {}
        for n in (number - 2, number - 1, number + 1, number + 2):
            if 1 <= n <= self.page_count:
                for other in self.page(n).lines:
                    tops.setdefault(_furniture_key(other.text), []).append(other.top)
        out = set()
        for i, line in enumerate(info.lines):
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

    def body_above(self, table: PageTable) -> bool:
        return any(
            ln.bottom < table.top + BODY_GAP_PT for ln in self.body_lines(table.page)
        )

    def caption(self, table: PageTable) -> str | None:
        """The nearest body line above the table that reads like a caption."""
        above = [
            ln
            for ln in self.body_lines(table.page)
            if ln.bottom < table.top + BODY_GAP_PT
            and ln.top >= table.top - CAPTION_GAP_PT
        ]
        if not above:
            return None
        nearest = max(above, key=lambda ln: ln.top)
        m = _CAPTION.match(nearest.text.strip())
        return m.group("text").strip() if m else None

    # ------------------------------------------------- continuation

    def continues(self, a: PageTable, b: PageTable) -> bool:
        """True when table ``b`` (first on its page) carries on table ``a``
        (last on the page before)."""
        if b.page != a.page + 1:
            return False
        if a.index != len(self.page(a.page).tables) - 1 or b.index != 0:
            return False
        if not columns_match(a.columns, b.columns):
            return False
        return not self.body_below(a) and not self.body_above(b)

    def logical_tables(
        self,
        number: int,
        section_of: Callable[[int, str | None], str | None] | None = None,
    ) -> list[LogicalTable]:
        """Every Logical Table that touches the page, top to bottom."""
        return self.read_page(number, section_of)[0]

    def read_page(
        self,
        number: int,
        section_of: Callable[[int, str | None], str | None] | None = None,
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
            prev = self.page(cur.page - 1).tables
            if not prev or not self.continues(prev[-1], cur):
                break
            cur = prev[-1]
            parts.insert(0, cur)
        cur = table
        while cur.page < self.page_count:
            nxt = self.page(cur.page + 1).tables
            if not nxt or not self.continues(cur, nxt[0]):
                break
            cur = nxt[0]
            parts.append(cur)
        return self._assemble(parts, section_of)

    def _assemble(self, parts: list[PageTable], section_of) -> LogicalTable:
        first = parts[0]
        rows: list[list[str]] = [list(r) for r in first.rows]
        row_pages = [first.page] * len(rows)
        previous = first
        for part in parts[1:]:
            more = drop_repeated_header(rows, part.rows)
            more = drop_repeated_header(rows, more)  # a "(continued)" sub-header too
            cut = previous.open_bottom or previous.drawn == CELLS
            if more and rows and cut and _is_cut_row(more[0]):
                rows[-1] = join_cells(rows[-1], more[0])
                more = more[1:]
            rows.extend(more)
            row_pages.extend([part.page] * len(more))
            previous = part
        caption = self.caption(first)
        section = section_of(first.page, caption) if section_of else None
        return LogicalTable(
            first=first.page,
            last=parts[-1].page,
            index=first.index + 1,
            caption=caption,
            section=section,
            columns=first.columns,
            parts=[[p.page, p.index, *[round(v, 1) for v in p.bbox]] for p in parts],
            rows=rows,
            drawn=first.drawn,
            row_pages=row_pages,
        )


def _holds(table: LogicalTable, part: PageTable) -> bool:
    return any(int(p[0]) == part.page and int(p[1]) == part.index for p in table.parts)


def _furniture_key(text: str) -> str:
    return " ".join(sorted(_DIGITS.sub("", text).lower().split()))


def columns_match(a: list[float], b: list[float]) -> bool:
    if len(a) != len(b):
        return False
    return all(abs(x - y) <= COLUMN_TOL_PT for x, y in zip(a, b, strict=True))


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
    replaced."""
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
    with open(path, "w", encoding="utf-8", newline="") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
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

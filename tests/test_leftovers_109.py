"""PR #109 leftovers: the listing module exports only what exists and has no
uncalled DMTF title parser (F5); the ``_document_span`` docstring is one
evenly wrapped paragraph (F6)."""

import inspect

from bmc_toolkit.spec import listing as L
from bmc_toolkit.spec import refresh as R


def test_listing_has_no_parse_dmtf_titles():
    assert not hasattr(L, "parse_dmtf_titles")
    assert "parse_dmtf_titles" not in L.__all__


def test_listing_all_names_exist():
    missing = [name for name in L.__all__ if not hasattr(L, name)]
    assert missing == []


def test_document_span_docstring_has_no_short_line():
    # A line is short when the next line's first word would still have fit
    # within the widest line of the paragraph.
    lines = inspect.getdoc(R._document_span).splitlines()
    width = max(len(line) for line in lines)
    short = [
        line
        for line, nxt in zip(lines, lines[1:], strict=False)
        if len(line) + 1 + len(nxt.split()[0]) <= width
    ]
    assert short == []

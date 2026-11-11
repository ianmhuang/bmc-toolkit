"""PR #109 F5 leftover: the listing module exports only what exists and has
no uncalled DMTF title parser."""

from bmc_toolkit.spec import listing as L


def test_listing_has_no_parse_dmtf_titles():
    assert not hasattr(L, "parse_dmtf_titles")
    assert "parse_dmtf_titles" not in L.__all__


def test_listing_all_names_exist():
    missing = [name for name in L.__all__ if not hasattr(L, name)]
    assert missing == []

"""Reviewer acceptance tests for T81.4 AC-1 and AC-2: the bmc-spec
frontmatter names OData and the RFCs, inside the listing cap, and
`when_to_use` keeps its three situations and its "Not for" clause.

The checks are on shape (which names appear, in which part, how long the
two fields are), not on sentences: whether a wording triggers the skill is
measured in fresh Sessions, which no test here can do. Every test needs a
name the base branch lacks: there neither field mentions OData or an RFC.
"""

import re
from pathlib import Path

from bmc_toolkit.spec.catalog import load_catalog

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"

# description and when_to_use share this many characters in the skill listing
LISTING_CAP = 1536


def _fields() -> dict[str, str]:
    """The frontmatter, one `key: value` per line, double quotes taken off."""
    text = SKILL.read_text("utf-8")
    assert text.startswith("---\n")
    head, closed, _ = text[4:].partition("\n---\n")
    assert closed, "frontmatter is not closed"
    fields: dict[str, str] = {}
    for line in head.splitlines():
        key, sep, value = line.partition(": ")
        assert sep and key not in fields, line[:40]
        if value[:1] == '"':
            assert len(value) > 1 and value.endswith('"'), key
            value = value[1:-1]
            assert '"' not in value and "\\" not in value, f"{key}: needs an escape"
        fields[key] = value
    return fields


def _situations(when_to_use: str) -> tuple[str, str, str, str]:
    """The text of (1), (2) and (3), and what follows from "Not for" on."""
    marks = [m.start() for m in re.finditer(r"\(\d\)", when_to_use)]
    assert re.findall(r"\((\d)\)", when_to_use) == ["1", "2", "3"], when_to_use
    not_for = re.search(r"\bNot for\b", when_to_use)
    assert not_for and not_for.start() > marks[2], "no `Not for` after (3)"
    return (
        when_to_use[marks[0] : marks[1]],
        when_to_use[marks[1] : marks[2]],
        when_to_use[marks[2] : not_for.start()],
        when_to_use[not_for.start() :],
    )


# ------------------------------------------------------------------ AC-1


def test_ac1_description_names_odata_and_the_rfcs_and_the_catalog_holds_them():
    description = _fields()["description"]
    assert re.search(r"\bOData\b", description), "OData is not named"
    assert re.search(r"\bRFCs?\b", description), "the RFCs are not named"
    # the description may name them because the shipped catalog holds them
    catalog = load_catalog()
    assert catalog.by_family("odata"), "no OData document in the catalog"
    assert any(
        catalog.families[doc.family].publisher == "IETF" for doc in catalog.documents
    ), "no IETF document in the catalog"


def test_ac1_both_fields_with_the_new_names_fit_the_listing_cap():
    fields = _fields()
    description, when_to_use = fields["description"], fields["when_to_use"]
    # the names this change adds are there, so the count is of the new wording
    assert "OData" in description and "RFC" in description
    assert "RFC" in when_to_use
    total = len(description) + len(when_to_use)
    assert total <= LISTING_CAP, total
    # each field is still a finished sentence, not one cut to fit
    assert description.rstrip().endswith("."), description[-40:]
    assert when_to_use.rstrip().endswith("."), when_to_use[-40:]
    assert list(fields) == ["name", "description", "when_to_use", "allowed-tools"]


# ------------------------------------------------------------------ AC-2


def test_ac2_an_rfc_question_is_situation_one_and_the_other_two_are_kept():
    first, second, third, _ = _situations(_fields()["when_to_use"])
    # (1): what a document defines, now an RFC too
    assert re.search(r"\bRFC\b", first), first
    assert "specification" in first and "Command" in first, first
    assert "in any language" in first, first
    # an RFC is a kind of question (1) asks, not a situation of its own
    assert not re.search(r"\bRFC", second + third), second + third
    # (2): pasted tool output
    assert "pastes" in second, second
    for tool in ("`ipmitool`", "`pldmtool`", "`mctp-client`"):
        assert tool in second, tool
    # (3): how the source implements something
    for source in ("OpenBMC", "Aspeed", "Nuvoton"):
        assert source in third, source


def test_ac2_the_not_for_clause_is_kept_and_keeps_application_development_out():
    first, _, _, tail = _situations(_fields()["when_to_use"])
    # the change that brings RFC questions in ...
    assert re.search(r"\bRFC\b", first), first
    # ... keeps the three things the clause already excluded
    assert "general programming" in tail, tail
    assert "system administration" in tail, tail
    assert "protocols the catalog does not hold" in tail, tail
    # and says that building on HTTP is among them (a web server, a framework)
    assert re.search(r"web|HTTP|framework|application", tail), tail

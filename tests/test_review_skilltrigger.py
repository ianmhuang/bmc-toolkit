"""Acceptance tests for the bmc-spec frontmatter a Session reads before it
decides whether to invoke the skill (AC-1, AC-4, AC-5).

The frontmatter is read the way a YAML loader gets it: one key per line, the
value one scalar. Every test needs the `when_to_use` field, so each one fails
on develop, where the frontmatter has no such field. The tests check shape
(fields, the listing cap, the order of the lead, the tool and source names),
not the sentences of the description.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"

# description and when_to_use share this many characters in the skill listing
LISTING_CAP = 1536

# Names a list of families would start with (the ones the description named
# before this change).
FAMILIES = (
    "IPMI",
    "DCMI",
    "MCTP",
    "PLDM",
    "SPDM",
    "NC-SI",
    "SMBIOS",
    "Redfish",
    "NVMe",
    "DC-SCM",
    "DC-MHS",
    "I2C",
    "SMBus",
    "CMIS",
)


def _scalar(key: str, value: str) -> str:
    """One frontmatter value as YAML reads it. A plain scalar holds neither
    `: ` nor ` #`; a quoted one is closed and holds no quote of its own kind."""
    assert value, f"{key}: empty value"
    if value[0] == '"':
        assert len(value) > 1 and value.endswith('"'), f"{key}: quote not closed"
        inner = value[1:-1]
        assert '"' not in inner and "\\" not in inner, f"{key}: needs an escape"
        return inner
    if value[0] == "'":
        assert len(value) > 1 and value.endswith("'"), f"{key}: quote not closed"
        inner = value[1:-1]
        assert "'" not in inner.replace("''", ""), f"{key}: lone single quote"
        return inner.replace("''", "'")
    assert value[0] not in "[]{}*&!|>%@`#,", f"{key}: bad first character"
    assert ": " not in value and " #" not in value, f"{key}: must be quoted"
    assert not value.endswith(":"), f"{key}: plain scalar ends with a colon"
    return value


def _frontmatter() -> dict[str, str]:
    text = SKILL.read_text("utf-8")
    assert text.startswith("---\n")
    head, closed, _ = text[4:].partition("\n---\n")
    assert closed, "frontmatter is not closed"
    fields: dict[str, str] = {}
    for line in head.splitlines():
        key, sep, value = line.partition(":")
        assert sep and key and key == key.strip(), f"not `key: value`: {line[:40]}"
        assert key not in fields, f"{key} appears twice"
        fields[key] = _scalar(key, value.strip())
    return fields


def _listing_fields() -> tuple[str, str]:
    fields = _frontmatter()
    assert "description" in fields, sorted(fields)
    assert "when_to_use" in fields, sorted(fields)
    return fields["description"], fields["when_to_use"]


def _first_family(text: str) -> int:
    found = [
        m.start()
        for name in FAMILIES
        if (m := re.search(rf"(?<![\w-]){re.escape(name)}(?![\w])", text))
    ]
    assert found, "no family is named at all"
    return min(found)


# ------------------------------------------------------------------ AC-1


def test_when_to_use_is_a_field_of_its_own_next_to_description():
    description, when_to_use = _listing_fields()
    assert description.strip() and when_to_use.strip()
    # the skill is still the same skill
    assert _frontmatter()["name"] == "bmc-spec"


def test_description_and_when_to_use_fit_the_listing_cap():
    description, when_to_use = _listing_fields()
    total = len(description) + len(when_to_use)
    assert total <= LISTING_CAP, total


def test_description_says_what_then_when_before_the_first_family():
    """The lead is everything before the first family name. It holds one
    finished sentence (what the skill does), then a sentence that says when
    to use it, finished before the list of families starts."""
    description, _ = _listing_fields()
    lead = description[: _first_family(description)]
    use = re.search(r"\bUse\b", lead)
    assert use, f"no `Use ...` sentence before the first family: {lead[:80]!r}"
    what = lead[: use.start()].strip()
    assert what and what.endswith("."), f"no sentence before `Use`: {what[-40:]!r}"
    assert ". " in lead[use.start() :], "the list of families starts inside the when"


# ------------------------------------------------------------------ AC-4


def test_when_to_use_names_the_three_tools_whose_output_is_pasted():
    _, when_to_use = _listing_fields()
    for tool in ("ipmitool", "pldmtool", "mctp-client"):
        assert tool in when_to_use, tool


def test_when_to_use_names_the_three_sources_and_a_limit():
    _, when_to_use = _listing_fields()
    for source in ("OpenBMC", "Aspeed", "Nuvoton"):
        assert source in when_to_use, source
    # it also says what the skill is not for
    assert re.search(r"\bnot\b", when_to_use, re.IGNORECASE)


# ------------------------------------------------------------------ AC-5


def test_description_keeps_the_tool_forms_and_every_value_is_one_scalar():
    # _frontmatter() reads every value as a YAML scalar, when_to_use included
    description, when_to_use = _listing_fields()
    for tool in ("ipmitool raw", "mctp-client", "pldmtool raw"):
        assert tool in description, tool
    # neither value was cut off at a `: ` inside it
    assert description.rstrip().endswith("."), description[-40:]
    assert when_to_use.rstrip().endswith("."), when_to_use[-40:]

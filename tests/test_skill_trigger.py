"""The frontmatter of the bmc-spec skill: what a Session reads before it
decides whether to invoke the skill. `description` and `when_to_use` are the
whole of it, and the skill listing cuts the two off at 1,536 characters."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"

LISTING_LIMIT = 1536


def frontmatter() -> dict[str, str]:
    """Key to value, each value on its key's line, quotes taken off."""
    text = SKILL.read_text("utf-8")
    assert text.startswith("---\n")
    fields = {}
    for line in text[4:].split("\n---\n", 1)[0].splitlines():
        key, sep, value = line.partition(": ")
        assert sep and key not in fields, line[:40]
        if value[:1] == '"':
            assert len(value) > 1 and value.endswith('"'), key
            value = value[1:-1]
        fields[key] = value
    return fields


def flat(value: str) -> str:
    return " ".join(value.lower().split())


def test_frontmatter_holds_the_four_fields_and_no_other():
    assert list(frontmatter()) == [
        "name",
        "description",
        "when_to_use",
        "allowed-tools",
    ]


def test_description_and_when_to_use_fit_the_skill_listing():
    fields = frontmatter()
    total = len(fields["description"]) + len(fields["when_to_use"])
    assert total <= LISTING_LIMIT, total


def test_description_leads_with_what_and_when_before_any_family():
    description = frontmatter()["description"]
    first_family = min(
        description.index(name)
        for name in ("IPMI", "DCMI", "MCTP", "PLDM", "SPDM", "Redfish", "NVMe")
    )
    what = description.index("Looks up")
    when = description.index("Use it")
    assert what == 0, description[:40]
    assert what < when < first_family


def test_description_says_to_look_up_before_answering():
    text = flat(frontmatter()["description"])
    assert "before answering" in text
    assert "even when the answer seems known" in text
    # the baseline's habit: answer from memory, then offer the skill
    assert "never answer from memory and offer the lookup afterwards" in text


def test_description_does_not_read_as_the_whole_catalog():
    text = flat(frontmatter()["description"])
    assert "source catalog" in text
    assert "many more that are not named here" in text
    assert "check the catalog before deciding a document is not covered" in text


def test_when_to_use_names_the_three_situations():
    text = flat(frontmatter()["when_to_use"])
    # a question about what a specification or a Command defines
    assert "in any language" in text
    assert "specification" in text and "command" in text
    # pasted tool output
    for tool in ("`ipmitool`", "`pldmtool`", "`mctp-client`"):
        assert tool in text, tool
    assert "pastes" in text
    # source questions
    for source in ("openbmc", "aspeed", "nuvoton"):
        assert source in text, source


def test_when_to_use_says_what_the_skill_is_not_for():
    text = flat(frontmatter()["when_to_use"])
    tail = text[text.index("not for") :]
    assert "general programming" in tail
    assert "protocols the catalog does not hold" in tail

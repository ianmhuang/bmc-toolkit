"""Reviewer acceptance test for AC-7: the Command workflow block of SKILL.md
sends the Session to ``invocation --subcommand`` for a PLDM Command and
grows by at most two lines over develop's 44.

On develop the block names no ``--subcommand``, so the test fails there.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"
START = "<!-- command-workflow:start -->"
END = "<!-- command-workflow:end -->"
MAX_LINES = 52  # develop's 44 plus the two lines AC-7 allows; 46 until T52


def _body() -> list[str]:
    lines = SKILL.read_text("utf-8").splitlines()
    assert lines.count(START) == 1 and lines.count(END) == 1
    first, last = lines.index(START), lines.index(END)
    assert first < last
    return lines[first + 1 : last]


def test_the_pldm_bullet_sends_the_session_to_the_option_within_the_cap():
    body = _body()
    assert len(body) <= MAX_LINES, len(body)
    text = " ".join(" ".join(body).split())
    bullet = text[text.index("- MCTP control, PLDM, SPDM:") :]
    bullet = bullet[: bullet.index("3. Headers")]
    # the option is added to the helper call; what it prints is copied, the
    # placeholders filled, with the cite; `none` leaves the raw lines alone
    assert "--subcommand <Name>" in bullet
    assert "`subcommand:`" in bullet and "`note:`" in bullet
    assert "cite" in bullet
    assert "`none`" in bullet
    # the pldmtool raw form stays, before the subcommand rule
    raw = "`pldmtool raw -m <eid> -d 0x<byte> ...`"
    assert raw in bullet and bullet.index(raw) < bullet.index("--subcommand <Name>")

"""Review tests: a --ref or --release clone that lands on a commit the
Library holds under another name records that name on the held tree, and
reading commands find the tree by it (black-box through the CLI against
local bare repositories; skipped when git is not on PATH)."""

import json
import shutil

import pytest

from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG
from tests.test_code import (
    RECIPE,
    RECIPE_URL,
    THING_FILES,
    commit,
    git,
    make_repo,
    make_scenario,
    push,
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")

PIN_FILE = "meta-phosphor/recipes-phosphor/things/thing_git.bb"


@pytest.fixture
def lib(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(root))
    return root


def _build_thing(root):
    (root / "remote").mkdir(exist_ok=True)
    work, _bare, url = make_repo(root / "remote", "thing", THING_FILES, branch="master")
    c1 = git("rev-parse", "HEAD", cwd=work)
    c2 = commit(work, {"README.md": "thing two\n"}, "two")
    push(work, "master")
    return {"work": work, "url": url, "c1": c1, "c2": c2}


@pytest.fixture
def thing(tmp_path):
    """thing on master: c1, then c2 (the branch head)."""
    return make_scenario(tmp_path, "review-alsonames-thing", _build_thing)


@pytest.fixture
def obmc(tmp_path, thing):
    """openbmc on master; its recipe pins thing at c1."""
    files = {
        PIN_FILE: RECIPE.format(url=RECIPE_URL, sha=thing["c1"]),
        "README.md": "distro\n",
    }
    work, _bare, url = make_repo(tmp_path / "remote", "openbmc", files, branch="master")
    return {"work": work, "url": url}


@pytest.fixture
def cat(tmp_path, thing, obmc):
    text = MINI_CATALOG + (
        f'\n[[repos]]\nid = "thing"\nurl = "{thing["url"]}"\ntopics = ["power"]\n'
        f'\n[[repos]]\nid = "openbmc"\nurl = "{obmc["url"]}"\n'
        'topics = ["release"]\nsparse = ["meta-phosphor"]\n'
    )
    path = tmp_path / "catalog.toml"
    path.write_text(text, encoding="utf-8", newline="")
    return path


def cli(capsys, cat, *argv):
    rc = main(["--catalog", str(cat), *argv])
    return rc, capsys.readouterr().out


def cli_offline(capsys, monkeypatch, cat, *argv):
    def refuse(*args, **kwargs):
        raise AssertionError(f"git ran: {args}")

    with monkeypatch.context() as m:
        m.setattr(code_mod, "run_git", refuse)
        return cli(capsys, cat, *argv)


def pin(obmc, sha):
    commit(obmc["work"], {PIN_FILE: RECIPE.format(url=RECIPE_URL, sha=sha)}, "pin")
    push(obmc["work"], "master")


def on_dev(thing, text):
    work = thing["work"]
    if git("branch", "--list", "dev", cwd=work):
        git("checkout", "-q", "dev", cwd=work)
    else:
        git("checkout", "-q", "-b", "dev", cwd=work)
    sha = commit(work, {"README.md": text}, "dev work")
    push(work, "dev")
    return sha


def tag(thing, name, sha):
    git("tag", name, sha, cwd=thing["work"])
    git("push", "-q", "origin", name, cwd=thing["work"])


def meta(lib, sha):
    path = lib / "code" / "thing" / sha / code_mod.TREE_META
    return json.loads(path.read_text("utf-8"))


def cite_of(out):
    """(repository and commit, provenance) of the cite: line."""
    line = next(ln for ln in out.splitlines() if ln.startswith("cite: "))
    fields = line.split(" | ")
    return fields[1], fields[2]


def superseded(out):
    return [ln for ln in out.splitlines() if ln.startswith("superseded ")]


def also_names(lib, sha):
    return [(a["kind"], a["name"]) for a in meta(lib, sha).get("also", [])]


# AC-1 ---------------------------------------------------------------------


def test_release_on_a_ref_tree_is_read_by_code_and_grep(
    lib, thing, obmc, cat, capsys, monkeypatch
):
    c3 = on_dev(thing, "dev readme\n")
    pin(obmc, c3)
    rc, out = cli(capsys, cat, "clone", "thing", "--ref", "dev")
    assert rc == 0 and f"cloned thing {c3[:7]} (dev " in out

    rc, out = cli(capsys, cat, "clone", "thing", "--release", "master")
    assert rc == 0, out
    assert f"held thing {c3[:7]} (dev " in out
    assert f"pin: {c3[:7]} from {PIN_FILE}" in out
    obmc_head = git("rev-parse", "HEAD", cwd=obmc["work"])
    recorded = meta(lib, c3)
    assert recorded["provenance"] == {"kind": "ref", "name": "dev"}
    assert recorded["also"] == [
        {"kind": "release", "name": "master", "openbmc_commit": obmc_head}
    ]

    rc, out = cli(capsys, cat, "code", "thing", "README.md", "--release", "master")
    assert rc == 0, out
    assert cite_of(out) == (f"thing {c3[:7]}", "release master")
    assert "dev readme" in out

    rc, out = cli(capsys, cat, "grep", "thing", "dev readme", "--release", "master")
    assert rc == 0, out
    assert f"thing@{c3[:7]}" in out

    rc, out = cli_offline(
        capsys, monkeypatch, cat, "clone", "thing", "--release", "master"
    )
    assert rc == 0 and f"held thing {c3[:7]} (dev " in out
    assert also_names(lib, c3) == [("release", "master")]


# AC-2 ---------------------------------------------------------------------


def test_release_on_the_default_tree_leaves_it_the_default(
    lib, thing, obmc, cat, capsys, monkeypatch
):
    c2 = thing["c2"]
    pin(obmc, c2)
    rc, out = cli(capsys, cat, "clone", "thing")
    assert rc == 0 and f"cloned thing {c2[:7]} (master " in out

    rc, out = cli(capsys, cat, "clone", "thing", "--release", "master")
    assert rc == 0 and f"held thing {c2[:7]} (master " in out
    assert meta(lib, c2)["provenance"] == {"kind": "default", "name": "master"}
    assert also_names(lib, c2) == [("release", "master")]

    rc, out = cli_offline(capsys, monkeypatch, cat, "clone", "thing")
    assert rc == 0, out
    assert len(out.splitlines()) == 1, out
    assert out.startswith(f"held thing {c2[:7]} (master ")

    rc, out = cli(capsys, cat, "code", "thing", "README.md")
    assert rc == 0, out
    day = meta(lib, c2)["fetched_at"][:10]
    assert cite_of(out) == (f"thing {c2[:7]}", f"master {day}")
    rc, out = cli(capsys, cat, "code", "thing", "README.md", "--release", "master")
    assert rc == 0 and cite_of(out) == (f"thing {c2[:7]}", "release master")


# AC-3 ---------------------------------------------------------------------


def test_forced_repin_onto_a_ref_tree_supersedes_the_old_release_tree(
    lib, thing, obmc, cat, capsys
):
    c1 = thing["c1"]
    rc, out = cli(capsys, cat, "clone", "thing", "--release", "master")
    assert rc == 0 and f"cloned thing {c1[:7]} (release master)" in out
    c3 = on_dev(thing, "dev readme\n")
    rc, out = cli(capsys, cat, "clone", "thing", "--ref", "dev")
    assert rc == 0, out

    pin(obmc, c3)
    rc, out = cli(capsys, cat, "clone", "thing", "--release", "master", "--force")
    assert rc == 0, out
    assert superseded(out) == [f"superseded thing {c1[:7]} (release master)"]
    assert meta(lib, c1)["superseded_by"] == c3
    assert also_names(lib, c3) == [("release", "master")]
    assert "superseded_by" not in meta(lib, c3)

    rc, out = cli(capsys, cat, "code", "thing", "README.md", "--release", "master")
    assert rc == 0 and cite_of(out) == (f"thing {c3[:7]}", "release master")


# AC-4 ---------------------------------------------------------------------


def test_tag_on_a_release_tree_is_recorded_and_cited_with_its_date(
    lib, thing, obmc, cat, capsys, monkeypatch
):
    c1 = thing["c1"]
    tag(thing, "v1", c1)
    rc, out = cli(capsys, cat, "clone", "thing", "--release", "master")
    assert rc == 0, out

    rc, out = cli(capsys, cat, "clone", "thing", "--ref", "v1")
    assert rc == 0 and out.startswith(f"held thing {c1[:7]} (release master)")
    assert meta(lib, c1)["also"] == [{"kind": "ref", "name": "v1"}]

    rc, out = cli(capsys, cat, "code", "thing", "README.md", "--ref", "v1")
    assert rc == 0, out
    day = meta(lib, c1)["fetched_at"][:10]
    assert cite_of(out) == (f"thing {c1[:7]}", f"v1 {day}")

    rc, out = cli_offline(capsys, monkeypatch, cat, "clone", "thing", "--ref", "v1")
    assert rc == 0 and out.startswith(f"held thing {c1[:7]} (release master)")


def test_tag_on_the_default_tree_is_recorded_and_found(
    lib, thing, cat, capsys, monkeypatch
):
    c2 = thing["c2"]
    tag(thing, "v2", c2)
    rc, out = cli(capsys, cat, "clone", "thing")
    assert rc == 0, out

    rc, out = cli(capsys, cat, "clone", "thing", "--ref", "v2")
    assert rc == 0 and out.startswith(f"held thing {c2[:7]} (master ")
    assert meta(lib, c2)["also"] == [{"kind": "ref", "name": "v2"}]

    rc, out = cli(capsys, cat, "grep", "thing", "thing two", "--ref", "v2")
    assert rc == 0 and f"thing@{c2[:7]}" in out
    rc, out = cli(capsys, cat, "code", "thing", "README.md", "--ref", "v2")
    assert rc == 0, out
    day = meta(lib, c2)["fetched_at"][:10]
    assert cite_of(out) == (f"thing {c2[:7]}", f"v2 {day}")

    rc, out = cli_offline(capsys, monkeypatch, cat, "clone", "thing", "--ref", "v2")
    assert rc == 0 and out.startswith(f"held thing {c2[:7]} (master ")


# AC-5 ---------------------------------------------------------------------


def _dev_also_release(lib, thing, obmc, cat, capsys):
    c3 = on_dev(thing, "dev readme\n")
    pin(obmc, c3)
    assert cli(capsys, cat, "clone", "thing", "--ref", "dev")[0] == 0
    assert cli(capsys, cat, "clone", "thing", "--release", "master")[0] == 0
    assert also_names(lib, c3) == [("release", "master")]
    return c3


def test_moving_the_own_name_hands_over_the_also_name(lib, thing, obmc, cat, capsys):
    c3 = _dev_also_release(lib, thing, obmc, cat, capsys)
    c4 = on_dev(thing, "dev readme 2\n")
    rc, out = cli(capsys, cat, "clone", "thing", "--ref", "dev", "--force")
    assert rc == 0 and f"cloned thing {c4[:7]} (dev " in out
    assert superseded(out) == []
    after = meta(lib, c3)
    assert after["provenance"]["kind"] == "release"
    assert after["provenance"]["name"] == "master"
    assert "also" not in after and "superseded_by" not in after

    rc, out = cli(capsys, cat, "code", "thing", "README.md", "--release", "master")
    assert rc == 0 and cite_of(out) == (f"thing {c3[:7]}", "release master")
    rc, out = cli(capsys, cat, "code", "thing", "README.md", "--ref", "dev")
    assert rc == 0 and cite_of(out)[0] == f"thing {c4[:7]}"


def test_moving_the_also_name_removes_only_that_entry(lib, thing, obmc, cat, capsys):
    c3 = _dev_also_release(lib, thing, obmc, cat, capsys)
    c1 = thing["c1"]
    pin(obmc, c1)
    rc, out = cli(capsys, cat, "clone", "thing", "--release", "master", "--force")
    assert rc == 0 and f"cloned thing {c1[:7]} (release master)" in out
    assert superseded(out) == []
    after = meta(lib, c3)
    assert after["provenance"] == {"kind": "ref", "name": "dev"}
    assert "also" not in after and "superseded_by" not in after

    rc, out = cli(capsys, cat, "code", "thing", "README.md", "--ref", "dev")
    assert rc == 0 and cite_of(out)[0] == f"thing {c3[:7]}"
    rc, out = cli(capsys, cat, "code", "thing", "README.md", "--release", "master")
    assert rc == 0 and cite_of(out) == (f"thing {c1[:7]}", "release master")


def test_a_tree_is_superseded_once_its_last_name_moves(lib, thing, obmc, cat, capsys):
    c3 = _dev_also_release(lib, thing, obmc, cat, capsys)
    c4 = on_dev(thing, "dev readme 2\n")
    assert cli(capsys, cat, "clone", "thing", "--ref", "dev", "--force")[0] == 0
    assert "superseded_by" not in meta(lib, c3)  # release master still on it

    c1 = thing["c1"]
    pin(obmc, c1)
    rc, out = cli(capsys, cat, "clone", "thing", "--release", "master", "--force")
    assert rc == 0, out
    assert superseded(out) == [f"superseded thing {c3[:7]} (release master)"]
    assert meta(lib, c3)["superseded_by"] == c1
    assert "superseded_by" not in meta(lib, c4)


# AC-6 ---------------------------------------------------------------------


def test_repos_lists_several_also_names_comma_separated(lib, thing, obmc, cat, capsys):
    c1 = thing["c1"]
    tag(thing, "v1", c1)
    tag(thing, "v1b", c1)
    assert cli(capsys, cat, "clone", "thing", "--release", "master")[0] == 0
    assert cli(capsys, cat, "clone", "thing", "--ref", "v1")[0] == 0
    assert cli(capsys, cat, "clone", "thing", "--ref", "v1b")[0] == 0

    rc, out = cli(capsys, cat, "repos")
    assert rc == 0, out
    line = next(ln for ln in out.splitlines() if ln.startswith("thing\t"))
    assert line.split("\t")[1] == f"{c1[:7]} release master (also v1, v1b)"

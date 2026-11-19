"""Independent acceptance tests for what ``clone REPO --release L`` says when
the fetch of a ``release_tag`` tag fails (AC-1, AC-2).

Everything goes through the ``bmcspec`` CLI against local bare git
repositories: a component ``gizmo`` whose only tag is ``v1.0`` and an openbmc
remote whose release 1.0.0 builds gizmo 1.0 and whose release 2.0.0 builds
gizmo 7.7 (a version the remote has no tag for). The remote is made
unreachable by moving its directory away, or by leaving an empty directory
in its place; a tag the remote lists and cannot serve is a tag on a commit
whose tree the repository does not have. No network.
"""

import json
import shutil
import subprocess

import pytest

from bmc_toolkit.spec import catalog as catalog_mod
from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG
from tests.test_code import commit, git, make_repo, make_scenario, push

SHIPPED = catalog_mod.load_catalog()

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")

# kept short (Windows path length)
LAYER = "upstream-layers/oe/recipes"


def _tarball(name):
    """A recipe that fetches a release tarball: no git URL, no SRCREV."""
    return (
        f'SUMMARY = "{name}"\n'
        f'SRC_URI = "https://downloads.example.org/{name}/${{BP}}.tar.gz"\n'
        'SRC_URI[sha256sum] = "00"\n'
    )


def _build(root):
    work, bare, url = make_repo(root, "gizmo", {"src/gizmo.c": "int gizmo_v10;\n"})
    c10 = git("rev-parse", "HEAD", cwd=work)
    git("tag", "-a", "v1.0", "-m", "1.0", cwd=work)
    commit(work, {"src/gizmo.c": "int gizmo_next;\n"}, "next")
    push(work, "main")
    push(work, "refs/tags/v1.0")

    files = {
        f"{LAYER}/gizmo/gizmo_1.0.bb": _tarball("gizmo"),
        "README.md": "distro\n",
    }
    ob, _ob_bare, ob_url = make_repo(root, "openbmc", files, branch="master")
    git("tag", "1.0.0", cwd=ob)
    push(ob, "1.0.0")
    # 2.0.0 builds a version the gizmo remote has no tag for
    (ob / f"{LAYER}/gizmo/gizmo_1.0.bb").unlink()
    commit(ob, {f"{LAYER}/gizmo/gizmo_7.7.bb": _tarball("gizmo")}, "7.7")
    git("tag", "2.0.0", cwd=ob)
    push(ob, "2.0.0")
    return {"gizmo": url, "gizmo_bare": bare, "ob": ob_url, "c10": c10}


@pytest.fixture
def remotes(tmp_path):
    return make_scenario(tmp_path, "review-tagfetcherror", _build)


@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(root))
    return root


def _entry(repo_id, url, **keys):
    lines = ["[[repos]]", f'id = "{repo_id}"', f'url = "{url}"']
    keys.setdefault("topics", ["x"])
    lines += [f"{key} = {json.dumps(value)}" for key, value in keys.items()]
    return "\n".join(lines) + "\n"


def _catalog(tmp_path, remotes):
    parts = [
        MINI_CATALOG,
        _entry(
            "openbmc", remotes["ob"], sparse=list(SHIPPED.get_repo("openbmc").sparse)
        ),
        _entry("gizmo", remotes["gizmo"], release_tag="v{version}"),
    ]
    path = tmp_path / "catalog.toml"
    path.write_text("\n".join(parts), encoding="utf-8", newline="")
    assert catalog_mod.load_catalog(path).get_repo("gizmo").release_tag == "v{version}"
    return path


def _clone(capsys, cat, release, *flags):
    code = main(["--catalog", str(cat), "clone", "gizmo", "--release", release, *flags])
    return code, capsys.readouterr().out


def _trees(library):
    """commit -> the .bmc-tree.json of every Code Tree held of gizmo."""
    rdir = library / "code" / "gizmo"
    out = {}
    if not rdir.is_dir():
        return out
    for tdir in rdir.iterdir():
        meta = tdir / code_mod.TREE_META
        if meta.is_file():
            out[tdir.name] = json.loads(meta.read_text(encoding="utf-8"))
    return out


def _nothing_held(library):
    """No Code Tree of gizmo in the Library: no tree record and no commit
    directory (a dot-named temporary directory is not a tree)."""
    rdir = library / "code" / "gizmo"
    if not rdir.is_dir():
        return True
    left = [p.name for p in rdir.iterdir() if p.is_dir() and p.name[:1] != "."]
    return not left and not _trees(library)


def _message(out):
    """The last line printed: the failure message."""
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert lines, "nothing was printed"
    return lines[-1]


def _take_away(remotes, tmp_path, how):
    """Nothing answers at the gizmo URL any more: its directory is gone
    (``missing``) or is an empty directory (``not a repository``)."""
    bare = remotes["gizmo_bare"]
    bare.rename(tmp_path / "gizmo-away.git")
    if how == "not a repository":
        bare.mkdir()


def _bring_back(remotes, tmp_path):
    bare = remotes["gizmo_bare"]
    if bare.is_dir():
        bare.rmdir()
    (tmp_path / "gizmo-away.git").rename(bare)


def _is_the_fetch_error(out, tag):
    """The failure message is the one the fetch of the tag raised: it names
    the fetch and the ref that was being fetched, and neither of the other
    two messages is anywhere in the output."""
    message = _message(out)
    assert "ls-remote" not in out, out
    assert "has no tag" not in out, out
    assert "fetch" in message, out
    assert f"refs/tags/{tag}" in message, out
    assert "pin:" not in out, out


# --------------------------------------------------------------- AC-1


@pytest.mark.parametrize(
    "how", ["missing", "not a repository"], ids=["missing", "not-a-repository"]
)
def test_ac1_unreachable_remote_gives_the_error_of_the_fetch(
    tmp_path, remotes, library, capsys, how
):
    """AC-1: 1.0.0 builds gizmo 1.0, so the tag v1.0 is fetched. Nothing
    answers at the URL: the fetch fails and ``git ls-remote`` fails too.
    Exit 2, the fetch's error (not the ls-remote one, not ``has no tag``),
    no tree, no ``pin:`` line. Once the remote answers again the same
    command succeeds: the failure left nothing in the way."""
    cat = _catalog(tmp_path, remotes)
    _take_away(remotes, tmp_path, how)
    code, out = _clone(capsys, cat, "1.0.0")
    assert code == 2, out
    _is_the_fetch_error(out, "v1.0")
    assert _nothing_held(library)

    _bring_back(remotes, tmp_path)
    code, out = _clone(capsys, cat, "1.0.0")
    assert code == 0, out
    c10 = remotes["c10"]
    assert set(_trees(library)) == {c10}, out
    pins = [ln for ln in out.splitlines() if ln.startswith("pin:")]
    assert len(pins) == 1 and c10[:7] in pins[0] and "v1.0" in pins[0], out


def test_ac1_forced_refetch_of_a_held_tag_with_the_remote_gone(
    tmp_path, remotes, library, capsys
):
    """AC-1 with a tree already held: ``--force`` fetches the tag again, the
    remote is gone, so the fetch fails and ls-remote fails. Exit 2 with the
    fetch's error and no ``pin:`` line; no tree is written, so the tree held
    before is the only one."""
    cat = _catalog(tmp_path, remotes)
    code, out = _clone(capsys, cat, "1.0.0")
    assert code == 0, out
    c10 = remotes["c10"]
    assert set(_trees(library)) == {c10}, out

    _take_away(remotes, tmp_path, "missing")
    code, out = _clone(capsys, cat, "1.0.0", "--force")
    assert code == 2, out
    _is_the_fetch_error(out, "v1.0")
    assert set(_trees(library)) == {c10}


# --------------------------------------------------------------- AC-2


def test_ac2_a_remote_that_answers_without_the_tag_says_so(
    tmp_path, remotes, library, capsys
):
    """AC-2: 2.0.0 builds gizmo 7.7 and the remote, which answers, has no
    v7.7: the message is ``the release builds <repo> <version>, but <url>
    has no tag <tag>`` and the exit code is 2. No tree, no ``pin:`` line."""
    cat = _catalog(tmp_path, remotes)
    code, out = _clone(capsys, cat, "2.0.0")
    assert code == 2, out
    assert _message(out) == (
        f"the release builds gizmo 7.7, but {remotes['gizmo']} has no tag v7.7"
    )
    assert "pin:" not in out
    assert _nothing_held(library)


def _unfetchable_tag(bare, name, width):
    """A tag the remote lists and cannot serve: it names a commit whose tree
    the repository does not have."""
    body = (
        f"tree {'12' * (width // 2)}\n"
        "author t <t@example.test> 1700000000 +0000\n"
        "committer t <t@example.test> 1700000000 +0000\n"
        "\n"
        "a commit without its tree\n"
    )
    proc = subprocess.run(
        ["git", "hash-object", "-t", "commit", "-w", "--stdin"],
        cwd=str(bare),
        input=body.encode("utf-8"),
        capture_output=True,
        check=True,
    )
    sha = proc.stdout.decode("ascii").strip()
    git("update-ref", f"refs/tags/{name}", sha, cwd=bare)


def test_ac2_a_remote_that_has_the_tag_gives_the_error_of_the_fetch(
    tmp_path, remotes, library, capsys
):
    """AC-2: the remote answers ``git ls-remote`` and lists v7.7, and the
    fetch of that tag fails (the remote cannot pack the tag's commit): the
    fetch's error is printed, not ``has no tag``, and the exit code is 2."""
    cat = _catalog(tmp_path, remotes)
    _unfetchable_tag(remotes["gizmo_bare"], "v7.7", len(remotes["c10"]))
    listed = git("ls-remote", "--tags", remotes["gizmo"], "refs/tags/v7.7")
    assert listed.endswith("refs/tags/v7.7"), listed  # the remote lists the tag

    code, out = _clone(capsys, cat, "2.0.0")
    assert code == 2, out
    _is_the_fetch_error(out, "v7.7")
    assert _nothing_held(library)

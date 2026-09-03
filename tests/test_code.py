"""Code Trees against local bare repositories: cloning by default branch,
ref and commit, superseding, release pins from recipes, config, grep and
reading files. Skipped when git is not on PATH."""

import json
import shutil
import subprocess

import pytest

from bmc_toolkit.spec import code as C

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")

RECIPE = """SUMMARY = "Thing daemon"
SRC_URI = "git://{url};branch=main;protocol=https"
SRCREV = "{sha}"
"""


def git(*args, cwd=None) -> str:
    proc = subprocess.run(
        ["git", "-c", "core.autocrlf=false", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return proc.stdout.strip()


def make_repo(tmp_path, name, files, *, branch="main"):
    """A work tree with one commit and a bare clone of it that allows
    shallow fetches of any commit and partial (sparse) clones."""
    work = tmp_path / f"{name}-work"
    work.mkdir()
    git("init", "-q", "-b", branch, cwd=work)
    git("config", "user.email", "t@example.test", cwd=work)
    git("config", "user.name", "t", cwd=work)
    commit(work, files, "first")
    bare = tmp_path / f"{name}.git"
    git("clone", "-q", "--bare", str(work), str(bare))
    git("config", "uploadpack.allowAnySHA1InWant", "true", cwd=bare)
    git("config", "uploadpack.allowFilter", "true", cwd=bare)
    git("remote", "add", "origin", str(bare), cwd=work)
    return work, bare, bare.as_uri()


def commit(work, files, message) -> str:
    for rel, text in files.items():
        path = work / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")
    git("add", "-A", cwd=work)
    git("commit", "-q", "-m", message, cwd=work)
    return git("rev-parse", "HEAD", cwd=work)


def push(work, branch="main") -> None:
    git("push", "-q", "origin", branch, cwd=work)


THING_FILES = {
    "src/main.cpp": "int main() {\n    return powerState();\n}\n",
    "src/state.hpp": "// CurrentPowerState\nint powerState();\n",
    "src/many.txt": "hit 1\nhit 2\nhit 3\n",
    "README.md": "thing\n",
}


@pytest.fixture
def thing(tmp_path):
    return make_repo(tmp_path, "thing", THING_FILES)


@pytest.fixture
def library(tmp_path):
    return C.CodeLibrary(tmp_path / "lib")


# ---------------------------------------------------------------- clone


def test_clone_default_branch_records_provenance_and_holds_once(thing, library):
    work, bare, url = thing
    tree, fetched = library.clone("thing", url, C.Provenance("default", ""))
    assert fetched
    assert tree.commit == git("rev-parse", "HEAD", cwd=work)
    assert tree.path == library.code / "thing" / tree.commit
    assert (tree.path / "src" / "main.cpp").is_file()
    assert tree.provenance == C.Provenance("default", "main")
    meta = json.loads((tree.path / C.TREE_META).read_text("utf-8"))
    assert meta["provenance"] == {"kind": "default", "name": "main"}
    assert meta["url"] == url and meta["fetched_at"]
    again, fetched = library.clone("thing", url, C.Provenance("default", ""))
    assert not fetched and again.commit == tree.commit
    assert [t.commit for t in library.trees("thing")] == [tree.commit]
    assert library.held("thing", tree.commit[:7]).path == tree.path


def test_clone_by_tag_and_by_commit(thing, library):
    work, bare, url = thing
    first = git("rev-parse", "HEAD", cwd=work)
    git("tag", "v1", cwd=work)
    second = commit(work, {"src/main.cpp": "int main() { return 1; }\n"}, "second")
    push(work)
    push(work, "v1")
    tagged, _ = library.clone("thing", url, C.Provenance("ref", "v1"), ref="v1")
    assert tagged.commit == first
    assert tagged.provenance.label("2026-09-03T00:00:00+00:00") == "v1 2026-09-03"
    by_sha, _ = library.clone("thing", url, C.Provenance("ref", second), ref=second)
    assert by_sha.commit == second
    short, fetched = library.clone(
        "thing", url, C.Provenance("ref", second[:10]), ref=second[:10]
    )
    assert not fetched and short.commit == second  # a held prefix answers locally
    with pytest.raises(C.CodeError, match="full 40-character id"):
        library.clone("thing", url, C.Provenance("ref", "abcdef1234"), ref="abcdef1234")
    pinned, fetched = library.clone(
        "thing", url, C.Provenance("release", "1.0"), commit=first
    )
    assert not fetched and pinned.commit == first  # already held from the tag


def test_force_makes_a_new_tree_and_supersedes_the_old_one(thing, library):
    work, bare, url = thing
    old, _ = library.clone("thing", url, C.Provenance("default", ""))
    new_sha = commit(work, {"README.md": "thing 2\n"}, "second")
    push(work)
    held, fetched = library.clone("thing", url, C.Provenance("default", ""))
    assert not fetched and held.commit == old.commit  # no --force: nothing moves
    new, fetched = library.clone("thing", url, C.Provenance("default", ""), force=True)
    assert fetched and new.commit == new_sha
    trees = {t.commit: t for t in library.trees("thing")}
    assert trees[old.commit].superseded_by == new_sha
    assert not trees[new_sha].superseded
    assert (old.path / "README.md").is_file()  # never deleted


def test_force_at_the_same_commit_keeps_the_held_tree(thing, library):
    # git's objects are read-only on Windows; nothing may be half-deleted
    work, bare, url = thing
    old, _ = library.clone("thing", url, C.Provenance("default", ""))
    again, fetched = library.clone(
        "thing", url, C.Provenance("default", ""), force=True
    )
    assert not fetched and again.path == old.path and again.commit == old.commit
    assert not [
        p for p in (library.code / "thing").iterdir() if p.name.startswith(".tmp")
    ]
    assert (old.path / "src" / "main.cpp").is_file()


def test_a_failed_clone_leaves_no_directory(thing, library, tmp_path):
    work, bare, url = thing
    with pytest.raises(C.CodeError):
        library.clone("thing", url, C.Provenance("ref", "nope"), ref="nope")
    assert not list((library.code / "thing").iterdir())
    with pytest.raises(C.CodeError):
        library.clone(
            "gone", (tmp_path / "missing.git").as_uri(), C.Provenance("default", "")
        )


def test_sparse_clone_checks_out_only_the_listed_paths(tmp_path, library):
    files = {"meta-phosphor/a.bb": "x\n", "meta/big.txt": "y\n", "README": "z\n"}
    work, bare, url = make_repo(tmp_path, "distro", files)
    tree, _ = library.clone(
        "distro",
        url,
        C.Provenance("ref", "main"),
        ref="main",
        sparse=("meta-phosphor",),
    )
    assert (tree.path / "meta-phosphor" / "a.bb").is_file()
    assert not (tree.path / "meta" / "big.txt").exists()
    files = {
        "meta-phosphor/recipes/a.bb": "x\n",
        "meta-phosphor/recipes/a.patch": "y\n",
        "meta-vendor/recipes/b.bb": "z\n",
        "README": "r\n",
    }
    work, bare, url = make_repo(tmp_path, "layers", files)
    tree, _ = library.clone(
        "layers",
        url,
        C.Provenance("ref", "main"),
        ref="main",
        sparse=("/meta-*/**/*.bb",),
    )
    assert (tree.path / "meta-phosphor" / "recipes" / "a.bb").is_file()
    assert (tree.path / "meta-vendor" / "recipes" / "b.bb").is_file()
    assert not (tree.path / "meta-phosphor" / "recipes" / "a.patch").exists()
    assert not (tree.path / "README").exists()


# -------------------------------------------------------------- releases


def test_find_pin_reads_the_recipe_that_names_the_repository(tmp_path):
    distro = tmp_path / "distro"
    recipes = distro / "meta-phosphor" / "recipes-phosphor" / "things"
    recipes.mkdir(parents=True)
    (recipes / "thing_git.bb").write_text(
        RECIPE.format(url="github.com/openbmc/thing", sha="a" * 40), encoding="utf-8"
    )
    (recipes / "other_git.bb").write_text(
        RECIPE.format(url="github.com/openbmc/other-thing.git", sha="b" * 40),
        encoding="utf-8",
    )
    (recipes / "auto_git.bb").write_text(
        'SRC_URI = "git://github.com/openbmc/auto.git;branch=main"\n'
        'SRCREV = "${AUTOREV}"\n',
        encoding="utf-8",
    )
    assert C.find_pin(distro, "thing") == "a" * 40
    assert C.find_pin(distro, "other-thing") == "b" * 40
    with pytest.raises(C.CodeError, match="no recipe in this release names nope"):
        C.find_pin(distro, "nope")
    with pytest.raises(C.CodeError, match="no fixed SRCREV"):
        C.find_pin(distro, "auto")


# ---------------------------------------------------------------- config


def test_load_config(tmp_path):
    assert C.load_config(tmp_path) == C.Config()
    (tmp_path / "config.toml").write_text(
        '[code]\nrelease = "2.18.0"\n[code.checkouts]\nBMCWEB = "~/src/bmcweb"\n',
        encoding="utf-8",
    )
    cfg = C.load_config(tmp_path)
    assert cfg.release == "2.18.0"
    assert list(cfg.checkouts) == ["bmcweb"]
    assert cfg.checkouts["bmcweb"].name == "bmcweb"
    (tmp_path / "config.toml").write_text(
        '[code.checkouts]\nthing = "../thing-work"\n', encoding="utf-8"
    )
    assert C.load_config(tmp_path).checkouts["thing"] == tmp_path / "../thing-work"
    (tmp_path / "config.toml").write_text("[code]\nrelease = 3\n", encoding="utf-8")
    with pytest.raises(C.CodeError):
        C.load_config(tmp_path)
    (tmp_path / "config.toml").write_text("not = [toml", encoding="utf-8")
    with pytest.raises(C.CodeError):
        C.load_config(tmp_path)


def test_checkout_tree_reads_head(thing, tmp_path):
    work, bare, url = thing
    tree = C.checkout_tree("thing", url, work)
    assert tree.commit == git("rev-parse", "HEAD", cwd=work)
    assert tree.provenance.label() == "user checkout"
    with pytest.raises(C.CodeError, match="not a git checkout"):
        C.checkout_tree("thing", url, tmp_path)
    with pytest.raises(C.CodeError, match="not a directory"):
        C.checkout_tree("thing", url, tmp_path / "nowhere")


# -------------------------------------------------------- grep and read


def test_grep_hits_context_regex_and_glob(thing, library):
    work, bare, url = thing
    tree, _ = library.clone("thing", url, C.Provenance("default", ""))
    hits = C.grep(tree, "powerState")
    assert [(h.path, h.line, h.context) for h in hits] == [
        ("src/main.cpp", 2, False),
        ("src/state.hpp", 2, False),
    ]
    assert hits[0].text == "    return powerState();"
    hits = C.grep(tree, "powerState", context=1)
    assert [(h.path, h.line, h.context) for h in hits] == [
        ("src/main.cpp", 1, True),
        ("src/main.cpp", 2, False),
        ("src/main.cpp", 3, True),
        ("", 0, False),
        ("src/state.hpp", 1, True),
        ("src/state.hpp", 2, False),
    ]
    assert [h.path for h in C.grep(tree, "powerState", glob="src/*.hpp")] == [
        "src/state.hpp"
    ]
    assert [h.line for h in C.grep(tree, "^int .*\\(\\)", regex=True)] == [1, 2]
    assert C.grep(tree, "nothing here") == []
    assert C.grep(tree, "int main() {") == [C.Hit("src/main.cpp", 1, "int main() {")]


def test_read_lines_and_cite(thing, library):
    work, bare, url = thing
    tree, _ = library.clone("thing", url, C.Provenance("default", ""))
    path, lines = C.read_lines(tree, "src\\main.cpp")
    assert path == "src/main.cpp" and lines[:2] == [
        "int main() {",
        "    return powerState();",
    ]
    for bad in (
        "../x",
        "/etc/passwd",
        "C:/Windows/win.ini",
        "C:x",
        "src/nope.cpp",
        "src",
    ):
        with pytest.raises(C.CodeError):
            C.read_lines(tree, bad)
    line = C.cite(tree, "src/main.cpp", 1, 3, url)
    fields = line.split(" | ")
    assert fields[0] == "cite: code"
    assert fields[1] == f"thing {tree.short}"
    assert fields[2] == f"main {tree.fetched_at[:10]}"
    assert fields[3:6] == ["src/main.cpp lines 1-3", "-", url]
    assert fields[6] == str(tree.path)


def test_gh_search_without_gh_is_an_error(monkeypatch):
    monkeypatch.setattr(C.shutil, "which", lambda name: None)
    with pytest.raises(C.CodeError, match="gh is not on PATH"):
        C.gh_search("x")

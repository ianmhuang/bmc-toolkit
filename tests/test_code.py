"""Code Trees against local bare repositories: cloning by default branch,
ref and commit, superseding, release pins from recipes, config, grep and
reading files. Skipped when git is not on PATH."""

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from bmc_toolkit.spec import code as C
from tests.conftest import REPO_TEMPLATES

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")

RECIPE = """SUMMARY = "Thing daemon"
SRC_URI = "git://{url};branch=main;protocol=https"
SRCREV = "{sha}"
"""
# What the fixtures' recipes name thing by. find_pin only matches the name at
# the end, and one fixed recipe lets make_repo reuse its openbmc template.
RECIPE_URL = "github.com/openbmc/thing.git"


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
    shallow fetches of any commit and partial (sparse) clones.

    Within a pytest session the same name, files and branch are built once
    (tests/conftest.py ``_repo_templates``) and copied after that, so every
    caller gets its own pair, with the same commit id."""
    root = REPO_TEMPLATES["root"]
    if root is None:
        return _build_repo(tmp_path, name, files, branch)
    key = json.dumps([name, branch, files], sort_keys=True)
    template = root / hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    if not template.is_dir():
        template.mkdir()
        _build_repo(template, name, files, branch)
    work = tmp_path / f"{name}-work"
    bare = tmp_path / f"{name}.git"
    shutil.copytree(template / work.name, work)
    shutil.copytree(template / bare.name, bare)
    # the only absolute paths in either repository: each one's origin
    _set_origin(work / ".git" / "config", bare)
    _set_origin(bare / "config", work)
    return work, bare, bare.as_uri()


def _set_origin(config, target) -> None:
    text = config.read_text(encoding="utf-8")
    text, count = re.subn(
        r"^(\s*url = ).*$",
        lambda m: m.group(1) + str(target).replace("\\", "/"),
        text,
        flags=re.MULTILINE,
    )
    assert count == 1, config
    config.write_text(text, encoding="utf-8", newline="")


def _build_repo(tmp_path, name, files, branch):
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


def _refs(bare) -> dict[str, str]:
    lines = git("ls-remote", str(bare)).splitlines()
    return {ref: sha for sha, ref in (line.split("\t") for line in lines)}


def test_make_repo_copies_do_not_share_state(tmp_path):
    # a copy's commits, pushes and tags reach its own bare repository only;
    # the next copy starts from the template as it was built
    assert REPO_TEMPLATES["root"] is not None
    files = {"README.md": "copied\n"}
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    work1, bare1, _ = make_repo(tmp_path / "one", "copied", files)
    first = git("rev-parse", "HEAD", cwd=work1)
    second = commit(work1, {"README.md": "changed\n"}, "second")
    push(work1)
    git("tag", "v1", cwd=work1)
    push(work1, "v1")
    assert _refs(bare1)["refs/heads/main"] == second
    assert "refs/tags/v1" in _refs(bare1)

    work2, bare2, url2 = make_repo(tmp_path / "two", "copied", files)
    assert git("rev-parse", "HEAD", cwd=work2) == first
    assert _refs(bare2) == {"HEAD": first, "refs/heads/main": first}
    origin = git("remote", "get-url", "origin", cwd=work2)
    assert Path(origin).resolve() == bare2.resolve()
    assert url2 == bare2.as_uri()


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


def test_a_default_clone_retires_default_trees_of_other_branches(thing, library):
    # a changed catalog ref: the tree fetched under the old ref is superseded,
    # trees held under --ref or --release are not
    work, bare, url = thing
    first = git("rev-parse", "HEAD", cwd=work)
    for branch in ("sdk-a", "sdk-b", "other"):
        git("checkout", "-q", "-b", branch, "main", cwd=work)
        commit(work, {f"{branch}.c": f"int {branch[-1]};\n"}, branch)
        push(work, branch)
    old, _ = library.clone("thing", url, C.Provenance("default", "sdk-a"), ref="sdk-a")
    kept, _ = library.clone("thing", url, C.Provenance("ref", "other"), ref="other")
    pin, _ = library.clone("thing", url, C.Provenance("release", "1.0"), commit=first)
    new, fetched = library.clone(
        "thing", url, C.Provenance("default", "sdk-b"), ref="sdk-b"
    )
    assert fetched
    trees = {t.commit: t for t in library.trees("thing")}
    assert trees[old.commit].superseded_by == new.commit
    assert not trees[new.commit].superseded
    assert not trees[kept.commit].superseded
    assert not trees[pin.commit].superseded


def test_a_renamed_remote_default_branch_supersedes_the_old_tree(thing, library):
    work, bare, url = thing
    old, _ = library.clone("thing", url, C.Provenance("default", ""))
    git("checkout", "-q", "-b", "trunk", cwd=work)
    new_sha = commit(work, {"README.md": "thing on trunk\n"}, "trunk")
    push(work, "trunk")
    git("symbolic-ref", "HEAD", "refs/heads/trunk", cwd=bare)
    held, fetched = library.clone("thing", url, C.Provenance("default", ""))
    assert not fetched and held.commit == old.commit  # no --force: nothing moves
    new, fetched = library.clone("thing", url, C.Provenance("default", ""), force=True)
    assert fetched and new.commit == new_sha
    assert new.provenance == C.Provenance("default", "trunk")
    trees = {t.commit: t for t in library.trees("thing")}
    assert trees[old.commit].superseded_by == new_sha


def test_a_branch_moved_back_makes_its_old_tree_current_again(thing, library):
    work, bare, url = thing
    first, _ = library.clone("thing", url, C.Provenance("default", ""))
    second_sha = commit(work, {"README.md": "thing 2\n"}, "second")
    push(work)
    library.clone("thing", url, C.Provenance("default", ""), force=True)
    git("reset", "-q", "--hard", first.commit, cwd=work)
    git("push", "-q", "-f", "origin", "main", cwd=work)
    again, fetched = library.clone(
        "thing", url, C.Provenance("default", ""), force=True
    )
    assert not fetched and again.commit == first.commit
    trees = {t.commit: t for t in library.trees("thing")}
    assert not trees[first.commit].superseded
    assert trees[second_sha].superseded_by == first.commit
    meta = json.loads((first.path / C.TREE_META).read_text("utf-8"))
    assert "superseded_by" not in meta


def test_a_default_landing_on_a_tree_superseded_under_another_name_revives_it(
    thing, library
):
    # catalog ref main, then dev, then trunk, which points back at main's commit:
    # no two trees may supersede each other (prune would remove both)
    work, bare, url = thing
    first = git("rev-parse", "HEAD", cwd=work)
    old, _ = library.clone("thing", url, C.Provenance("default", "main"), ref="main")
    git("checkout", "-q", "-b", "dev", cwd=work)
    commit(work, {"dev.c": "int dev;\n"}, "dev")
    push(work, "dev")
    dev, _ = library.clone("thing", url, C.Provenance("default", "dev"), ref="dev")
    git("branch", "trunk", first, cwd=work)
    push(work, "trunk")
    back, fetched = library.clone(
        "thing", url, C.Provenance("default", "trunk"), ref="trunk"
    )
    assert not fetched and back.commit == old.commit
    trees = {t.commit: t for t in library.trees("thing")}
    assert not trees[old.commit].superseded
    assert trees[dev.commit].superseded_by == old.commit


def test_a_default_landing_on_a_superseded_ref_tree_retires_nothing(thing, library):
    work, bare, url = thing
    first = git("rev-parse", "HEAD", cwd=work)
    git("checkout", "-q", "-b", "rel", cwd=work)
    push(work, "rel")
    stale, _ = library.clone("thing", url, C.Provenance("ref", "rel"), ref="rel")
    commit(work, {"rel.c": "int rel;\n"}, "rel")
    push(work, "rel")
    library.clone("thing", url, C.Provenance("ref", "rel"), ref="rel", force=True)
    git("checkout", "-q", "-b", "d1", "main", cwd=work)
    commit(work, {"d1.c": "int d1;\n"}, "d1")
    push(work, "d1")
    current, _ = library.clone("thing", url, C.Provenance("default", "d1"), ref="d1")
    git("branch", "back", first, cwd=work)
    push(work, "back")
    library.clone("thing", url, C.Provenance("default", "back"), ref="back")
    trees = {t.commit: t for t in library.trees("thing")}
    assert trees[stale.commit].superseded  # still: it is a --ref tree
    assert not trees[current.commit].superseded


def test_a_held_ref_tree_does_not_retire_the_default_of_its_branch(thing, library):
    work, bare, url = thing
    git("checkout", "-q", "-b", "sdk", cwd=work)
    push(work, "sdk")
    default, _ = library.clone("thing", url, C.Provenance("default", "sdk"), ref="sdk")
    # make the order of the two clones certain, so the newer --ref tree is
    # the one that answers
    default.fetched_at = "2026-01-01T00:00:00+00:00"
    library.write_tree(default)
    commit(work, {"sdk.c": "int sdk;\n"}, "sdk")
    push(work, "sdk")
    newer, _ = library.clone(
        "thing", url, C.Provenance("ref", "sdk"), ref="sdk", force=True
    )
    held, fetched = library.clone(
        "thing", url, C.Provenance("default", "sdk"), ref="sdk"
    )
    assert not fetched and held.path == newer.path
    trees = {t.commit: t for t in library.trees("thing")}
    assert not trees[default.commit].superseded


def test_a_ref_and_the_same_named_default_answer_each_other(
    thing, library, monkeypatch
):
    def no_git(*a, **k):
        raise AssertionError("git must not run")

    work, bare, url = thing
    git("checkout", "-q", "-b", "sdk", cwd=work)
    commit(work, {"sdk.c": "int sdk;\n"}, "sdk")
    push(work, "sdk")
    other = C.CodeLibrary(library.root.parent / "lib2")
    by_ref, _ = library.clone("thing", url, C.Provenance("ref", "sdk"), ref="sdk")
    default, _ = other.clone("thing", url, C.Provenance("default", "sdk"), ref="sdk")
    monkeypatch.setattr(C, "run_git", no_git)
    held, fetched = library.clone(
        "thing", url, C.Provenance("default", "sdk"), ref="sdk"
    )
    assert not fetched and held.path == by_ref.path
    held, fetched = other.clone("thing", url, C.Provenance("ref", "sdk"), ref="sdk")
    assert not fetched and held.path == default.path


def test_trees_fetched_within_one_second_sort_newest_first(thing, library):
    # the order _already_held and reading rely on; a whole-second stamp an
    # older version wrote sorts before a same-second one with a fraction
    work, bare, url = thing
    git("tag", "v1", cwd=work)
    push(work, "v1")
    first, _ = library.clone("thing", url, C.Provenance("ref", "v1"), ref="v1")
    commit(work, {"README.md": "thing 2\n"}, "second")
    push(work)
    second, _ = library.clone("thing", url, C.Provenance("ref", "main"), ref="main")
    stamp = second.fetched_at[:19] + "+00:00"
    assert "." in second.fetched_at and second.fetched_at > stamp
    first.fetched_at = stamp  # the same second, whole-second form
    library.write_tree(first)
    assert [t.commit for t in library.trees("thing")] == [second.commit, first.commit]


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


@pytest.mark.parametrize(
    "url",
    ["/D:/999.%20Temp/pytest-1/test0/thing.git", "/tmp/pytest-1/test0/thing.git"],
)
def test_find_pin_matches_a_local_path_url(tmp_path, url):
    # the fixtures' recipes use RECIPE_URL; a bare repository's path, as a
    # file URI gives it on Windows and on POSIX, names thing just as well
    recipes = tmp_path / "meta-phosphor" / "recipes-phosphor" / "things"
    recipes.mkdir(parents=True)
    (recipes / "thing_git.bb").write_text(
        RECIPE.format(url=url, sha="a" * 40), encoding="utf-8"
    )
    assert C.find_pin(tmp_path, "thing") == "a" * 40
    with pytest.raises(C.CodeError, match="no recipe in this release names test0"):
        C.find_pin(tmp_path, "test0")


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


def test_find_pin_recipe_reports_the_path_and_refuses_disagreeing_layers(tmp_path):
    distro = tmp_path / "distro"
    phosphor = distro / "meta-phosphor" / "recipes-phosphor" / "things"
    vendor = distro / "meta-vendor" / "recipes-phosphor" / "things"
    phosphor.mkdir(parents=True)
    vendor.mkdir(parents=True)
    (phosphor / "thing_git.bb").write_text(
        RECIPE.format(url="github.com/openbmc/thing", sha="a" * 40), encoding="utf-8"
    )
    rev, recipe = C.find_pin_recipe(distro, "thing")
    assert rev == "a" * 40
    assert recipe == "meta-phosphor/recipes-phosphor/things/thing_git.bb"
    # a second layer agreeing on the commit is fine
    (vendor / "thing_%.bbappend").write_text("x\n", encoding="utf-8")
    (vendor / "thing_git.bb").write_text(
        RECIPE.format(url="github.com/openbmc/thing.git", sha="a" * 40),
        encoding="utf-8",
    )
    assert C.find_pin(distro, "thing") == "a" * 40
    # a layer pinning another commit is reported with both paths
    (vendor / "thing_git.bb").write_text(
        RECIPE.format(url="github.com/openbmc/thing.git", sha="b" * 40),
        encoding="utf-8",
    )
    with pytest.raises(C.CodeError, match="different commits") as exc:
        C.find_pin(distro, "thing")
    message = str(exc.value)
    assert (
        "meta-phosphor/recipes-phosphor/things/thing_git.bb pins aaaaaaaaaaaa"
        in message
    )
    assert (
        "meta-vendor/recipes-phosphor/things/thing_git.bb pins bbbbbbbbbbbb" in message
    )


def test_clone_ref_fallback_cleans_its_directory_with_the_readonly_aware_remover(
    thing, library, monkeypatch
):
    """The sha fallback of _clone_ref removes a half-made directory the
    same way every other path does (git objects are read-only on Windows)."""
    work, bare, url = thing
    second = commit(work, {"README.md": "two\n"}, "second")
    push(work)
    removed = []
    real = C._rmtree

    def spy(path):
        removed.append(path)
        real(path)

    monkeypatch.setattr(C, "_rmtree", spy)
    tmp = library.code / "thing" / ".tmp-x"
    tmp.mkdir(parents=True)
    (tmp / "stale").write_text("x", encoding="utf-8")
    C._clone_ref(url, second, tmp, ())
    assert tmp in removed and (tmp / "README.md").is_file()
    real(tmp)

"""Code Trees: shallow checkouts of the Source Catalog's repositories, held
in the Library one directory per commit, reached by a Ref, a Release or the
default branch, searched and read with ``git``.

Layout::

    <library>/code/<repo>/<commit>/     the checkout (a git work tree)
    <library>/code/<repo>/<commit>/.bmc-tree.json
        {"repo": id, "url": ..., "commit": full sha,
         "provenance": {"kind": "default" | "ref" | "release", "name": ...,
                        "openbmc_commit": sha (release only)},
         "fetched_at": ISO 8601 UTC, "superseded_by": sha (optional),
         "catalog_known": false when the repository is not in the catalog
                          and its URL was guessed under GUESS_BASE}
    <library>/config.toml
        [code]
        release = "2.18.0"          default Release for every repository
        [code.checkouts]
        bmcweb = "/path/to/bmcweb"  a user checkout, wins over the Library

A Release is a tag or branch of ``openbmc/openbmc``; the recipes of its
``meta-*`` layers pin every component with ``SRCREV``. ``openbmc/openbmc``
is held as a sparse Code Tree of its own (the recipe files of every layer)
so a Release resolves without the network once fetched.

Standard library only; ``git`` and ``gh`` run as subprocesses with UTF-8.
"""

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from bmc_toolkit.spec.library import now_iso

CODE_DIRNAME = "code"
TREE_META = ".bmc-tree.json"
CONFIG_NAME = "config.toml"
OPENBMC_REPO = "openbmc"  # catalog id of openbmc/openbmc, the release source
GUESS_BASE = "https://github.com/openbmc/"  # where an unlisted repository is looked for
GIT_TIMEOUT = 600  # seconds for one git command
MAX_WHOLE_FILE = 200  # ``code`` prints a longer file only with --lines

_SHA = re.compile(r"^[0-9a-f]{7,40}$")
_SRCREV = re.compile(r'^\s*SRCREV\s*(?:=|\?=|:=)\s*"([^"]*)"', re.MULTILINE)
_SRC_URI = re.compile(r'SRC_URI\s*(?:=|\?=|:=|\+=)\s*"([^"]*)"', re.MULTILINE)


class CodeError(Exception):
    """A git or gh operation failed, or an input cannot be used; the message
    is for the user (exit 2 unless stated)."""


class GitMissing(CodeError):
    """git is not on PATH."""


@dataclass(frozen=True)
class Provenance:
    kind: str  # default | ref | release | checkout
    name: str  # branch, ref, release name, or the checkout path
    openbmc_commit: str | None = None

    def label(self, fetched_at: str | None = None) -> str:
        """The provenance as it appears in a cite: line."""
        if self.kind == "checkout":
            return "user checkout"
        if self.kind == "release":
            return f"release {self.name}"
        day = f" {fetched_at[:10]}" if fetched_at else ""
        return f"{self.name}{day}"

    def to_dict(self) -> dict:
        out = {"kind": self.kind, "name": self.name}
        if self.openbmc_commit:
            out["openbmc_commit"] = self.openbmc_commit
        return out

    @classmethod
    def from_dict(cls, data: dict) -> "Provenance":
        return cls(
            str(data.get("kind", "ref")),
            str(data.get("name", "")),
            data.get("openbmc_commit"),
        )


@dataclass
class Tree:
    """One held Code Tree, or a user checkout."""

    repo: str
    url: str
    commit: str
    path: Path
    provenance: Provenance
    fetched_at: str = ""
    superseded_by: str | None = None
    catalog_known: bool = True

    @property
    def short(self) -> str:
        return self.commit[:7]

    @property
    def label(self) -> str:
        return f"{self.repo} {self.short}"

    @property
    def superseded(self) -> bool:
        return bool(self.superseded_by)

    def to_meta(self) -> dict:
        meta = {
            "repo": self.repo,
            "url": self.url,
            "commit": self.commit,
            "provenance": self.provenance.to_dict(),
            "fetched_at": self.fetched_at,
        }
        if self.superseded_by:
            meta["superseded_by"] = self.superseded_by
        if not self.catalog_known:
            meta["catalog_known"] = False
        return meta


@dataclass
class Config:
    release: str | None = None
    checkouts: dict[str, Path] = field(default_factory=dict)


# ------------------------------------------------------------------ git


def git_path() -> str:
    path = shutil.which("git")
    if not path:
        raise GitMissing("git is not on PATH; install git to work with Code Trees")
    return path


def run_git(args: list[str], *, cwd: Path | None = None, check: bool = True):
    """Run git with UTF-8 text; CodeError with the last output line on
    failure when ``check``."""
    # longpaths: the Library path plus a 40-character commit plus a recipe
    # path passes Windows' 260-character limit; autocrlf off keeps files as
    # the repository has them, so line numbers and text match on every OS.
    cmd = [git_path(), "-c", "core.longpaths=true", "-c", "core.autocrlf=false", *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"},
        )
    except subprocess.TimeoutExpired as exc:
        raise CodeError(f"git {args[0]} took longer than {GIT_TIMEOUT}s") from exc
    except OSError as exc:
        raise CodeError(f"cannot run git: {exc}") from exc
    if check and proc.returncode != 0:
        raise CodeError(f"git {args[0]} failed: {_last_line(proc.stderr, proc.stdout)}")
    return proc


def _last_line(*streams: str) -> str:
    for stream in streams:
        lines = [ln.strip() for ln in (stream or "").splitlines() if ln.strip()]
        if lines:
            return lines[-1]
    return "no output"


def default_branch(url: str) -> str | None:
    """The remote's default branch name, from its symbolic HEAD."""
    proc = run_git(["ls-remote", "--symref", url, "HEAD"])
    for line in proc.stdout.splitlines():
        if line.startswith("ref:"):
            ref = line.split()[1]
            return ref.removeprefix("refs/heads/")
    return None


def head_commit(work: Path) -> str:
    return run_git(["rev-parse", "HEAD"], cwd=work).stdout.strip()


# -------------------------------------------------------------- config


def load_config(root: Path) -> Config:
    """``config.toml`` at the Library root; missing keys are None/empty.
    A relative checkout path is taken from the Library root."""
    path = root / CONFIG_NAME
    if not path.is_file():
        return Config()
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise CodeError(f"{path}: {exc}") from exc
    code = data.get("code", {})
    if not isinstance(code, dict):
        raise CodeError(f"{path}: [code] must be a table")
    release = code.get("release")
    if release is not None and (not isinstance(release, str) or not release.strip()):
        raise CodeError(f"{path}: code.release must be a non-empty string")
    raw = code.get("checkouts", {})
    if not isinstance(raw, dict):
        raise CodeError(f"{path}: [code.checkouts] must be a table")
    checkouts = {}
    for repo, value in raw.items():
        if not isinstance(value, str) or not value.strip():
            raise CodeError(f"{path}: code.checkouts.{repo} must be a path string")
        given = Path(value).expanduser()
        checkouts[repo.lower()] = given if given.is_absolute() else root / given
    return Config(release.strip() if release else None, checkouts)


# ------------------------------------------------------------ the store


class CodeLibrary:
    def __init__(self, root: Path):
        self.root = Path(root)

    @property
    def code(self) -> Path:
        return self.root / CODE_DIRNAME

    def repo_dir(self, repo: str) -> Path:
        return self.code / repo

    def trees(self, repo: str | None = None) -> list[Tree]:
        """Held Code Trees, newest fetched first; one repository or all."""
        out = []
        if not self.code.is_dir():
            return out
        repos = [self.code / repo] if repo else sorted(p for p in self.code.iterdir())
        for rdir in repos:
            if not rdir.is_dir():
                continue
            for tdir in sorted(p for p in rdir.iterdir() if p.is_dir()):
                tree = self.read_tree(tdir)
                if tree:
                    out.append(tree)
        out.sort(key=lambda t: t.fetched_at, reverse=True)
        return out

    def read_tree(self, tdir: Path) -> Tree | None:
        path = tdir / TREE_META
        if not path.is_file():
            return None
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return Tree(
            repo=str(meta.get("repo", tdir.parent.name)),
            url=str(meta.get("url", "")),
            commit=str(meta.get("commit", tdir.name)),
            path=tdir,
            provenance=Provenance.from_dict(meta.get("provenance", {})),
            fetched_at=str(meta.get("fetched_at", "")),
            superseded_by=meta.get("superseded_by"),
            catalog_known=bool(meta.get("catalog_known", True)),
        )

    def write_tree(self, tree: Tree) -> None:
        with open(tree.path / TREE_META, "w", encoding="utf-8", newline="") as fh:
            json.dump(tree.to_meta(), fh, indent=4, sort_keys=True)
            fh.write("\n")

    def held(self, repo: str, commit: str) -> Tree | None:
        for t in self.trees(repo):
            if t.commit == commit or (
                len(commit) >= 7 and t.commit.startswith(commit.lower())
            ):
                return t
        return None

    # -------------------------------------------------------- cloning

    def clone(
        self,
        repo: str,
        url: str,
        provenance: Provenance,
        *,
        ref: str | None = None,
        commit: str | None = None,
        sparse: tuple[str, ...] = (),
        force: bool = False,
        catalog_known: bool = True,
    ) -> tuple[Tree, bool]:
        """Bring the repository in at ``ref`` (branch or tag), at ``commit``,
        or at the default branch; returns (tree, fetched). A tree already
        held at the resolved commit is returned with fetched False."""
        held = self._already_held(repo, provenance, ref, commit)
        if held is not None and not force:
            return held, False
        if ref and _SHA.match(ref) and len(ref) < 40:
            raise CodeError(
                f"{ref} looks like a commit; fetching one needs its full "
                f"40-character id (a branch or tag name is fine as it is)"
            )
        rdir = self.repo_dir(repo)
        rdir.mkdir(parents=True, exist_ok=True)
        tmp = rdir / f".tmp-{os.getpid()}"
        if tmp.exists():
            _rmtree(tmp)
        try:
            if commit:
                _fetch_commit(url, commit, tmp, sparse)
            else:
                _clone_ref(url, ref, tmp, sparse)
            sha = head_commit(tmp)
            if provenance.kind == "default" and not provenance.name:
                branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=tmp)
                provenance = Provenance("default", branch.stdout.strip())
            target = rdir / sha
            existing = self.read_tree(target) if target.exists() else None
            if existing is not None:  # the same commit again: keep what we hold
                _rmtree(tmp)
                return existing, False
            if target.exists():  # a directory without its meta: a leftover
                _rmtree(target)
            os.replace(tmp, target)
        except BaseException:
            try:
                _rmtree(tmp)
            except CodeError:
                pass  # the original error matters more
            raise
        tree = Tree(
            repo, url, sha, target, provenance, now_iso(), catalog_known=catalog_known
        )
        self.write_tree(tree)
        self._supersede(tree)
        return tree, True

    def _already_held(self, repo, provenance, ref, commit) -> Tree | None:
        """The tree that answers without the network: the same commit, or
        the same moving name (branch, tag, default) not yet superseded."""
        if commit:
            return self.held(repo, commit)
        if ref and _SHA.match(ref):
            return self.held(repo, ref)
        for t in self.trees(repo):
            if t.superseded or t.provenance.kind != provenance.kind:
                continue
            if provenance.kind == "default" and not provenance.name:
                return t
            if t.provenance.name == provenance.name:
                return t
        return None

    def _supersede(self, new: Tree) -> None:
        """Older trees reached by the same moving name point at the new one."""
        for old in self.trees(new.repo):
            if old.commit == new.commit or old.superseded_by:
                continue
            same = (old.provenance.kind, old.provenance.name) == (
                new.provenance.kind,
                new.provenance.name,
            )
            if same and old.provenance.kind in ("default", "ref", "release"):
                old.superseded_by = new.commit
                self.write_tree(old)


def _rmtree(path: Path) -> None:
    """Remove a work tree, clearing the read-only bit git sets on objects
    and pack files (Windows refuses to unlink them otherwise)."""

    def retry(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    try:
        if sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=retry)
        else:
            shutil.rmtree(path, onerror=retry)  # onexc arrived in 3.12
    except OSError as exc:
        raise CodeError(f"cannot remove {path}: {exc}") from exc
    if path.exists():
        raise CodeError(f"cannot remove {path}: still there")


def _clone_args(sparse: tuple[str, ...]) -> list[str]:
    args = ["--depth", "1", "--quiet"]
    if sparse:
        args += ["--filter=blob:none", "--sparse"]
    return args


def _apply_sparse(work: Path, sparse: tuple[str, ...]) -> None:
    """Directories in cone mode; entries with a glob (``/meta-*/**/*.bb``)
    switch to pattern mode so recipe files of every layer come without the
    layers' sources."""
    if not sparse:
        return
    args = ["sparse-checkout", "set"]
    if any(ch in entry for entry in sparse for ch in "*?["):
        args.append("--no-cone")
    run_git([*args, *sparse], cwd=work)


def _clone_ref(url: str, ref: str | None, tmp: Path, sparse: tuple[str, ...]) -> None:
    args = ["clone", *_clone_args(sparse)]
    if ref:
        args += ["--branch", ref]
    proc = run_git([*args, url, str(tmp)], check=False)
    if proc.returncode != 0:
        if ref and _SHA.match(ref):
            if tmp.exists():
                _rmtree(tmp)
            _fetch_commit(url, ref, tmp, sparse)
            return
        raise CodeError(f"git clone failed: {_last_line(proc.stderr, proc.stdout)}")
    _apply_sparse(tmp, sparse)


def _fetch_commit(url: str, commit: str, tmp: Path, sparse: tuple[str, ...]) -> None:
    """A shallow fetch of one commit (GitHub allows fetching any sha)."""
    tmp.mkdir(parents=True, exist_ok=True)
    run_git(["init", "--quiet", str(tmp)])
    run_git(["remote", "add", "origin", url], cwd=tmp)
    fetch = ["fetch", "--depth", "1", "--quiet"]
    if sparse:
        fetch.append("--filter=blob:none")
        _apply_sparse(tmp, sparse)
    proc = run_git([*fetch, "origin", commit], cwd=tmp, check=False)
    if proc.returncode != 0:
        raise CodeError(
            f"git fetch of {commit[:12]} failed: {_last_line(proc.stderr, proc.stdout)}"
        )
    run_git(["checkout", "--quiet", "FETCH_HEAD"], cwd=tmp)


# ------------------------------------------------------------ releases


def find_pin(openbmc_tree: Path, repo: str) -> str:
    """The SRCREV a Release's recipes give for the repository."""
    return find_pin_recipe(openbmc_tree, repo)[0]


def find_pin_recipe(openbmc_tree: Path, repo: str) -> tuple[str, str]:
    """(SRCREV, recipe path relative to the tree) for the repository.

    The recipe is a ``.bb`` or ``.inc`` of any ``meta-*`` layer whose SRC_URI
    names the repository (``.../<repo>.git`` or ``.../<repo>;``). Several
    recipes may name it (a layer overriding another); they must agree on
    the commit, otherwise the CodeError lists them all.
    """
    wanted = re.compile(rf"/{re.escape(repo)}(?:\.git)?(?:;|\"|\s|$)")
    candidates = []
    pins: dict[str, list[str]] = {}
    recipes = list(openbmc_tree.rglob("*.bb")) + list(openbmc_tree.rglob("*.inc"))
    for path in sorted(recipes):
        if ".git" in path.parts or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        uris = _SRC_URI.findall(text)
        if not any(wanted.search(u) for u in uris):
            continue
        rel = path.relative_to(openbmc_tree).as_posix()
        m = _SRCREV.search(text)
        if m:
            rev = m.group(1).strip()
            if rev and "${" not in rev:
                pins.setdefault(rev, []).append(rel)
                continue
            candidates.append(f"{rel} pins {rev or 'nothing'}")
        else:
            candidates.append(f"{rel} has no SRCREV")
    if len(pins) > 1:
        listed = "; ".join(
            f"{', '.join(paths)} pins {rev[:12]}" for rev, paths in pins.items()
        )
        raise CodeError(
            f"the recipes of this release pin {repo} at different commits: {listed}"
        )
    if pins:
        rev, paths = next(iter(pins.items()))
        return rev, paths[0]
    if candidates:
        raise CodeError(
            f"no fixed SRCREV for {repo} in this release: {'; '.join(candidates)}"
        )
    raise CodeError(f"no recipe in this release names {repo}")


# -------------------------------------------------------------- reading


def checkout_tree(repo: str, url: str, path: Path) -> Tree:
    """A user checkout as a Tree: HEAD is read, provenance is the path."""
    if not path.is_dir():
        raise CodeError(f"user checkout for {repo} is not a directory: {path}")
    proc = run_git(["rev-parse", "HEAD"], cwd=path, check=False)
    if proc.returncode != 0:
        raise CodeError(f"user checkout for {repo} is not a git checkout: {path}")
    return Tree(repo, url, proc.stdout.strip(), path, Provenance("checkout", str(path)))


@dataclass(frozen=True)
class Hit:
    path: str
    line: int
    text: str
    context: bool = False  # a context line, not a match


def grep(
    tree: Tree,
    pattern: str,
    *,
    regex: bool = False,
    glob: str | None = None,
    context: int = 0,
) -> list[Hit]:
    """``git grep -n`` over the tree; hits and, with ``context``, the lines
    around them (a ``--`` separator becomes a Hit with line 0).

    Two passes: the matches alone, then with context; ``-z`` puts NUL after
    the path and the line number, which is unambiguous, but loses the
    match/context mark, so the first pass supplies it.
    """
    base = ["grep", "-n", "-I", "-z", "-E" if regex else "-F", "-e", pattern]
    if glob:
        base += ["--", glob]
    matches = {(h.path, h.line) for h in _grep_pass(tree, base)}
    if not matches:
        return []
    if not context:
        return _grep_pass(tree, base)
    with_context = base[:1] + ["-C", str(context)] + base[1:]
    return [
        Hit(h.path, h.line, h.text, h.line != 0 and (h.path, h.line) not in matches)
        for h in _grep_pass(tree, with_context)
    ]


def _grep_pass(tree: Tree, args: list[str]) -> list[Hit]:
    proc = run_git(args, cwd=tree.path, check=False)
    if proc.returncode == 1:
        return []
    if proc.returncode != 0:
        raise CodeError(f"git grep failed: {_last_line(proc.stderr, proc.stdout)}")
    hits = []
    for raw in proc.stdout.split(chr(10)):
        if raw == "--":
            hits.append(Hit("", 0, "", False))
            continue
        parts = raw.split(chr(0), 2)
        if len(parts) != 3 or not parts[1].isdigit():
            continue
        hits.append(Hit(parts[0], int(parts[1]), parts[2].rstrip(chr(13))))
    return hits


def read_lines(tree: Tree, rel: str) -> tuple[str, list[str]]:
    """(normalised path, lines) of a file inside the tree."""
    clean = PurePosixPath(rel.replace("\\", "/"))
    if (
        clean.is_absolute()
        or ".." in clean.parts
        or any(":" in part for part in clean.parts)  # a Windows drive
    ):
        raise CodeError(f"{rel} is not a path inside the tree")
    path = tree.path.joinpath(*clean.parts)
    try:
        inside = path.resolve().is_relative_to(tree.path.resolve())
    except OSError:
        inside = False
    if not inside:
        raise CodeError(f"{rel} is not a path inside the tree")
    if not path.is_file():
        raise CodeError(f"{clean} is not a file in {tree.label}")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise CodeError(f"cannot read {clean}: {exc}") from exc
    return str(clean), text.split("\n")


def cite(tree: Tree, path: str, first: int, last: int, origin: str) -> str:
    return " | ".join(
        [
            f"cite: {CODE_DIRNAME}",
            tree.label,
            tree.provenance.label(tree.fetched_at),
            f"{path} lines {first}-{last}",
            "-",
            origin,
            str(tree.path),
        ]
    )


# ------------------------------------------------------------------- gh


def gh_search(
    pattern: str, owner: str = "openbmc", limit: int = 20
) -> list[tuple[str, str]]:
    """(repository, path) pairs from ``gh search code``; CodeError when gh
    is missing or not logged in."""
    gh = shutil.which("gh")
    if not gh:
        raise CodeError("gh is not on PATH; install GitHub CLI and run: gh auth login")
    try:
        proc = subprocess.run(
            [
                gh,
                "search",
                "code",
                pattern,
                "--owner",
                owner,
                "--limit",
                str(limit),
                "--json",
                "repository,path",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CodeError(f"cannot run gh: {exc}") from exc
    if proc.returncode != 0:
        raise CodeError(f"gh search failed: {_last_line(proc.stderr, proc.stdout)}")
    try:
        items = json.loads(proc.stdout or "[]")
    except ValueError as exc:
        raise CodeError(f"gh returned something other than JSON: {exc}") from exc
    out = []
    for item in items:
        repo = item.get("repository", {})
        name = repo.get("nameWithOwner") or repo.get("name") or "?"
        out.append((str(name), str(item.get("path", ""))))
    return out


def guess_url(repo_id: str) -> str:
    """The URL an unlisted repository is looked for at."""
    return f"{GUESS_BASE}{repo_id}.git"


__all__ = [
    "CODE_DIRNAME",
    "CONFIG_NAME",
    "GUESS_BASE",
    "MAX_WHOLE_FILE",
    "OPENBMC_REPO",
    "TREE_META",
    "CodeError",
    "CodeLibrary",
    "Config",
    "GitMissing",
    "Hit",
    "Provenance",
    "Tree",
    "checkout_tree",
    "cite",
    "default_branch",
    "find_pin",
    "find_pin_recipe",
    "gh_search",
    "grep",
    "guess_url",
    "load_config",
    "read_lines",
    "run_git",
]

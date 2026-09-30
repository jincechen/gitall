#!/usr/bin/env python3
"""gitall -- run git in several repositories at once.

Usage:  gitall [options] <git command> [git arguments]

Type gitall where you would type git: the command runs in every repo, and its
arguments mean what they mean in git. A few commands get extra help:

  status          one line per repo (branch, ahead/behind, changes), then the changed
                  files; give any status option (e.g. -s) for plain git status
  commit          previews what each repo would commit, asks once, then commits;
                  repos with nothing to commit are skipped; {repo} in the message
                  becomes the repo's folder name; --dry-run only previews;
                  without -m (or with -c, -e, --squash) git opens an editor per repo
  push            only repos with unpushed commits; previews them and asks once
  pull            one line per repo: fast-forward, merged, up to date or CONFLICT
  fetch           one line per repo: what came in, then ahead/behind
  anything else   runs in every repo; repos with no output are left out; commands
                  that change things show what will run and ask first

Choosing repos (these options go before the git command):
  -r, --repo SPEC     only these repos. SPEC is a comma-separated list of:
                        name      the repo's name, else part of a name (any case)
                        glob      e.g. 'Deck*'
                        N, N-M    positions in the list (see -l)
                        group     a [group] from .gitall
                        :state    dirty clean staged modified untracked ahead behind
                                  diverged noupstream stash merging detached
                                  on=BRANCH has=BRANCH
                        !term     leave these out
                      names and groups add up; :states keep the repos in any of
                      them, e.g.  -r decks -r :dirty,:ahead
  -x, --exclude SPEC  leave these repos out
  -l, --list          list the chosen repos with their numbers and state

Other options:
  -y, --yes           don't ask for confirmation (also accepted as the last argument)
  -q, --quiet         leave out repos with nothing to report
  --prefix            start each output line with the repo's path (grep, ls-files, ...)
  -C DIR              start in DIR instead of the current directory
  -c NAME=VALUE, --no-pager, --literal-pathspecs, ...
                      git's own options are passed on to git
  -h, --help          show this help

Which repos: those listed in the nearest .gitall file (in the current directory or a
parent); else every git repo directly inside the current directory; else, inside a
repo, that repo and its siblings. A .gitall file has one entry per line: a name, a
path or a glob ('Deck*', 'archive/*'); '!entry' leaves repos out; '[name]' starts a
group and '[]' ends it; # starts a comment.
"""
import errno
import fnmatch
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

PROG = Path(__file__).stem              # rename the file and messages/config name follow
CONFIG = f".{PROG}"

# commands that only show things: no confirmation needed
READ_ONLY = {
    "status", "diff", "log", "show", "shortlog", "blame", "annotate", "grep", "ls-files",
    "ls-tree", "ls-remote", "rev-parse", "rev-list", "describe", "cat-file", "check-ignore",
    "check-attr", "check-mailmap", "check-ref-format", "name-rev", "count-objects",
    "whatchanged", "fetch", "range-diff", "for-each-ref", "show-ref", "show-branch",
    "merge-base", "cherry", "diff-tree", "diff-files", "diff-index", "var", "verify-commit",
    "verify-tag", "fsck",
}
NO_CONFIRM = READ_ONLY | {"add", "pull"}
# commands with their own handling, and other common built-ins: never looked up as aliases
COMMON = READ_ONLY | {
    "add", "pull", "push", "commit", "switch", "checkout", "branch", "merge", "rebase", "reset",
    "restore", "stash", "tag", "remote", "config", "clean", "rm", "mv", "init", "clone", "help",
    "version", "reflog", "worktree", "notes", "submodule", "cherry-pick", "revert", "am",
    "apply", "archive", "format-patch", "gc", "maintenance", "bisect", "mergetool", "difftool",
}

# options that make a command interactive (run attached to the terminal), per command;
# the same letters mean something else elsewhere (log -p, grep -i, grep -e)
INTERACTIVE = {
    "add": {"-p", "--patch", "-i", "--interactive", "-e", "--edit"},
    "checkout": {"-p", "--patch"}, "reset": {"-p", "--patch"}, "restore": {"-p", "--patch"},
    "stash": {"-p", "--patch"}, "clean": {"-i", "--interactive"}, "rebase": {"-i", "--interactive"},
    "merge": {"-e", "--edit"}, "revert": {"-e", "--edit"}, "cherry-pick": {"-e", "--edit"},
    "tag": {"-e", "--edit"}, "config": {"-e", "--edit"}, "am": {"-i", "--interactive"},
    "commit": {"-p", "--patch", "--interactive"},
    "pull": {"--rebase=interactive", "--rebase=i", "-r=i", "-ri"},
}
# branch options that create, delete, rename or configure branches, and ones that list them
BRANCH_CHANGES = {"--delete", "--move", "--copy", "--set-upstream-to", "--unset-upstream",
                  "--edit-description", "--force", "--track", "--no-track", "--create-reflog"}
BRANCH_LISTS = {"-l", "--list", "-v", "-vv", "--verbose", "--contains", "--no-contains",
                "--merged", "--no-merged", "--points-at", "--show-current"}
TAG_CHANGES = {"-d", "--delete", "-a", "--annotate", "-s", "--sign", "-u", "--local-user",
               "-f", "--force", "-m", "--message", "-F", "--file", "-e", "--edit"}
TAG_LISTS = {"-l", "--list", "--contains", "--no-contains", "--points-at", "--merged",
             "--no-merged", "-v", "--verify"}
CONFIG_READS = {"-l", "--list", "--get", "--get-all", "--get-regexp", "--get-urlmatch",
                "--get-color", "--get-colorbool"}
CONFIG_WRITES = {"--add", "--replace-all", "--unset", "--unset-all", "--rename-section",
                 "--remove-section", "-e", "--edit"}
# options whose value is a file: made absolute, so they mean the file you're looking at
FILE_OPTS = {
    "commit": {"-F", "--file", "-t", "--template"}, "tag": {"-F", "--file"},
    "merge": {"-F", "--file"}, "notes": {"-F", "--file"}, "archive": {"-o", "--output"},
    "format-patch": {"-o", "--output-directory"}, "diff": {"--output"}, "log": {"--output"},
    "show": {"--output"},
}
# options that take a value, so the value is never read as an option (commit -am "-Fix"):
# short ones per command (they mean different things elsewhere), long ones everywhere
SHORT_VALUES = {"commit": "mFCct", "tag": "mFu", "merge": "mF", "notes": "mFCc",
                "archive": "o", "format-patch": "o"}
LONG_VALUES = {"--message", "--file", "--template", "--author", "--date", "--trailer", "--cleanup",
               "--format", "--pretty", "--grep", "--reuse-message", "--reedit-message", "--fixup",
               "--squash", "--output", "--output-directory"}
# branch/tag options whose value is the next argument (branch --sort -committerdate)
LIST_VALUES = {"--sort", "--format", "--contains", "--no-contains", "--merged", "--no-merged",
               "--points-at", "-u", "--set-upstream-to", "-m", "--message", "-F", "--file"}

# git's own options that may come before the command: passed on to every git call
GIT_FLAGS = {"--literal-pathspecs", "--glob-pathspecs", "--noglob-pathspecs", "--icase-pathspecs",
             "--no-optional-locks", "--no-replace-objects", "--no-lazy-fetch", "--no-advice"}
GIT_REFUSED = ("--git-dir", "--work-tree", "--namespace", "--bare", "--exec-path", "-p", "--paginate")

GLOB_CHARS = "*?["
STATUS_FILES = 10                       # changed files listed per repo by status

NO_COLOR = bool(os.environ.get("NO_COLOR"))
TTY = sys.stdout.isatty()
if os.name == "nt" and TTY:
    os.system("")  # enable ANSI colours in the Windows console


def _c(code):
    return lambda t: f"\033[{code}m{t}\033[0m" if TTY and not NO_COLOR else t


BOLD, RED, GREEN, YELLOW = _c("1"), _c("31"), _c("32"), _c("33")


# ---- output --------------------------------------------------------------------------
class PipeClosed(Exception):
    """The reader of our output went away (gitall log | head)."""


def _write(stream, text):
    try:
        stream.buffer.write(text.encode("utf-8", "replace"))
        stream.flush()
    except BrokenPipeError:
        raise PipeClosed from None
    except OSError as e:
        if e.errno == errno.EINVAL:  # Windows says this for a closed pipe
            raise PipeClosed from None
        raise


def out(text=""):
    _write(sys.stdout, text + "\n")


def err(text=""):
    sys.stdout.flush()
    _write(sys.stderr, text + "\n")


def die(msg, code=2):
    err(RED(f"{PROG}: {msg}"))
    sys.exit(code)


def indent(text):
    return "    " + text.replace("\n", "\n    ")


def header(text):
    out()
    out(BOLD(f"== {text}"))


def quote(arg):
    """An argument as you'd type it, for messages."""
    if arg and not re.search(r"[\s\"'$`!&|<>;(){}*?\[\]\\]", arg):
        return arg
    return '"' + arg.replace('"', '\\"') + '"'


def shown(args):
    return " ".join(quote(a) for a in args)


def plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def ago(seconds):
    for size, unit in ((86400, "day"), (3600, "hour"), (60, "minute")):
        if seconds >= size:
            return f"{plural(int(seconds // size), unit)} ago"
    return "just now"


def confirm(question, yes):
    if yes:
        return
    if not sys.stdin.isatty():
        die("not running interactively: re-run with -y")
    try:
        ans = input(f"{question} [y/N] ")
    except EOFError:
        out()
        die("no answer (input closed): re-run with -y", code=1)
    if ans.strip().lower() not in ("y", "yes"):
        out("aborted, nothing changed")
        sys.exit(1)


# ---- running git ---------------------------------------------------------------------
USER_OPTS = []      # git's own options from the command line, e.g. ["-c", "core.abbrev=12"]


class Res:
    def __init__(self, rc, out_, err_):
        self.rc, self.out, self.err = rc, out_, err_


def _text(b):
    return b.decode("utf-8", "replace").rstrip("\n")


def git(cwd, *args, live=False, colour=False, internal=False):
    """Run git in cwd -> Res(rc, out, err).
    internal: for gitall's own queries (plain, uncoloured output);
    live: attached to the terminal (editors, prompts)."""
    if internal:
        cmd = ["git", *USER_OPTS, "-c", "core.quotePath=false", "-c", "color.ui=never"]
    else:
        cmd = ["git", "-c", "core.quotePath=false"]
        if colour and TTY and not NO_COLOR:
            cmd += ["-c", "color.ui=always"]
        cmd += USER_OPTS
    cmd += ["--no-pager", *args]
    if live:
        return Res(subprocess.call(cmd, cwd=cwd), "", "")
    p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return Res(p.returncode, _text(p.stdout), _text(p.stderr))


def git_ok(cwd, *args):
    r = git(cwd, *args, internal=True)
    return r.out if r.rc == 0 else None


def first_error(res):
    lines = [ln.strip() for ln in (res.err + "\n" + res.out).splitlines() if ln.strip()]
    for ln in lines:
        if ln.startswith(("fatal:", "error:")):
            return ln
    return lines[0] if lines else f"git exited with {res.rc}"


# ---- repos ---------------------------------------------------------------------------
def natural(name):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r"(\d+)", name)]


def key(path):
    return os.path.normcase(os.path.abspath(path))


def is_repo(p):
    return p.is_dir() and (p / ".git").exists()


def git_dir(path):
    g = path / ".git"
    if g.is_dir():
        return g
    try:
        text = g.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if text.startswith("gitdir:"):
        d = Path(text[7:].strip())
        return d if d.is_absolute() else path / d
    return None


def worktree_of(path):
    """The main repo's folder if path is a linked worktree, else None."""
    if not (path / ".git").is_file():
        return None
    d = git_dir(path)
    return d.parent.parent.parent if d and d.parent.name == "worktrees" else None


def subdirs(d):
    try:
        return sorted((p for p in d.iterdir() if p.is_dir()), key=lambda p: natural(p.name))
    except OSError:
        return []


OPS = (("MERGE_HEAD", "merge"), ("rebase-merge", "rebase"), ("rebase-apply", "rebase"),
       ("CHERRY_PICK_HEAD", "cherry-pick"), ("REVERT_HEAD", "revert"))
OP_HELP = {"merge": "merge in progress (fix conflicts and commit, or git merge --abort)",
           "rebase": "rebase in progress (git rebase --continue or --abort)",
           "cherry-pick": "cherry-pick in progress (git cherry-pick --continue or --abort)",
           "revert": "revert in progress (git revert --continue or --abort)"}


class State:
    """A repo's branch, upstream, changes and in-progress operations, from one git status."""

    def __init__(self, path, pathspec=()):
        self.path = path
        self.error = self.branch = self.oid = self.upstream = None
        self.detached = self.unborn = self.gone = False
        self.ahead = self.behind = self.stash = 0
        self.staged = self.modified = self.untracked = self.conflicts = 0
        self.files = []
        self._refs = self._remotes = None
        self.gitdir = git_dir(path)
        gd = self.gitdir
        self.op = next((op for f, op in OPS if gd and (gd / f).exists()), None)
        self.locked = bool(gd and (gd / "index.lock").exists())
        res = git(path, "--no-optional-locks", "status", "--porcelain=v2", "--branch", "--show-stash",
                  *(["--", *pathspec] if pathspec else []), internal=True)
        if res.rc:
            self.error = first_error(res)
            return
        for line in res.out.splitlines():
            if line.startswith("# "):
                name, _, val = line[2:].partition(" ")
                if name == "branch.oid":
                    self.unborn = val == "(initial)"
                    self.oid = None if self.unborn else val
                elif name == "branch.head":
                    self.detached = val == "(detached)"
                    self.branch = None if self.detached else val
                elif name == "branch.upstream":
                    self.upstream, self.gone = val, True   # until branch.ab shows it exists
                elif name == "branch.ab":
                    a, b = val.split()
                    self.ahead, self.behind, self.gone = int(a), -int(b), False
                elif name == "stash":
                    self.stash = int(val)
            elif line[:2] in ("1 ", "2 "):
                xy = line[2:4]
                path_ = line.split(" ", 9 if line[0] == "2" else 8)[-1]
                if line[0] == "2":
                    new, _, orig = path_.partition("\t")
                    path_ = f"{orig} -> {new}"
                self.staged += xy[0] != "."
                self.modified += xy[1] != "."
                self.files.append(f"{xy.replace('.', ' ')} {path_}")
            elif line.startswith("u "):
                self.conflicts += 1
                self.files.append(f"{line[2:4]} {line.split(' ', 10)[-1]}")
            elif line.startswith("? "):
                self.untracked += 1
                self.files.append(f"?? {line[2:]}")

    @property
    def dirty(self):
        return bool(self.staged or self.modified or self.untracked or self.conflicts)

    @property
    def tracking(self):
        """Has an upstream branch that exists (as of the last fetch)."""
        return bool(self.upstream) and not self.gone

    def problem(self):
        """Why it isn't safe to commit/pull/push here right now, or None."""
        if self.error:
            return self.error
        if self.locked:
            return (f"index.lock exists (another git or editor running? if not, delete "
                    f"{self.gitdir / 'index.lock'})")
        if self.op:
            return OP_HELP[self.op]
        if self.detached:
            return "detached HEAD (git switch <branch>)"
        return None

    @property
    def remotes(self):
        if self._remotes is None:
            self._remotes = (git_ok(self.path, "remote") or "").split()
        return self._remotes

    def refs(self):
        """(local branches, {remote: branches}, {remote: its default branch})"""
        if self._refs is None:
            local, remote, heads = set(), {}, {}
            text = git_ok(self.path, "for-each-ref", "--format=%(refname)%09%(symref)",
                          "refs/heads", "refs/remotes") or ""
            for line in text.splitlines():
                ref, _, sym = line.partition("\t")
                if ref.startswith("refs/heads/"):
                    local.add(ref[11:])
                elif ref.startswith("refs/remotes/"):
                    rem, _, b = ref[13:].partition("/")
                    if b != "HEAD":
                        remote.setdefault(rem, set()).add(b)
                    elif sym.startswith(f"refs/remotes/{rem}/"):
                        heads[rem] = sym[len(f"refs/remotes/{rem}/"):]
            self._refs = local, remote, heads
        return self._refs

    def has_branch(self, pattern):
        local, remote, _ = self.refs()
        return any(fnmatch.fnmatchcase(b, pattern) for b in local.union(*remote.values()))

    def fetched(self):
        """Seconds since the last fetch, or None if never."""
        for d in (self.gitdir, self.gitdir and self.gitdir.parent.parent):
            if d and (d / "FETCH_HEAD").exists():
                return time.time() - (d / "FETCH_HEAD").stat().st_mtime
        return None


class Repo:
    def __init__(self, path, root):
        self.path, self.folder = path, path.name
        try:
            self.name = path.relative_to(root).as_posix()
        except ValueError:
            self.name = path.name
        self._state = None

    @property
    def state(self):
        if self._state is None:
            self._state = State(self.path)
        return self._state

    def refresh(self):
        self._state = None

    def __repr__(self):
        return f"<Repo {self.name}>"


# ---- which repos ---------------------------------------------------------------------
class Workspace:
    def __init__(self, root, config=None):
        self.root, self.config = root, config
        self.repos, self.groups, self.hidden, self.warnings = [], {}, [], []


def find_workspace(start):
    """Where the repos are, like git finds its repo from any subfolder:
    1. the repos listed in the nearest .gitall file (start or a parent folder);
    2. else the git repos directly inside start;
    3. else, if start is inside a repo, that repo and its sibling repos."""
    for d in [start, *start.parents]:
        if (d / CONFIG).is_file():
            return read_config(d, d / CONFIG)
    ws = Workspace(start)
    found = [p for p in subdirs(start) if is_repo(p)]
    if not found:
        top = git_ok(start, "rev-parse", "--show-toplevel")
        if top:
            ws.root = Path(top).resolve().parent
            found = [p for p in subdirs(ws.root) if is_repo(p)]
    keys, here = {key(p) for p in found}, key(start)
    for p in found:
        main = worktree_of(p)
        inside = here == key(p) or here.startswith(key(p) + os.sep)
        if main is not None and key(main) in keys and not inside:
            ws.hidden.append(f"{p.name} (worktree of {main.name})")
        else:
            ws.repos.append(Repo(p, ws.root))
    return ws


def config_entry(root, entry):
    """The repos an entry of .gitall names: a name, a path, or globs per path part."""
    paths = [root]
    for part in entry.split("/"):
        if any(ch in part for ch in GLOB_CHARS):
            paths = [c for d in paths for c in subdirs(d) if fnmatch.fnmatchcase(c.name, part)
                     and (part.startswith(".") or not c.name.startswith("."))]
        else:
            paths = [d / part for d in paths]
    return [p for p in paths if is_repo(p)]


def read_config(root, cfg):
    ws = Workspace(root, cfg)
    known, excluded, group = {}, set(), None
    for n, raw in enumerate(cfg.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = re.sub(r"(^|\s)#.*", "", raw).strip()    # '#' starts a comment, 'C#' doesn't
        if not line:
            continue
        m = re.fullmatch(r"\[\s*(.*?)\s*\]", line)
        if m:
            group = m.group(1) or None                    # [] ends the group
            if group:
                ws.groups.setdefault(group.lower(), (group, []))
            continue
        exclude = line.startswith("!")
        entry = line.lstrip("!").strip()
        entry = entry.replace("\\", "/").rstrip("/")
        hits = config_entry(root, entry)
        if exclude:
            excluded |= {key(p) for p in hits}
            continue
        if not hits:
            ws.warnings.append(f"{cfg}, line {n}: '{entry}' is not a git repo, left out")
            continue
        for p in hits:
            r = known.get(key(p))
            if r is None:
                r = known[key(p)] = Repo(p, root)
                ws.repos.append(r)
            if group and r not in ws.groups[group.lower()][1]:
                ws.groups[group.lower()][1].append(r)
    ws.repos = [r for r in ws.repos if key(r.path) not in excluded]
    for g, (name, members) in ws.groups.items():
        ws.groups[g] = (name, [r for r in members if key(r.path) not in excluded])
    return ws


STATE_TESTS = {
    "dirty": lambda s: s.dirty,
    "clean": lambda s: not s.dirty,
    "staged": lambda s: s.staged > 0,
    "modified": lambda s: s.modified > 0,
    "untracked": lambda s: s.untracked > 0,
    "ahead": lambda s: s.tracking and s.ahead > 0,
    "behind": lambda s: s.tracking and s.behind > 0,
    "diverged": lambda s: s.tracking and s.ahead > 0 and s.behind > 0,
    "noupstream": lambda s: not s.tracking,
    "stash": lambda s: s.stash > 0,
    "merging": lambda s: s.op is not None,
    "detached": lambda s: s.detached,
}


def state_test(term):
    """A test for ':name' or ':on=BRANCH' / ':has=BRANCH' (term without the colon)."""
    name, eq, value = term.partition("=")
    if eq and name == "on":
        test = lambda s: fnmatch.fnmatchcase(s.branch or "", value)  # noqa: E731
    elif eq and name == "has":
        test = lambda s: s.has_branch(value)  # noqa: E731
    elif not eq and name in STATE_TESTS:
        test = STATE_TESTS[name]
    else:
        die(f"unknown state ':{term}' (states: {' '.join(STATE_TESTS)} on=BRANCH has=BRANCH)")
    return lambda r: not r.state.error and test(r.state)


def match_term(ws, term):
    """The repos a name, glob, position, range or group stands for."""
    t, repos = term.lower(), ws.repos
    m = re.fullmatch(r"(\d+)(?:-(\d+))?", term)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
        return repos[lo - 1:hi] if 1 <= lo <= hi <= len(repos) else []
    if t in ws.groups:
        return ws.groups[t][1]
    exact = [r for r in repos if t in (r.name.lower(), r.folder.lower())]
    if exact:
        return exact
    if any(ch in t for ch in GLOB_CHARS):
        return [r for r in repos if fnmatch.fnmatchcase(r.name.lower(), t)
                or fnmatch.fnmatchcase(r.folder.lower(), t)]
    return [r for r in repos if t in r.name.lower()]


def no_match(ws, term):
    listing = ", ".join(f"{i}:{r.name}" for i, r in enumerate(ws.repos, 1))
    groups = f"; groups: {', '.join(name for name, _ in ws.groups.values())}" if ws.groups else ""
    die(f"no repo matches '{term}' (repos: {listing}{groups})")


def select(ws, picks, drops):
    """The repos chosen by -r (picks) and -x (drops), in list order."""
    names, states, excluded = [], [], []
    for spec in picks:
        for term in (t.strip() for t in spec.split(",")):
            if term.startswith("!"):
                excluded.append(term[1:])
            elif term.startswith(":"):
                states.append(state_test(term[1:]))
            elif term:
                names.append(term)
    excluded += [t.strip().lstrip("!") for spec in drops for t in spec.split(",") if t.strip()]
    chosen = ws.repos
    if names:
        hits = set()
        for term in names:
            found = match_term(ws, term)
            if not found:
                no_match(ws, term)
            hits.update(found)
        chosen = [r for r in ws.repos if r in hits]
    if states:
        chosen = [r for r in chosen if any(test(r) for test in states)]
    for term in excluded:
        if term.startswith(":"):
            test = state_test(term[1:])
            chosen = [r for r in chosen if not test(r)]
        else:
            found = match_term(ws, term)
            if not found:
                no_match(ws, term)
            chosen = [r for r in chosen if r not in found]
    return chosen


# ---- what a command does -------------------------------------------------------------
def read_only(cmd, args):
    """True if git <cmd> <args> only shows things (no confirmation needed)."""
    if cmd in READ_ONLY:
        return True
    opts, words, i = [], [], 0
    while i < len(args):
        a = args[i]
        i += 1
        if a.startswith("-"):
            opts.append(a.split("=", 1)[0])
            if cmd in ("branch", "tag") and a in LIST_VALUES and i < len(args):
                i += 1                      # its value (branch --sort -committerdate)
        else:
            words.append(a)
    short = "".join(o[1:] for o in opts if not o.startswith("--"))
    if cmd == "stash":
        return bool(words) and words[0] in ("list", "show")
    if cmd == "remote":
        return (not words and set(opts) <= {"-v", "--verbose"}) or (bool(words) and words[0] in ("get-url", "show"))
    if cmd == "branch":
        if set(short) & set("dDmMcCuft") or set(opts) & BRANCH_CHANGES:
            return False
        return not words or bool(set(opts) & BRANCH_LISTS)
    if cmd == "tag":
        if set(opts) & TAG_CHANGES:
            return False
        return not words or bool(set(opts) & TAG_LISTS) or any(re.fullmatch(r"-n\d*", o) for o in opts)
    if cmd == "config":
        if words and words[0] in ("get", "list"):
            return True
        if set(opts) & CONFIG_WRITES or (words and words[0] in ("set", "unset", "rename-section",
                                                                 "remove-section", "edit")):
            return False
        return bool(set(opts) & CONFIG_READS) or len(words) == 1  # git config <key> reads it
    if cmd == "reflog":
        return not words or words[0] not in ("expire", "delete", "drop")
    if cmd == "worktree":
        return bool(words) and words[0] == "list"
    if cmd == "notes":
        return not words or words[0] in ("list", "show")
    if cmd == "submodule":
        return not words or words[0] in ("status", "summary")
    if cmd == "clean":
        return ("n" in short or "--dry-run" in opts) and not interactive(cmd, args)
    if cmd in ("rm", "mv"):
        return "-n" in opts or "--dry-run" in opts
    if cmd == "bisect":
        return bool(words) and words[0] in ("log", "visualize", "view")
    if cmd == "lfs":
        return bool(words) and words[0] in ("ls-files", "status", "env", "version", "locks")
    return False


def interactive(cmd, args):
    if cmd in ("mergetool", "difftool"):
        return True
    if cmd == "stash" and args and args[0] in ("list", "show"):
        return False
    if cmd == "config" and args and args[0] == "edit":
        return True
    if cmd == "notes" and args and args[0] == "edit":
        return True
    if cmd == "tag" and set(args) & {"-a", "--annotate", "-s", "--sign", "-u"} and \
            not any(a in ("-m", "-F", "--message", "--file") or a.startswith(("-m", "-F", "--message=", "--file="))
                    for a in args):
        return True  # annotated tag without a message: git opens an editor
    return bool(INTERACTIVE.get(cmd, set()) & set(args))


COMMIT_VALUE = {"message", "file", "reuse-message", "reedit-message", "fixup", "squash", "template",
                "author", "date", "cleanup", "trailer", "pathspec-from-file"}


def commit_options(args):
    """The options given to git commit, as {name: value}: short ones by letter ('m'),
    long ones by name ('reedit-message'). Option values are not mistaken for options."""
    opts, i = {}, 0
    while i < len(args):
        a = args[i]
        i += 1
        if a == "--":
            break
        if a.startswith("--"):
            name, eq, value = a[2:].partition("=")
            if not eq and name in COMMIT_VALUE and i < len(args):
                value, i = args[i], i + 1
            opts[name] = value
        elif a.startswith("-") and len(a) > 1:
            for j, ch in enumerate(a[1:], 2):
                opts[ch] = ""
                if ch in "Su":  # optional value, only in this word (-S<keyid>, -u<mode>)
                    opts[ch] = a[j:]
                    break
                if ch in "mFCct":  # takes a value: the rest of this word, or the next word
                    opts[ch] = a[j:]
                    if j == len(a) and i < len(args):
                        opts[ch], i = args[i], i + 1
                    break
    return opts


def commit_opens_editor(args):
    """Whether git commit will open an editor for the message."""
    opts = commit_options(args)
    if "no-edit" in opts:
        return False
    fixup = opts.get("fixup", "")
    if {"e", "edit", "c", "reedit-message"} & opts.keys() or fixup.startswith(("amend:", "reword:")):
        return True
    return not {"m", "message", "F", "file", "C", "reuse-message", "fixup"} & opts.keys()


def absolutize(cmd, args, start):
    """Make file options (commit -F msg.txt, archive -o out.zip) relative to where gitall
    was started, not to each repo."""
    opts = FILE_OPTS.get(cmd, set()) | {"--pathspec-from-file"}
    letters = SHORT_VALUES.get(cmd, "")

    def fix(v):
        return v if v == "-" or os.path.isabs(v) else os.path.normpath(os.path.join(start, v))
    res, i = [], 0
    while i < len(args):
        a = args[i]
        i += 1
        if a == "--":
            return res + args[i - 1:]
        if a.startswith("--"):
            name, eq, val = a.partition("=")
            if eq:
                a = f"{name}={fix(val)}" if name in opts else a
            elif (name in opts or name in LONG_VALUES) and i < len(args):
                res += [a, fix(args[i]) if name in opts else args[i]]
                i += 1
                continue
        elif a.startswith("-") and len(a) > 1:
            # a cluster of short options (-am); the first one that takes a value ends it:
            # the value is the rest of the word (-Fmsg.txt) or the next argument
            for k, ch in enumerate(a[1:], 2):
                if ch not in letters:
                    continue
                fixit = f"-{ch}" in opts
                if k < len(a):
                    a = a[:k] + (fix(a[k:]) if fixit else a[k:])
                elif i < len(args):
                    res += [a, fix(args[i]) if fixit else args[i]]
                    i += 1
                    a = None
                break
            if a is None:
                continue
        res.append(a)
    return res


def strip_yes(args):
    """Remove a trailing -y/--yes (gitall's, not git's) -> (args, found)."""
    if args and args[-1] in ("-y", "--yes") and "--" not in args[:-1] and \
            not (len(args) > 1 and args[-2] in ("-m", "--message", "-F", "--file")):
        return args[:-1], True
    return args, False


_builtins = None


def resolve_alias(cmd, args, cwd):
    """Expand git aliases -> (cmd, args, kind, chain); kind is 'shell' for !aliases."""
    global _builtins
    chain = []
    for _ in range(10):
        if cmd in COMMON:
            break
        val = git_ok(cwd, "config", "--get", f"alias.{cmd}")
        if val is None:
            break
        if _builtins is None:
            _builtins = set((git_ok(cwd, "--list-cmds=main,nohelpers") or "").split())
        if cmd in _builtins:  # git ignores aliases that hide its own commands
            break
        chain.append(f"{cmd} = {val}")
        if val.startswith("!"):
            return cmd, args, "shell", chain
        parts = shlex.split(val)
        if not parts:
            break
        cmd, args = parts[0], parts[1:] + args
    return cmd, args, "git", chain


# ---- commands --------------------------------------------------------------------------
class Blocks:
    """Each repo's output under a header. While every repo prints just one line, the lines
    are held back and printed as aligned 'repo  line' rows instead."""

    def __init__(self, prefix_from=None):
        self.pending, self.streaming, self.printed = [], False, False
        self.prefix_from = prefix_from

    def add(self, repo, res):
        o, e = res.out.splitlines() if res.out else [], res.err.splitlines() if res.err else []
        if not o and not e:
            return
        self.printed = True
        if self.prefix_from is not None:
            pre = os.path.relpath(repo.path, self.prefix_from).replace(os.sep, "/")
            pre = "" if pre == "." else pre + "/"
            for ln in o:
                out(pre + ln)
            for ln in e:
                err(f"{repo.name}: {ln}")
            return
        if not self.streaming and (len(o) == 1 or (not o and len(e) == 1)):
            # one line of output (git's warnings on stderr don't count): a row
            self.pending += [(repo, True, ln) for ln in o] + [(repo, False, ln) for ln in e]
            return
        self.flush()
        self.streaming = True
        header(repo.name)
        if o:
            out(res.out)
        if e:
            err(res.err)

    def flush(self):
        for repo, to_out, line in self.pending:
            header(repo.name)
            (out if to_out else err)(line)
        self.pending = []

    def close(self):
        if self.streaming:
            return self.flush()
        width = max((len(r.name) for r, _, _ in self.pending), default=0)
        for repo, to_out, line in self.pending:
            (out if to_out else err)(f"{BOLD(repo.name.ljust(width))}  {line}")
        self.pending = []


def sync_text(s):
    if s.error:
        return RED("error: " + s.error)
    if not s.upstream:
        return YELLOW("local only" if not s.remotes else "no upstream")
    if s.gone:
        return RED("upstream gone")
    return ", ".join([YELLOW(f"ahead {s.ahead}")] * bool(s.ahead) + [YELLOW(f"behind {s.behind}")] * bool(s.behind))


def change_text(s):
    parts = [f"{s.staged} staged"] * bool(s.staged) + [f"{s.modified} modified"] * bool(s.modified) + \
            [f"{s.untracked} untracked"] * bool(s.untracked)
    if s.conflicts:
        parts.append(RED(plural(s.conflicts, "conflict")))
    if s.stash:
        parts.append(f"{s.stash} stashed")
    text = ", ".join(parts)
    flags = [RED(s.op.upper() + " IN PROGRESS")] if s.op else []
    flags += [RED("index.lock")] * s.locked
    return "  ".join(t for t in [text, *flags] if t)


def branch_text(s):
    if s.error:
        return "?"
    if s.detached:
        return f"(detached {s.oid[:7]})" if s.oid else "(detached)"
    return s.branch + (" (no commits)" if s.unborn else "")


def repo_row(repo, width, bwidth, changes=True):
    s = repo.state
    rest = "  ".join(t for t in (sync_text(s), change_text(s) if changes else "") if t)
    return f"{repo.name:<{width}}  {branch_text(s):<{bwidth}}  {rest or GREEN('clean')}".rstrip()


class Run:
    def __init__(self, ws, repos, o, gitcmd):
        self.ws, self.repos, self.o, self.gitcmd = ws, repos, o, gitcmd
        self.failed, self.skipped, self.tally, self.code = [], [], {}, 0
        self.width = max((len(r.name) for r in repos), default=0)

    # -- bookkeeping
    def skip(self, repo, why):
        self.skipped.append((repo, why))

    def fail(self, repo, msg, retry=None):
        if "unknown switch `y'" in msg or "unknown option `yes'" in msg:
            msg += f" ({PROG}'s -y goes before the git command, or last)"
        self.failed.append((repo, msg, retry))

    def count(self, outcome, repo):
        self.tally.setdefault(outcome, []).append(repo)

    def finish(self, label=None):
        if self.skipped:
            out()
            out(YELLOW("Skipped:"))
            for r, why in self.skipped:
                out(f"  {r.name}: {why}")
        if self.failed:
            out()
            out(RED("Failed:"))
            by_msg = {}
            for r, msg, _ in self.failed:
                by_msg.setdefault(msg, []).append(r)
            for msg, rs in by_msg.items():
                if len(rs) == 1:
                    out(f"  {rs[0].name}: {msg}")
                else:
                    out(f"  {', '.join(r.name for r in rs)}: {msg}")
            by_retry = {}
            for r, _, retry in self.failed:
                if retry is not False:
                    by_retry.setdefault(tuple(retry or self.gitcmd), []).append(r)
            for argv, rs in by_retry.items():
                out(f"  retry:  {self.command_line(rs, argv)}")
        if label and len(self.repos) > 1 and not self.o.quiet:
            parts = [f"{len(v)} {k}" for k, v in self.tally.items() if v]
            parts += [f"{len(self.failed)} failed"] * bool(self.failed)
            parts += [f"{len(self.skipped)} skipped"] * bool(self.skipped)
            if parts:
                out()
                out(f"{label}: {', '.join(parts)}")
        sys.exit(1 if self.failed else self.code)

    def command_line(self, repos, argv):
        where = ["-C", quote(str(self.o.start))] if key(self.o.start) != key(Path.cwd()) else []
        return " ".join([PROG, *where, "-r", quote(",".join(r.name for r in repos)),
                         *(quote(a) for a in USER_OPTS), *(quote(a) for a in argv)])

    def plan(self):
        """The repos that are safe to change; skips the others."""
        res = []
        for r in self.repos:
            prob = r.state.problem()
            if prob and r.state.error:
                self.fail(r, prob, False)      # not a repo git can read
            elif prob:
                self.skip(r, prob)
            else:
                res.append(r)
        return res

    # -- status
    def status(self, args):
        if any(a.startswith("-") and a != "--" for a in args):
            return self.passthrough("status", args)
        paths = [a for a in args if a != "--"]
        for r in self.repos if paths else []:
            r._state = State(r.path, paths)
        bwidth = min(30, max(len(branch_text(r.state)) for r in self.repos))
        details = []
        for r in self.repos:
            s = r.state
            if s.error:
                self.fail(r, s.error)
            busy = s.dirty or not s.tracking or s.ahead or s.behind or s.op or s.locked or s.detached
            if self.o.quiet and not busy:
                continue
            out(repo_row(r, self.width, bwidth))
            if s.files:
                details.append(r)
        if self.o.quiet and not details and not self.failed and \
                not any(r.state.ahead or r.state.behind or not r.state.tracking for r in self.repos):
            out(f"all {plural(len(self.repos), 'repo')} clean")
        for r in details:
            header(r.name)
            files = r.state.files
            out("\n".join(files[:STATUS_FILES]))
            if len(files) > STATUS_FILES + 1:
                out(f"... and {len(files) - STATUS_FILES} more ({PROG} -r {quote(r.name)} status -s)")
            elif len(files) == STATUS_FILES + 1:
                out(files[-1])
        ages = [(r.state.fetched(), r) for r in self.repos if r.state.tracking]
        stale = [(a, r) for a, r in ages if a is not None and a > 3600]
        if stale:
            age, r = max(stale, key=lambda x: x[0])
            out()
            out(f"(ahead/behind is as of each repo's last fetch; oldest: {r.name}, {ago(age)}. "
                f"{PROG} fetch updates it)")
        self.finish()

    # -- commit
    def commit(self, args):
        opts = commit_options(args)
        user_dry = "dry-run" in opts
        live_commit = bool({"p", "patch", "interactive"} & opts.keys())
        anything = live_commit or bool({"amend", "allow-empty"} & opts.keys())
        repo_editor = commit_opens_editor(args)
        todo, unmatched = [], []
        for r in self.plan():
            rargs = absolutize("commit", [a.replace("{repo}", r.folder) for a in args], self.o.start)
            s = r.state
            if live_commit:
                if not (s.staged or s.modified):
                    continue
                res, text = None, "\n".join(s.files)
            else:
                dry = ["commit", "--dry-run", "--short", *[a for a in rargs if a != "--dry-run"]]
                res = git(r.path, *dry, internal=True)
                text = res.out
            if res is not None and res.rc != 0:  # nothing to commit here -- unless git reported a real error
                if "did not match any file(s) known to git" in res.err:
                    unmatched.append(first_error(res))
                    continue
                if re.search(r"^(fatal|error):", res.err, re.M):
                    self.fail(r, first_error(res))
                    continue
                if not anything:
                    continue
            todo.append((r, rargs))
            header(f"{r.name} ({branch_text(s)}{', ' + sync_text(s) if sync_text(s) else ''})")
            lines = [ln for ln in text.splitlines() if ln[:1] not in (" ", "?")]
            if lines:
                out("\n".join(lines))
        if not todo:
            if unmatched and not self.failed and len(unmatched) + len(self.skipped) == len(self.repos):
                die(f"{unmatched[0]} (in any of the repos)", 1)
            if not self.failed:
                out("nothing to commit (stage changes with  git add  first, or use  commit -a  or  "
                    "commit -- <paths>)")
            self.finish()
        out()
        if user_dry:
            out(f"(dry run: {plural(len(todo), 'repo')} would be committed)")
            self.finish()
        if repo_editor or live_commit:
            out(YELLOW("git will open an editor (or ask questions) in each repo in turn."))
        confirm(f"Commit {plural(len(todo), 'repo')}?", self.o.yes)
        for r, rargs in todo:
            if repo_editor or live_commit:
                header(r.name)
                res = git(r.path, "commit", *rargs, live=True)
            else:
                res = git(r.path, "commit", "-q", *rargs)
            if res.rc == 0:
                n = len((git_ok(r.path, "show", "--name-only", "--format=", "HEAD") or "").splitlines())
                out(f"{r.name}: {GREEN('committed')} {git_ok(r.path, 'log', '-1', '--format=%h %s')} "
                    f"({n} file(s))")
                self.count("committed", r)
            else:
                out(f"{r.name}: {RED('commit failed')}")
                if res.out or res.err:
                    out(indent("\n".join(t for t in (res.out, res.err) if t)))
                self.fail(r, first_error(res))
        self.finish("commit")

    # -- push
    def push(self, args):
        words = [a for a in args if not a.startswith("-")]
        opts = {a.split("=", 1)[0] for a in args if a.startswith("-")}
        dry = bool({"-n", "--dry-run"} & opts)
        force = bool({"-f", "--force", "--force-with-lease"} & opts) or any(w.startswith("+") for w in words)
        plain = not words and not opts & {"--tags", "--follow-tags", "--all", "--mirror", "--branches",
                                          "--delete", "-d", "--prune"}
        setup = None
        todo = []
        for r in self.plan():
            s = r.state
            if plain:
                if s.unborn:
                    self.skip(r, "no commits yet")
                    continue
                if not s.tracking:
                    if setup is None:
                        setup = git_ok(r.path, "config", "--type=bool", "push.autoSetupRemote") == "true"
                    if s.upstream or not setup:
                        why = "its upstream branch is gone" if s.upstream else "no upstream branch"
                        self.skip(r, f"{why} (to publish it: {PROG} -r {quote(r.name)} push -u origin HEAD)")
                        continue
                    header(f"{r.name} ({s.branch}, new on the remote)")
                elif not s.ahead:
                    self.count("up to date", r)
                    continue
                else:
                    header(f"{r.name} ({branch_text(s)}, {sync_text(s)})")
                    out(git_ok(r.path, "log", "--format=  %h %s", "@{u}..HEAD") or "")
            todo.append((r, args))
        if not todo:
            out("nothing to push")
            self.finish()
        if not plain:
            if any(rargs != args for _, rargs in todo):
                out("Will run:")
                for r, rargs in todo:
                    out(f"  {r.name}: git push {shown(rargs)}")
            else:
                out(f"Will run:  git push {shown(args)}")
                out(f"in: {' '.join(r.name for r, _ in todo)}")
        out()
        if not dry:
            if force:
                out(RED("This is a force push: it can overwrite commits on the remote."))
            confirm(f"{'Force-push' if force else 'Push'} {plural(len(todo), 'repo')}?", self.o.yes)
        for r, rargs in todo:
            res = git(r.path, "push", "--porcelain", *rargs)
            refs = [ln.split("\t") for ln in res.out.splitlines() if ln.count("\t") >= 2]
            if any(f == "!" for f, _, _ in refs) or (res.rc and re.search(r"rejected|fetch first", res.err)):
                why = next((summary for f, _, summary in refs if f == "!"), "")
                out(f"{r.name}: {RED('rejected')} {why.replace('[rejected]', '').strip()}".rstrip())
                self.fail(r, "rejected: the remote has newer commits (pull first, then push again)", ["pull"])
            elif res.rc:
                out(f"{r.name}: {RED('push failed')}")
                out(indent("\n".join(t for t in (res.out, res.err) if t)))
                self.fail(r, first_error(res))
            else:
                done = [(f, to, summary) for f, to, summary in refs if f != "="]
                if not done:
                    out(f"{r.name}: up to date")
                    self.count("up to date", r)
                    continue
                verb = "would push" if dry else "pushed"
                what = ", ".join(f"{re.sub(r'^refs/(heads|tags)/', '', to.split(':')[-1])} {summary}"
                                 for _, to, summary in done)
                out(f"{r.name}: {GREEN(verb)} {what}")
                self.count(verb, r)
        self.finish("push")

    # -- pull
    def pull(self, args):
        live = interactive("pull", args)
        words = [a for a in args if not a.startswith("-")]
        todo = []
        for r in self.plan():
            if not words and not r.state.tracking:
                why = "its upstream branch is gone" if r.state.upstream else "no upstream branch"
                self.skip(r, f"{why}, nothing to pull from")
                continue
            todo.append((r, args))
        rargs_of, uptodate = dict(todo), []

        def work(r):
            before = r.state.oid
            if live:
                header(r.name)
            res = git(r.path, "pull", "--no-edit", *rargs_of[r], live=live)
            after = git_ok(r.path, "rev-parse", "-q", "--verify", "HEAD")
            change = describe_change(r.path, before, after) if res.rc == 0 and after != before else None
            r.refresh()
            conflicts = (git_ok(r.path, "diff", "--name-only", "--diff-filter=U") or "").split("\n") \
                if res.rc else []
            return res, change, [c for c in conflicts if c]
        for r, (res, change, conflicts) in ((r, work(r)) for r, _ in todo):
            if res.rc == 0 and change is None:
                uptodate.append(r.name)
                self.count("up to date", r)
            elif res.rc == 0:
                out(f"{r.name:<{self.width}}  {GREEN(change)}")
                self.count("updated", r)
            else:
                header(r.name)
                out("\n".join(t for t in (res.out, res.err) if t))
                if conflicts or r.state.op:
                    files = ", ".join(conflicts) or "some files"
                    nxt = "git rebase --continue" if r.state.op == "rebase" else "git commit --no-edit"
                    self.fail(r, f"CONFLICT in {files}: fix them, then git add <files> and {nxt}", False)
                else:
                    self.fail(r, first_error(res))
        if uptodate and not self.o.quiet:
            out()
            out(f"{GREEN('up to date:')} {' '.join(uptodate)}")
        self.finish("pull")

    # -- fetch
    def fetch(self, args):
        todo = [(r, args) for r in self.repos]
        rargs_of = dict(todo)
        bwidth = min(30, max(len(branch_text(r.state)) for r in self.repos))

        def work(r):
            res = git(r.path, "fetch", *rargs_of[r])
            r.refresh()
            return res
        for r, res in ((r, work(r)) for r, _ in todo):
            if res.rc:
                out(f"{r.name}: {RED('fetch failed')}")
                out(indent(res.err or res.out))
                self.fail(r, first_error(res))
                continue
            got = fetched_summary(res.err)
            line = repo_row(r, self.width, bwidth)
            if got or not self.o.quiet or r.state.behind:
                out(line + (f"  ({got})" if got else ""))
            self.count("fetched" if got else "nothing new", r)
        self.finish("fetch")

    # -- everything else
    def passthrough(self, cmd, args, alias=None):
        live = interactive(cmd, args)
        shows = read_only(cmd, args) and alias != "shell"
        todo = [(r, absolutize(cmd, args, self.o.start)) for r in self.repos]
        if not (shows or cmd in NO_CONFIRM):
            if alias == "shell":
                out(f"'{cmd}' is a shell alias: {self.o.alias_chain[-1]}")
            out(f"Will run:  git {shown([cmd, *args])}")
            out(f"in: {' '.join(r.name for r, _ in todo)}")
            confirm("Continue?", self.o.yes)
        rargs_of = dict(todo)
        quiet_diff = cmd.startswith("diff") and bool({"--quiet", "--exit-code"} & set(args))
        matched = differs = False
        blocks = Blocks(self.o.start if self.o.prefix else None)
        if live:
            for r, _ in todo:
                header(r.name)
                res = git(r.path, cmd, *rargs_of[r], live=True)
                if res.rc:
                    self.fail(r, f"git {cmd} exited with {res.rc}")
            self.finish()

        def work(r):
            return git(r.path, cmd, *rargs_of[r], colour=not self.o.prefix)
        for r, res in ((r, work(r)) for r, _ in todo):
            blocks.add(r, res)
            # exit 1 from grep / diff --exit-code means "no match" / "has differences", not failure
            if cmd == "grep" and res.rc in (0, 1):
                matched |= res.rc == 0
            elif quiet_diff and res.rc in (0, 1):
                differs |= res.rc == 1
            elif res.rc:
                self.fail(r, first_error(res) if res.err else f"git {cmd} exited with {res.rc}")
        blocks.close()
        if cmd == "grep":
            self.code = 0 if matched else 1
        elif quiet_diff:
            self.code = 1 if differs else 0
        if not blocks.printed and not self.o.quiet and "--quiet" not in args and not self.o.prefix:
            out("(no output)" if shows else f"done in {plural(len(todo), 'repo')}")
        self.finish()


def describe_change(path, before, after):
    """'fast-forward, 3 commits, 2 files changed' and the like."""
    if not before:
        return f"pulled {plural(int(git_ok(path, 'rev-list', '--count', after) or 0), 'commit')}"
    n = int(git_ok(path, "rev-list", "--count", f"{before}..{after}") or 0)
    parents = (git_ok(path, "rev-parse", f"{after}^@") or "").split()
    if git(path, "merge-base", "--is-ancestor", before, after, internal=True).rc == 0:
        kind = "merged" if len(parents) > 1 and parents[0] == before else "fast-forward"
    else:
        kind = "rebased"
    stat = (git_ok(path, "diff", "--shortstat", before, after) or "").strip().split(",")[0]
    return ", ".join(t for t in (kind, plural(n, "commit"), stat) if t)

FETCH_LINE = re.compile(r"^ ([ +\-t*!=]) (\[[^\]]+\]|\S+)\s+\S.*?->\s+\S+")


def fetched_summary(text):
    """'2 updated, 1 new branch' from git fetch's report."""
    counts = {}
    for line in text.splitlines():
        m = FETCH_LINE.match(line)
        if not m:
            continue
        flag, what = m.group(1), m.group(2)
        kind = {" ": "updated", "+": "forced update", "-": "pruned", "t": "tag updated",
                "!": "rejected", "=": None}.get(flag)
        if flag == "*":
            kind = what.strip("[]")          # new branch / new tag / new ref
        if kind:
            counts[kind] = counts.get(kind, 0) + 1
    return ", ".join(f"{n} {k}" for k, n in counts.items())


def list_repos(ws, chosen, picked):
    where = f"in {ws.root}" + (f" (from {CONFIG})" if ws.config else "")
    total = f"{len(chosen)} of {len(ws.repos)}" if picked else f"{len(ws.repos)}"
    out(f"{total} repo(s) {where}")
    if chosen:
        width = max(len(r.name) for r in chosen)
        bwidth = min(30, max(len(branch_text(r.state)) for r in chosen))
        for r in chosen:
            out(f"{ws.repos.index(r) + 1:3}  {repo_row(r, width, bwidth)}")
    if ws.groups:
        out("groups: " + ", ".join(f"{name} ({len(rs)})" for name, rs in ws.groups.values()))
    if ws.hidden:
        out("left out: " + ", ".join(ws.hidden))
    return 0


class Options:
    def __init__(self):
        self.picks, self.drops, self.yes, self.quiet, self.prefix = [], [], False, False, False
        self.jobs, self.list, self.start, self.alias_chain = None, False, Path.cwd(), []


def usage():
    return __doc__.strip().replace("gitall", PROG).replace(".gitall", CONFIG)


def main(argv):
    o, i = Options(), 0
    USER_OPTS.clear()
    with_value = {"-r": "picks", "--repo": "picks", "-x": "drops", "--exclude": "drops",
                  "-C": "start", "-c": "config", "--config-env": "config-env"}
    while i < len(argv):
        a = argv[i]
        name, eq, value = a.partition("=") if a.startswith("--") else (a, "", "")
        if name in with_value:
            if not eq:
                if i + 1 >= len(argv):
                    die(f"{a} needs a value")
                value = argv[i + 1]
                i += 1
            what = with_value[name]
            if what in ("picks", "drops"):
                getattr(o, what).append(value)
            elif what == "start":
                o.start = (o.start / value).resolve()
                if not o.start.is_dir():
                    die(f"-C: no such directory: {o.start}")
            elif what == "config":
                USER_OPTS.extend(["-c", value])
            else:
                USER_OPTS.append(f"--config-env={value}")
        elif a in ("-y", "--yes"):
            o.yes = True
        elif a in ("-q", "--quiet"):
            o.quiet = True
        elif a in ("-l", "--list"):
            o.list = True
        elif a == "--prefix":
            o.prefix = True
        elif a in ("-h", "--help"):
            out(usage())
            return 0
        elif a in ("--version", "-v"):
            return subprocess.call(["git", "--version"])
        elif a in GIT_FLAGS:
            USER_OPTS.append(a)
        elif a in ("--no-pager", "-P"):
            pass                            # gitall never pages
        elif name in GIT_REFUSED:
            hint = "pipe the output to less instead" if a in ("-p", "--paginate") else \
                "it would point every repo at the same place"
            die(f"{a} doesn't work with {PROG}: {hint}")
        elif a.startswith("-"):
            die(f"unknown option '{a}' ({PROG}'s own options go before the git command; see {PROG} -h)")
        else:
            break
        i += 1
    if i >= len(argv) and not o.list:
        out(usage())
        return 2
    if o.list and i < len(argv):
        die(f"-l lists the repos; it doesn't run a git command (drop -l to run '{argv[i]}')")
    cmd, args = (argv[i], argv[i + 1:]) if i < len(argv) else (None, [])
    args, yes = strip_yes(args)
    o.yes |= yes

    if cmd:
        cmd, args, kind, o.alias_chain = resolve_alias(cmd, args, o.start)
        before_dashdash = args[:args.index("--")] if "--" in args else args
        if cmd in ("help", "version") or args == ["-h"] or "--help" in before_dashdash:
            if cmd == "help" and not args:
                out(usage())
                return 0
            return subprocess.call(["git", *USER_OPTS, cmd, *args], cwd=o.start)  # once, not per repo
        words = [a for a in args if not a.startswith("-")]
        once = (cmd == "clone" and words) or (cmd == "init" and words) or cmd.startswith("credential") or \
            (cmd == "config" and any(a in ("--global", "--system", "-f", "--file") or a.startswith("--file=")
                                     for a in args))
        if cmd == "init" and not words:
            die(f"init creates a new repo; give its folder: {PROG} init <folder>")
        if once:
            return subprocess.call(["git", *USER_OPTS, cmd, *args], cwd=o.start)
    else:
        kind = None

    ws = find_workspace(o.start)
    for w in ws.warnings:
        err(YELLOW(f"{PROG}: {w}"))
    if not ws.repos:
        die(f"no git repos found in {ws.root} (run it in or inside the folder that contains "
            f"your repos, or list them in a {CONFIG} file)")
    repos = select(ws, o.picks, o.drops)
    if o.list:
        return list_repos(ws, repos, bool(o.picks or o.drops))
    if not repos:
        out("no repo matches " + " ".join([*(f"-r {quote(p)}" for p in o.picks),
                                            *(f"-x {quote(d)}" for d in o.drops)]))
        return 0
    run = Run(ws, repos, o, [cmd, *args])
    if kind == "shell":
        return run.passthrough(cmd, args, alias="shell")
    handler = {"status": run.status, "commit": run.commit, "push": run.push,
               "pull": run.pull, "fetch": run.fetch}.get(cmd)
    if handler:
        return handler(args)
    return run.passthrough(cmd, args)


if __name__ == "__main__":
    try:
        code = main(sys.argv[1:])
    except KeyboardInterrupt:
        code = 130
    except PipeClosed:
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except OSError:
            pass
        code = 141 if os.name != "nt" else 1    # like git killed by SIGPIPE
    sys.exit(code)

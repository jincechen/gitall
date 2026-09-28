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
  push           only repos with unpushed commits; asks first
  pull            "already up to date" repos are listed on one line
  fetch           then shows ahead/behind per repo
  anything else   runs in every repo; repos with no output are left out; commands
                  that change things show what will run and ask first

Options (before the git command):
  -r, --repo NAME   only repos whose folder name contains NAME, or the NAME-th repo
                    in the list (1, 2, ...); repeatable
  -l, --list        list the repos (with their numbers) and exit
  -C DIR            start in DIR instead of the current directory
  -y, --yes         don't ask for confirmation (also accepted after the git command)
  -h, --help        show this help

Which repos: the folders listed in a .gitall file (in the current directory or the
nearest parent that has one); else every git repo directly inside the current
directory; else, when run inside a repo, that repo and its sibling repos.
`gitall -l` shows which repos it picked.
"""
import fnmatch
import os
import re
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

# options that make a command interactive (run attached to the terminal), per command;
# the same letters mean something else elsewhere (log -p, grep -i, grep -e)
INTERACTIVE = {
    "add": {"-p", "--patch", "-i", "--interactive", "-e", "--edit"},
    "checkout": {"-p", "--patch"}, "reset": {"-p", "--patch"}, "restore": {"-p", "--patch"},
    "stash": {"-p", "--patch"}, "clean": {"-i", "--interactive"}, "rebase": {"-i", "--interactive"},
    "merge": {"-e", "--edit"}, "revert": {"-e", "--edit"}, "cherry-pick": {"-e", "--edit"},
    "tag": {"-e", "--edit"}, "config": {"-e", "--edit"}, "am": {"-i", "--interactive"},
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
# branch/tag options whose value is the next argument (branch --sort -committerdate)
LIST_VALUES = {"--sort", "--format", "--contains", "--no-contains", "--merged", "--no-merged",
               "--points-at", "-u", "--set-upstream-to", "-m", "--message", "-F", "--file"}

STATUS_FILES = 10                       # changed files listed per repo by status

TTY = sys.stdout.isatty()
if os.name == "nt" and TTY:
    os.system("")  # enable ANSI colours in the Windows console


def _c(code):
    return lambda t: f"\033[{code}m{t}\033[0m" if TTY else t


BOLD, RED, GREEN, YELLOW = _c("1"), _c("31"), _c("32"), _c("33")


# ---- output --------------------------------------------------------------------------
def out(text=""):
    sys.stdout.buffer.write((text + "\n").encode("utf-8", "replace"))
    sys.stdout.flush()


def err(text=""):
    sys.stdout.flush()
    sys.stderr.buffer.write((text + "\n").encode("utf-8", "replace"))
    sys.stderr.flush()


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
        cmd = ["git", "-c", "core.quotePath=false", "-c", "color.ui=never"]
    else:
        cmd = ["git", "-c", "core.quotePath=false"]
        if colour and TTY:
            cmd += ["-c", "color.ui=always"]
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
        self._remotes = None
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
        self.repos, self.groups = [], {}


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
    ws.repos = [Repo(p, ws.root) for p in found]
    return ws


def read_config(root, cfg):
    ws = Workspace(root, cfg)
    known = {}
    for n, raw in enumerate(cfg.read_text(encoding="utf-8").splitlines(), 1):
        entry = raw.split("#", 1)[0].strip().rstrip("/\\")
        if not entry:
            continue
        if any(ch in entry for ch in "*?["):
            hits = [p for p in subdirs(root) if fnmatch.fnmatchcase(p.name, entry) and is_repo(p)]
        else:
            hits = [root / entry] if is_repo(root / entry) else []
        if not hits:
            die(f"{cfg}, line {n}: '{entry}' is not a git repo")
        for p in hits:
            if key(p) not in known:
                known[key(p)] = Repo(p, root)
                ws.repos.append(known[key(p)])
    return ws


def no_match(ws, term):
    listing = ", ".join(f"{i}:{r.name}" for i, r in enumerate(ws.repos, 1))
    groups = f"; groups: {', '.join(name for name, _ in ws.groups.values())}" if ws.groups else ""
    die(f"no repo matches '{term}' (repos: {listing}{groups})")


def select(ws, picks):
    """The repos chosen by -r, in list order."""
    if not picks:
        return ws.repos
    chosen = set()
    for term in picks:
        if term.isdigit():
            hits = ws.repos[int(term) - 1:int(term)] if 1 <= int(term) <= len(ws.repos) else []
        else:
            hits = [r for r in ws.repos if term.lower() in r.name.lower()]
        if not hits:
            no_match(ws, term)
        chosen.update(hits)
    return [r for r in ws.repos if r in chosen]


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


# ---- commands --------------------------------------------------------------------------
class Blocks:
    """Each repo's output under a header. While every repo prints just one line, the lines
    are held back and printed as aligned 'repo  line' rows instead."""

    def __init__(self):
        self.pending, self.streaming, self.printed = [], False, False

    def add(self, repo, res):
        o, e = res.out.splitlines() if res.out else [], res.err.splitlines() if res.err else []
        if not o and not e:
            return
        self.printed = True
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


def branch_info(s):
    branch = s.branch or "DETACHED HEAD"
    if not s.tracking:
        return f"{branch}, no upstream"
    return ", ".join([branch] + [YELLOW(f"ahead {s.ahead}")] * bool(s.ahead) +
                     [YELLOW(f"behind {s.behind}")] * bool(s.behind))


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
    def __init__(self, ws, repos, o):
        self.ws, self.repos, self.o = ws, repos, o
        self.failed, self.skipped = [], []
        self.width = max((len(r.name) for r in repos), default=0)

    # -- bookkeeping
    def skip(self, repo, why):
        self.skipped.append((repo, why))

    def fail(self, repo, msg):
        self.failed.append((repo, msg))

    def finish(self):
        for title, items, col in (("Skipped:", self.skipped, YELLOW), ("Failed:", self.failed, RED)):
            if items:
                out()
                out(col(title))
                for r, msg in items:
                    out(f"  {r.name}: {msg}")
        sys.exit(1 if self.failed else 0)

    def plan(self):
        """The repos that are safe to change; skips the others."""
        res = []
        for r in self.repos:
            prob = r.state.problem()
            if prob:
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
            out(repo_row(r, self.width, bwidth))
            if s.files:
                details.append(r)
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
        user_dry = "--dry-run" in args
        editor = commit_opens_editor(args)
        todo = []
        for r in self.plan():
            rargs = [a.replace("{repo}", r.folder) for a in args]
            dry = ["commit", "--dry-run", "--short", *[a for a in rargs if a != "--dry-run"]]
            res = git(r.path, *dry, internal=True)
            if res.rc != 0:  # nothing to commit here -- unless git reported a real error
                if re.search(r"^(fatal|error):", res.err, re.M) and \
                        "did not match any file(s) known to git" not in res.err:
                    header(r.name)
                    out(res.err)
                    self.fail(r, "git commit failed")
                continue
            todo.append((r, rargs))
            s = r.state
            header(f"{r.name} ({branch_text(s)}{', ' + sync_text(s) if sync_text(s) else ''})")
            out("\n".join(ln for ln in res.out.splitlines() if ln[:1] not in (" ", "?")))
        if not todo:
            out("nothing to commit (stage changes with  git add  first, or use  commit -a  or  commit -- <paths>)")
            self.finish()
        out()
        if user_dry:
            out(f"(dry run: {len(todo)} repo(s) would be committed)")
            self.finish()
        if editor:
            out(YELLOW("git will open an editor for the message in each repo."))
        confirm(f"Commit {len(todo)} repo(s)?", self.o.yes)
        for r, rargs in todo:
            res = git(r.path, "commit", *rargs, live=True) if editor else git(r.path, "commit", "-q", *rargs)
            if res.rc == 0:
                n = len((git_ok(r.path, "show", "--name-only", "--format=", "HEAD") or "").splitlines())
                out(f"{r.name}: {GREEN('committed')} {git_ok(r.path, 'log', '-1', '--format=%h %s')} "
                    f"({n} file(s))")
            else:
                out(f"{r.name}: {RED('commit failed')}")
                if res.out or res.err:
                    out(indent("\n".join(t for t in (res.out, res.err) if t)))
                self.fail(r, "commit failed")
        self.finish()

    # -- push
    def push(self, args):
        user_dry = "--dry-run" in args or "-n" in args
        plain = not [a for a in args if a not in ("--dry-run", "-n")]  # no remote/refspec/flags given
        todo = []
        for r in self.plan():
            s = r.state
            if plain:
                if not s.tracking:
                    self.skip(r, "no upstream branch (git push -u origin <branch>)")
                    continue
                if not s.ahead:
                    continue
                header(f"{r.name} ({branch_text(s)}, {sync_text(s)})")
                out(git_ok(r.path, "log", "--format=  %h %s", "@{u}..HEAD") or "")
            todo.append(r)
        if not todo:
            out("nothing to push")
            self.finish()
        if not user_dry:
            out()
            confirm(f"Push {len(todo)} repo(s)?", self.o.yes)
        for r in todo:
            res = git(r.path, "push", *args)
            text = "\n".join(t for t in (res.out, res.err) if t)
            if res.rc == 0:
                out(f"{r.name}: {text}" if user_dry else f"{r.name}: {GREEN('pushed')}")
            elif re.search(r"rejected|fetch first|non-fast-forward", text):
                out(f"{r.name}: {RED('rejected')}")
                self.fail(r, f"the remote has newer commits -> {PROG} -r {r.name} pull, then push again")
            else:
                out(f"{r.name}: {RED('push failed')}")
                out(indent(text))
                self.fail(r, "push failed")
        self.finish()

    # -- pull
    def pull(self, args):
        live = interactive("pull", args)
        uptodate = []
        for r in self.plan():
            before = r.state.oid
            if live:
                header(r.name)
            res = git(r.path, "pull", "--no-edit", *args, live=live)
            r.refresh()
            if res.rc == 0 and r.state.oid == before:
                uptodate.append(r.name)
                continue
            if not live:
                header(r.name)
                out("\n".join(t for t in (res.out, res.err) if t))
            if res.rc != 0:
                if r.state.op == "merge":
                    self.fail(r, "CONFLICT -- fix the files listed above, then git add <files> and "
                                 "git commit --no-edit")
                else:
                    self.fail(r, "pull failed (if local changes block it, commit them first)")
        if uptodate:
            out()
            out(f"{GREEN('up to date:')} {' '.join(uptodate)}")
        self.finish()

    # -- fetch
    def fetch(self, args):
        width = self.width + 2
        for r in self.repos:
            res = git(r.path, "fetch", *args)
            r.refresh()
            if res.rc == 0:
                out(f"{r.name:{width}}{branch_info(r.state)}")
            else:
                out(f"{r.name}: {RED('fetch failed')}")
                out(indent(res.err or res.out))
                self.fail(r, "fetch failed")
        self.finish()

    # -- everything else
    def passthrough(self, cmd, args):
        live, shows = interactive(cmd, args), read_only(cmd, args)
        if not (shows or cmd in NO_CONFIRM):
            out(f"Will run:  git {' '.join([cmd, *args])}")
            out(f"in: {' '.join(r.name for r in self.repos)}")
            confirm("Continue?", self.o.yes)
        blocks = Blocks()
        for r in self.repos:
            if live:
                header(r.name)
                res = git(r.path, cmd, *args, live=True)
            else:
                res = git(r.path, cmd, *args, colour=True)
                blocks.add(r, res)
            # exit 1 from grep / diff --exit-code means "no match" / "has differences", not failure
            if res.rc and not (res.rc == 1 and (cmd == "grep" or (cmd == "diff" and {"--exit-code", "--quiet"} & set(args)))):
                self.fail(r, f"git {cmd} exited with {res.rc}")
        blocks.close()
        if not blocks.printed and not live:
            out("(no output)" if shows else f"done in {len(self.repos)} repo(s)")
        self.finish()


def list_repos(ws):
    out(f"{len(ws.repos)} repo(s) in {ws.root}" + (f" (from {CONFIG})" if ws.config else ""))
    for n, r in enumerate(ws.repos, 1):
        out(f"{n:3}  {r.name}")
    return 0


class Options:
    def __init__(self):
        self.picks, self.yes, self.start = [], False, Path.cwd()


def usage():
    return __doc__.strip().replace("gitall", PROG).replace(".gitall", CONFIG)


def main(argv):
    o, i = Options(), 0
    while i < len(argv):
        a = argv[i]
        if a in ("-r", "--repo", "-C"):
            if i + 1 >= len(argv):
                die(f"{a} needs a value")
            if a == "-C":
                o.start = (o.start / argv[i + 1]).resolve()
                if not o.start.is_dir():
                    die(f"-C: no such directory: {o.start}")
            else:
                o.picks.append(argv[i + 1])
            i += 2
            continue
        if a.startswith("--repo="):
            o.picks.append(a.split("=", 1)[1])
        elif a in ("-y", "--yes"):
            o.yes = True
        elif a in ("-l", "--list"):
            return list_repos(find_workspace(o.start))
        elif a in ("-h", "--help"):
            out(usage())
            return 0
        elif a.startswith("-"):
            die(f"unknown option '{a}' ({PROG}'s own options go before the git command; see {PROG} -h)")
        else:
            break
        i += 1
    if i >= len(argv):
        out(usage())
        return 2
    cmd, args = argv[i], argv[i + 1:]
    if cmd in ("help", "version"):
        if cmd == "help" and not args:
            out(usage())
            return 0
        return subprocess.call(["git", cmd, *args])  # once, not once per repo
    if cmd in ("commit", "push", "pull") or cmd not in NO_CONFIRM:
        if "-y" in args or "--yes" in args:
            o.yes = True
            args = [a for a in args if a not in ("-y", "--yes")]

    ws = find_workspace(o.start)
    if not ws.repos:
        die(f"no git repos found in {ws.root} (run it in or inside the folder that contains "
            f"your repos, or list them in a {CONFIG} file)")
    run = Run(ws, select(ws, o.picks), o)
    handler = {"status": run.status, "commit": run.commit, "push": run.push,
               "pull": run.pull, "fetch": run.fetch}.get(cmd)
    if handler:
        return handler(args)
    return run.passthrough(cmd, args)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(130)

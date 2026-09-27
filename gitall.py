#!/usr/bin/env python3
"""gitall -- run git in several repositories at once.

Usage:  gitall [options] <git command> [git arguments]

The git command and its arguments are passed to git in each repo, so they mean
what they mean in git. A few commands get extra handling:

  status          compact: branch, ahead/behind, changed files; clean repos on one line
                  (pass any status option, e.g. -s, for plain git status)
  commit          previews what each repo would commit, asks once, then commits;
                  repos with nothing to commit are skipped; {repo} in the message
                  becomes the repo's folder name; --dry-run only previews;
                  without -m (or with -c, -e, --squash) git opens an editor per repo
  push           only repos with unpushed commits; asks first
  pull            "already up to date" repos are listed on one line
  fetch           then shows ahead/behind per repo
  anything else   runs in every repo, repos with no output are left out;
                  commands that change things (checkout, reset, clean, ...) ask first

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
from pathlib import Path

PROG = Path(__file__).stem              # rename the file and messages/config name follow
CONFIG = f".{PROG}"

# commands that never change anything: no confirmation needed
READ_ONLY = {
    "status", "diff", "log", "show", "shortlog", "blame", "grep", "ls-files", "ls-tree",
    "rev-parse", "rev-list", "describe", "reflog", "cat-file", "check-ignore", "name-rev",
    "count-objects", "whatchanged", "fetch", "range-diff", "for-each-ref",
}
READ_ONLY |= {"stash list", "stash show", "branch list", "remote list", "config read"}
NO_CONFIRM = READ_ONLY | {"add", "pull"}

TTY = sys.stdout.isatty()
if os.name == "nt" and TTY:
    os.system("")  # enable ANSI colours in the Windows console


def _c(code):
    return lambda t: f"\033[{code}m{t}\033[0m" if TTY else t


BOLD, RED, GREEN, YELLOW = _c("1"), _c("31"), _c("32"), _c("33")


def out(text=""):
    sys.stdout.buffer.write((text + "\n").encode("utf-8", "replace"))
    sys.stdout.flush()


def die(msg, code=2):
    sys.stdout.flush()
    sys.stderr.buffer.write((RED(f"{PROG}: {msg}") + "\n").encode("utf-8", "replace"))
    sys.stderr.flush()
    sys.exit(code)


def indent(text):
    return "    " + text.replace("\n", "\n    ")


def git(repo, *args, live=False, colour=False, stderr=True):
    """Run git in repo -> (returncode, output). stderr=False drops warnings (for parsing);
    live=True runs attached to the terminal (editors, interactive prompts)."""
    cmd = ["git", "-c", "core.quotePath=false"]
    if colour and TTY:
        cmd += ["-c", "color.ui=always"]
    cmd += ["--no-pager", *args]
    if live:
        return subprocess.call(cmd, cwd=repo), ""
    p = subprocess.run(cmd, cwd=repo, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT if stderr else subprocess.DEVNULL)
    return p.returncode, p.stdout.decode("utf-8", "replace").rstrip("\n")


def git_ok(repo, *args):
    rc, text = git(repo, *args, stderr=False)
    return text if rc == 0 else None


# ---- which repos ---------------------------------------------------------------------
def natural(name):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r"(\d+)", name)]


def is_repo(p):
    return p.is_dir() and (p / ".git").exists()


def find_repos(start):
    """Where the repos are, like git finds its repo from any subfolder:
    1. the repos listed in the nearest .gitall file (start or a parent folder);
    2. else the git repos directly inside start;
    3. else, if start is inside a repo, that repo and its sibling repos."""
    for d in [start, *start.parents]:
        cfg = d / CONFIG
        if cfg.is_file():
            repos = []
            subdirs = sorted((p for p in d.iterdir() if p.is_dir()), key=lambda p: natural(p.name))
            for n, line in enumerate(cfg.read_text(encoding="utf-8").splitlines(), 1):
                entry = line.split("#", 1)[0].strip().rstrip("/\\")
                if not entry:
                    continue
                if any(ch in entry for ch in "*?["):
                    hits = [p for p in subdirs if fnmatch.fnmatchcase(p.name, entry) and is_repo(p)]
                else:
                    hits = [d / entry] if is_repo(d / entry) else []
                if not hits:
                    die(f"{cfg}, line {n}: '{entry}' is not a git repo")
                repos += [p for p in hits if p not in repos]
            return d, repos

    def repos_in(d):
        return sorted((p for p in d.iterdir() if is_repo(p)), key=lambda p: natural(p.name))

    repos = repos_in(start)
    if repos:
        return start, repos
    top = git_ok(start, "rev-parse", "--show-toplevel")
    if top:
        parent = Path(top).resolve().parent
        return parent, repos_in(parent)
    return start, []


def select_repos(start, filters):
    root, repos = find_repos(start)
    if not repos:
        die(f"no git repos found in {root} (run it in or inside the folder that contains "
            f"your repos, or list them in a {CONFIG} file)")
    if not filters:
        return repos
    chosen = []
    for f in filters:
        if f.isdigit():
            hits = [repos[int(f) - 1]] if 1 <= int(f) <= len(repos) else []
        else:
            hits = [r for r in repos if f.lower() in r.name.lower()]
        if not hits:
            listing = ", ".join(f"{i}:{r.name}" for i, r in enumerate(repos, 1))
            die(f"no repo matches '{f}' (repos: {listing})")
        chosen += [r for r in hits if r not in chosen]
    return [r for r in repos if r in chosen]


# ---- repo state ----------------------------------------------------------------------
def git_path(repo, name):
    p = git_ok(repo, "rev-parse", "--git-path", name)
    return (repo / p) if p else repo / ".git" / name


def problem(repo):
    """Why it isn't safe to commit/pull/push here right now, or None."""
    lock = git_path(repo, "index.lock")
    if lock.exists():
        return f"index.lock exists (another git or editor running? if not, delete {lock})"
    if git_path(repo, "MERGE_HEAD").exists():
        return "merge in progress (fix conflicts and commit, or git merge --abort)"
    if git_path(repo, "rebase-merge").exists() or git_path(repo, "rebase-apply").exists():
        return "rebase in progress (git rebase --continue or --abort)"
    if git_path(repo, "CHERRY_PICK_HEAD").exists():
        return "cherry-pick in progress"
    if git_ok(repo, "symbolic-ref", "-q", "HEAD") is None:
        return "detached HEAD (git switch <branch>)"
    return None


def ahead_behind(repo):
    """(ahead, behind) vs upstream as of the last fetch, or None if no upstream."""
    if git_ok(repo, "rev-parse", "--abbrev-ref", "-q", "@{u}") is None:
        return None
    counts = git_ok(repo, "rev-list", "--left-right", "--count", "HEAD...@{u}")
    return tuple(int(x) for x in counts.split()) if counts else (0, 0)


def branch_info(repo):
    branch = git_ok(repo, "symbolic-ref", "--short", "-q", "HEAD") or "DETACHED HEAD"
    ab = ahead_behind(repo)
    if ab is None:
        return f"{branch}, no upstream"
    parts = [branch] + [YELLOW(f"ahead {ab[0]}")] * bool(ab[0]) + [YELLOW(f"behind {ab[1]}")] * bool(ab[1])
    return ", ".join(parts)


def header(text):
    out()
    out(BOLD(f"== {text}"))


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
class Run:
    def __init__(self, repos, yes):
        self.repos, self.yes = repos, yes
        self.failed, self.skipped = [], []

    def finish(self):
        for title, items, col in (("Skipped:", self.skipped, YELLOW), ("Failed:", self.failed, RED)):
            if items:
                out()
                out(col(title))
                for s in items:
                    out(f"  {s}")
        sys.exit(1 if self.failed else 0)

    def status(self, args):
        if any(a.startswith("-") and a != "--" for a in args):
            return self.passthrough("status", args)
        clean = []
        for r in self.repos:
            rc, text = git(r, "status", "--porcelain=v1", *args, stderr=False)
            if rc != 0:
                header(r.name)
                out(git(r, "status", *args)[1])
                self.failed.append(f"{r.name}: git status failed")
                continue
            info, prob = branch_info(r), problem(r)
            if not text and not prob and "ahead" not in info and "behind" not in info:
                clean.append(r.name)
                continue
            header(f"{r.name} ({info})")
            if prob:
                out(RED(f"   ! {prob}"))
            out(text or "   (no changes)")
        if clean:
            out()
            out(f"{GREEN('clean:')} {' '.join(clean)}")
        self.finish()

    def commit(self, args):
        user_dry = "--dry-run" in args
        editor = commit_opens_editor(args)
        plan = []
        for r in self.repos:
            prob = problem(r)
            if prob:
                self.skipped.append(f"{r.name}: {prob}")
                continue
            rargs = [a.replace("{repo}", r.name) for a in args]
            dry = ["commit", "--dry-run", "--short", *[a for a in rargs if a != "--dry-run"]]
            rc, text = git(r, *dry, stderr=False)
            if rc != 0:  # nothing to commit here -- unless git reported a real error
                text = git(r, *dry)[1]
                if re.search(r"^(fatal|error):", text, re.M) and "did not match any file(s) known to git" not in text:
                    header(r.name)
                    out(text)
                    self.failed.append(f"{r.name}: git commit failed")
                continue
            plan.append((r, rargs))
            header(f"{r.name} ({branch_info(r)})")
            out("\n".join(ln for ln in text.splitlines() if ln[:1] not in (" ", "?")))
        if not plan:
            out("nothing to commit (stage changes with  git add  first, or use  commit -a  or  commit -- <paths>)")
            self.finish()
        out()
        if user_dry:
            out(f"(dry run: {len(plan)} repo(s) would be committed)")
            self.finish()
        if editor:
            out(YELLOW("git will open an editor for the message in each repo."))
        confirm(f"Commit {len(plan)} repo(s)?", self.yes)
        for r, rargs in plan:
            rc, text = git(r, "commit", *rargs, live=True) if editor else git(r, "commit", "-q", *rargs)
            if rc == 0:
                n = len((git_ok(r, "show", "--name-only", "--format=", "HEAD") or "").splitlines())
                out(f"{r.name}: {GREEN('committed')} {git_ok(r, 'log', '-1', '--format=%h %s')} ({n} file(s))")
            else:
                out(f"{r.name}: {RED('commit failed')}")
                if text:
                    out(indent(text))
                self.failed.append(f"{r.name}: commit failed")
        self.finish()

    def push(self, args):
        user_dry = "--dry-run" in args or "-n" in args
        plain = not [a for a in args if a not in ("--dry-run", "-n")]  # no remote/refspec/flags given
        plan = []
        for r in self.repos:
            prob = problem(r)
            if prob:
                self.skipped.append(f"{r.name}: {prob}")
                continue
            if plain:
                ab = ahead_behind(r)
                if ab is None:
                    self.skipped.append(f"{r.name}: no upstream branch (git push -u origin <branch>)")
                    continue
                if ab[0] == 0:
                    continue
                header(f"{r.name} ({branch_info(r)})")
                out(git_ok(r, "log", "--format=  %h %s", "@{u}..HEAD") or "")
            plan.append(r)
        if not plan:
            out("nothing to push")
            self.finish()
        if not user_dry:
            out()
            confirm(f"Push {len(plan)} repo(s)?", self.yes)
        for r in plan:
            rc, text = git(r, "push", *args)
            if rc == 0:
                out(f"{r.name}: {text}" if user_dry else f"{r.name}: {GREEN('pushed')}")
            elif re.search(r"rejected|fetch first|non-fast-forward", text):
                out(f"{r.name}: {RED('rejected')}")
                self.failed.append(f"{r.name}: the remote has newer commits -> "
                                   f"{PROG} -r {r.name} pull, then push again")
            else:
                out(f"{r.name}: {RED('push failed')}")
                out(indent(text))
                self.failed.append(f"{r.name}: push failed")
        self.finish()

    def pull(self, args):
        uptodate = []
        for r in self.repos:
            prob = problem(r)
            if prob:
                self.skipped.append(f"{r.name}: {prob}")
                continue
            before = git_ok(r, "rev-parse", "-q", "HEAD")
            rc, text = git(r, "pull", "--no-edit", *args)
            if rc == 0 and git_ok(r, "rev-parse", "-q", "HEAD") == before:
                uptodate.append(r.name)
                continue
            header(r.name)
            out(text)
            if rc != 0:
                if git_path(r, "MERGE_HEAD").exists():
                    self.failed.append(f"{r.name}: CONFLICT -- fix the files listed above, then "
                                       f"git add <files> and git commit --no-edit")
                else:
                    self.failed.append(f"{r.name}: pull failed (if local changes block it, commit them first)")
        if uptodate:
            out()
            out(f"{GREEN('up to date:')} {' '.join(uptodate)}")
        self.finish()

    def fetch(self, args):
        width = max(len(r.name) for r in self.repos) + 2
        for r in self.repos:
            rc, text = git(r, "fetch", *args)
            if rc == 0:
                out(f"{r.name:{width}}{branch_info(r)}")
            else:
                out(f"{r.name}: {RED('fetch failed')}")
                out(indent(text))
                self.failed.append(f"{r.name}: fetch failed")
        self.finish()

    def passthrough(self, cmd, args):
        interactive = cmd in ("mergetool", "difftool") or \
            any(a in ("-p", "--patch", "-i", "--interactive", "-e", "--edit") for a in args)
        key = cmd
        if cmd in ("stash", "branch", "remote"):
            listing = not args or all(a in ("-a", "-r", "-v", "-vv", "--list", "--all") for a in args)
            key = f"{cmd} list" if listing and cmd != "stash" else f"{cmd} {args[0] if args else 'push'}"
        if cmd == "config" and args and args[0] in ("-l", "--list", "--get", "--get-all", "--get-regexp"):
            key = "config read"
        if key not in NO_CONFIRM:
            out(f"Will run:  git {' '.join([cmd, *args])}")
            out(f"in: {' '.join(r.name for r in self.repos)}")
            confirm("Continue?", self.yes)
        printed = False
        for r in self.repos:
            if interactive:
                header(r.name)
                rc, _ = git(r, cmd, *args, live=True)
            else:
                rc, text = git(r, cmd, *args, colour=True)
                if text:
                    header(r.name)
                    out(text)
                    printed = True
            # exit 1 from grep / diff --exit-code means "no match" / "has differences", not failure
            if rc and not (rc == 1 and (cmd == "grep" or (cmd == "diff" and {"--exit-code", "--quiet"} & set(args)))):
                self.failed.append(f"{r.name}: git {cmd} exited with {rc}")
        if not printed and not interactive:
            out("(no output)" if key in READ_ONLY else f"done in {len(self.repos)} repo(s)")
        self.finish()


def usage():
    return __doc__.strip().replace("gitall", PROG).replace(".gitall", CONFIG)


def main(argv):
    filters, yes, start = [], False, Path.cwd()
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-r", "--repo", "-C"):
            if i + 1 >= len(argv):
                die(f"{a} needs a value")
            if a == "-C":
                start = (start / argv[i + 1]).resolve()
                if not start.is_dir():
                    die(f"-C: no such directory: {start}")
            else:
                filters.append(argv[i + 1])
            i += 2
            continue
        if a.startswith("--repo="):
            filters.append(a.split("=", 1)[1])
        elif a in ("-y", "--yes"):
            yes = True
        elif a in ("-l", "--list"):
            root, repos = find_repos(start)
            cfg = root / CONFIG
            out(f"{len(repos)} repo(s) in {root}" + (f" (from {CONFIG})" if cfg.is_file() else ""))
            for n, r in enumerate(repos, 1):
                out(f"{n:3}  {r.name}")
            return 0
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
            yes = True
            args = [a for a in args if a not in ("-y", "--yes")]

    run = Run(select_repos(start, filters), yes)
    handler = {"status": run.status, "commit": run.commit, "push": run.push,
               "pull": run.pull, "fetch": run.fetch}.get(cmd)
    if handler:
        handler(args)
    else:
        run.passthrough(cmd, args)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(130)

"""gitall status: one line per repo, then the changed files."""
import os
import re
import time

import pytest

import gitall
from conftest import git, write
from helpers import make_problem


def test_all_clean(world, run):
    world.repo("A")
    world.repo("B")
    r = run("status", cwd=world.work)
    assert r.code == 0
    assert r.out.strip() == "A  main  clean\nB  main  clean"


def test_changed_repo_shows_its_files(world, run):
    world.repo("A")
    b = world.repo("B")
    write(b / "main.tex", "changed\n")
    write(b / "new.tex")
    r = run("status", cwd=world.work)
    assert "A  main  clean" in r.out
    assert "B  main  1 modified, 1 untracked" in r.out
    assert "== B\n M main.tex\n?? new.tex" in r.out
    assert "== A" not in r.out


def test_staged_counts(world, run):
    a = world.repo("A")
    write(a / "new.tex")
    write(a / "main.tex", "changed\n")
    git(a, "add", "new.tex")
    r = run("status", cwd=world.work)
    assert "A  main  1 staged, 1 modified" in r.out
    assert "A  new.tex" in r.out


def test_ahead_is_shown(world, run):
    a = world.repo("A")
    world.local_commit("A", {"x.tex": "x"})
    r = run("status", cwd=world.work)
    assert r.out.strip() == "A  main  ahead 1"
    # a damaged commit-graph makes git print "error: commit-graph file is too small" and exit 0;
    # that once got parsed as the ahead/behind counts
    write(a / ".git" / "objects" / "info" / "commit-graph", "garbage" * 8)
    r = run("status", cwd=world.work)
    assert r.code == 0 and "A  main  ahead 1" in r.out, r


def test_behind_is_shown_after_a_fetch(world, run):
    a = world.repo("A")
    world.coauthor_edit("A", {"main.tex": "edited on Overleaf\n"})
    assert run("status", cwd=world.work).out.strip() == "A  main  clean"  # status itself doesn't fetch
    git(a, "fetch", "-q")
    assert run("status", cwd=world.work).out.strip() == "A  main  behind 1"


def test_ahead_and_behind_together(world, run):
    a = world.repo("A")
    world.local_commit("A", {"local.tex": "x"})
    world.coauthor_edit("A", {"overleaf.tex": "y"})
    git(a, "fetch", "-q")
    assert "A  main  ahead 1, behind 1" in run("status", cwd=world.work).out


def test_no_upstream_is_never_shown_as_clean(world, run):
    world.repo("A", remote=False)
    b = world.repo("B")
    git(b, "checkout", "-q", "-b", "feature")
    out = run("status", cwd=world.work).out
    assert "A  main     local only" in out
    assert "B  feature  no upstream" in out
    assert "clean" not in out


def test_upstream_gone(world, run):
    a = world.repo("A")
    git(a, "checkout", "-q", "-b", "feature")
    git(a, "push", "-q", "-u", "origin", "feature")
    git(a, "push", "-q", "origin", "--delete", "feature")
    assert "A  feature  upstream gone" in run("status", cwd=world.work).out


def test_stash_count(world, run):
    a = world.repo("A")
    write(a / "main.tex", "one\n")
    git(a, "stash", "-q")
    write(a / "main.tex", "two\n")
    git(a, "stash", "-q")
    assert run("status", cwd=world.work).out.strip() == "A  main  2 stashed"


def test_stash_count_from_git_before_2_35(world, run, monkeypatch):
    # older git accepts --show-stash but prints no "# stash N" line in porcelain v2
    def old_git(cwd, *args, **kw):
        res = real_git(cwd, *args, **kw)
        if "status" in args:
            res.out = "\n".join(ln for ln in res.out.splitlines() if not ln.startswith("# stash"))
        return res
    real_git = gitall.git
    monkeypatch.setattr(gitall, "git", old_git)
    a = world.repo("A")
    for text in ("one\n", "two\n"):
        write(a / "main.tex", text)
        git(a, "stash", "-q")
    assert run("status", cwd=world.work).out.strip() == "A  main  2 stashed"
    git(a, "stash", "drop", "-q")
    git(a, "stash", "drop", "-q")
    assert run("status", cwd=world.work).out.strip() == "A  main  clean"


@pytest.mark.skipif(os.name == "nt", reason="a fake git as a shell script")
def test_git_too_old(world, run, monkeypatch, tmp_path):
    world.repo("A", remote=False)
    fake = tmp_path / "oldgit" / "git"
    write(fake, '#!/bin/sh\nif [ "$*" = version ]; then echo "git version 2.14.6"; exit 0; fi\n'
                "echo \"error: unknown option \\`no-optional-locks'\" >&2; exit 129\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake.parent}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(gitall, "_git_version", [])
    r = run("status", cwd=world.work)
    assert r.code == 2 and "gitall needs git 2.15 or newer; this is git version 2.14.6" in r.err


def test_long_file_lists_are_capped(world, run):
    a = world.repo("A")
    for i in range(11):
        write(a / f"new{i:02}.tex")
    r = run("status", cwd=world.work)
    assert r.out.count("?? new") == 11 and "more" not in r.out   # eleven are all listed
    for i in range(11, 15):
        write(a / f"new{i:02}.tex")
    r = run("status", cwd=world.work)
    assert "A  main  15 untracked" in r.out
    assert r.out.count("?? new") == 10
    assert "... and 5 more (gitall -r A status -s)" in r.out


def test_quiet_hides_repos_with_nothing_to_report(world, run):
    world.repo("A")
    b = world.repo("B")
    assert run("-q", "status", cwd=world.work).out.strip() == "all 2 repos clean"
    write(b / "main.tex", "changed\n")
    r = run("-q", "status", cwd=world.work)
    assert "A" not in r.out.split()
    assert "B  main  1 modified" in r.out


def test_stale_fetch_note(world, run):
    a = world.repo("A")
    world.repo("B")
    git(a, "fetch", "-q")
    assert "last fetch" not in run("status", cwd=world.work).out   # not after a recent fetch
    old = time.time() - 3 * 3600
    os.utime(a / ".git" / "FETCH_HEAD", (old, old))
    r = run("status", cwd=world.work)
    assert "(ahead/behind is as of each repo's last fetch; oldest: A, 3 hours ago. gitall fetch updates it)" \
        in r.out


def test_status_options_give_plain_git_status(world, run):
    world.repo("A")
    b = world.repo("B")
    write(b / "main.tex", "changed\n")
    r = run("status", "-s", cwd=world.work)
    assert r.out.strip() == "B   M main.tex"


def test_status_pathspec_still_compact(world, run):
    a = world.repo("A")
    write(a / "main.tex", "changed\n")
    write(a / "other.md")
    r = run("status", "--", "*.tex", cwd=world.work)
    assert "A  main  1 modified" in r.out
    assert " M main.tex" in r.out and "other.md" not in r.out


@pytest.mark.parametrize("kind, patterns", [
    ("merge", [r"1 conflict  MERGE IN PROGRESS", r"UU main\.tex"]),
    ("rebase", [r"REBASE IN PROGRESS"]),
    ("index.lock", [r"A  main  index\.lock"]),
    ("detached", [r"^A  \(detached [0-9a-f]{7}\)  no upstream$"]),   # not clean
])
def test_problems_are_flagged(world, run, kind, patterns):
    make_problem(world.repo("A"), kind)
    r = run("status", cwd=world.work)
    for pattern in patterns:
        assert re.search(pattern, r.out, re.M), r


def test_repo_without_commits(world, run):
    (world.work / "fresh").mkdir()
    git(world.work / "fresh", "init", "-q")
    r = run("status", cwd=world.work)
    assert r.code == 0, r
    assert "fresh  main (no commits)  local only" in r.out


def test_non_ascii_filenames_are_not_quoted(world, run):
    a = world.repo("A")
    write(a / "Übung_讲义.tex")
    r = run("status", cwd=world.work)
    assert "?? Übung_讲义.tex" in r.out


def test_columns_line_up(world, run):
    world.repo("A")
    b = world.repo("LongName")
    git(b, "checkout", "-q", "-b", "feature/x")
    lines = run("status", cwd=world.work).out.splitlines()
    assert lines[0].startswith("A         main       ")
    assert lines[1].startswith("LongName  feature/x  ")

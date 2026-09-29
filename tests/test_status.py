"""gitall status: one line per repo, then the changed files."""
import os
import re
import time

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
    world.repo("A")
    world.local_commit("A", {"x.tex": "x"})
    r = run("status", cwd=world.work)
    assert r.out.strip() == "A  main  ahead 1"


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


def test_long_file_lists_are_capped(world, run):
    a = world.repo("A")
    for i in range(15):
        write(a / f"new{i:02}.tex")
    r = run("status", cwd=world.work)
    assert "A  main  15 untracked" in r.out
    assert r.out.count("?? new") == 10
    assert "... and 5 more (gitall -r A status -s)" in r.out


def test_eleven_files_are_all_listed(world, run):
    a = world.repo("A")
    for i in range(11):
        write(a / f"new{i:02}.tex")
    r = run("status", cwd=world.work)
    assert r.out.count("?? new") == 11
    assert "more" not in r.out


def test_quiet_hides_repos_with_nothing_to_report(world, run):
    world.repo("A")
    b = world.repo("B")
    write(b / "main.tex", "changed\n")
    r = run("-q", "status", cwd=world.work)
    assert "A" not in r.out.split()
    assert "B  main  1 modified" in r.out


def test_stale_fetch_note(world, run):
    a = world.repo("A")
    world.repo("B")
    git(a, "fetch", "-q")
    old = time.time() - 3 * 3600
    os.utime(a / ".git" / "FETCH_HEAD", (old, old))
    r = run("status", cwd=world.work)
    assert "(ahead/behind is as of each repo's last fetch; oldest: A, 3 hours ago. gitall fetch updates it)" \
        in r.out


def test_no_note_after_a_recent_fetch(world, run):
    a = world.repo("A")
    git(a, "fetch", "-q")
    assert "last fetch" not in run("status", cwd=world.work).out


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


def test_merge_in_progress_is_flagged(world, run):
    a = world.repo("A")
    make_problem(a, "merge")
    r = run("status", cwd=world.work)
    assert "1 conflict  MERGE IN PROGRESS" in r.out
    assert "UU main.tex" in r.out


def test_rebase_in_progress_is_flagged(world, run):
    a = world.repo("A")
    make_problem(a, "rebase")
    assert "REBASE IN PROGRESS" in run("status", cwd=world.work).out


def test_index_lock_is_flagged(world, run):
    a = world.repo("A")
    make_problem(a, "index.lock")
    assert "A  main  index.lock" in run("status", cwd=world.work).out


def test_detached_head_is_not_clean(world, run):
    a = world.repo("A")
    make_problem(a, "detached")
    r = run("status", cwd=world.work)
    assert re.search(r"^A  \(detached [0-9a-f]{7}\)  no upstream$", r.out, re.M), r


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


def test_warnings_from_git_do_not_break_ahead_behind(world, run):
    # a damaged commit-graph makes git print "error: commit-graph file is too small" and exit 0;
    # that once got parsed as the ahead/behind counts
    a = world.repo("A")
    world.local_commit("A", {"x.tex": "x"})
    write(a / ".git" / "objects" / "info" / "commit-graph", "garbage" * 8)
    r = run("status", cwd=world.work)
    assert r.code == 0
    assert "A  main  ahead 1" in r.out

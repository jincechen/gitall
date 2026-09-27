"""gitall status: compact view, clean repos on one line."""
from conftest import git, write
from helpers import make_problem


def test_all_clean_on_one_line(world, run):
    world.repo("A")
    world.repo("B")
    r = run("status", cwd=world.work)
    assert r.code == 0
    assert r.out.strip() == "clean: A B"


def test_changed_repo_shows_its_files(world, run):
    world.repo("A")
    b = world.repo("B")
    write(b / "main.tex", "changed\n")
    write(b / "new.tex")
    r = run("status", cwd=world.work)
    assert "== B (main)" in r.out
    assert " M main.tex" in r.out and "?? new.tex" in r.out
    assert "clean: A" in r.out
    assert "== A" not in r.out


def test_ahead_is_shown(world, run):
    world.repo("A")
    world.local_commit("A", {"x.tex": "x"})
    r = run("status", cwd=world.work)
    assert "== A (main, ahead 1)" in r.out
    assert "(no changes)" in r.out


def test_behind_is_shown_after_a_fetch(world, run):
    a = world.repo("A")
    world.coauthor_edit("A", {"main.tex": "edited on Overleaf\n"})
    assert "clean: A" in run("status", cwd=world.work).out  # status itself doesn't fetch
    git(a, "fetch", "-q")
    assert "== A (main, behind 1)" in run("status", cwd=world.work).out


def test_no_upstream(world, run):
    a = world.repo("A", remote=False)
    write(a / "main.tex", "changed\n")
    assert "== A (main, no upstream)" in run("status", cwd=world.work).out


def test_status_options_give_plain_git_status(world, run):
    world.repo("A")
    b = world.repo("B")
    write(b / "main.tex", "changed\n")
    r = run("status", "-s", cwd=world.work)
    assert "== B" in r.out and " M main.tex" in r.out
    assert "clean:" not in r.out and "== A" not in r.out


def test_status_pathspec_still_compact(world, run):
    a = world.repo("A")
    write(a / "main.tex", "changed\n")
    write(a / "other.md")
    r = run("status", "--", "*.tex", cwd=world.work)
    assert " M main.tex" in r.out and "other.md" not in r.out


def test_merge_in_progress_is_flagged(world, run):
    a = world.repo("A")
    make_problem(a, "merge")
    r = run("status", cwd=world.work)
    assert "! merge in progress" in r.out
    assert "UU main.tex" in r.out


def test_detached_head_is_not_clean(world, run):
    a = world.repo("A")
    make_problem(a, "detached")
    r = run("status", cwd=world.work)
    assert "DETACHED HEAD" in r.out and "! detached HEAD" in r.out


def test_non_ascii_filenames_are_not_quoted(world, run):
    a = world.repo("A")
    write(a / "Übung_讲义.tex")
    r = run("status", cwd=world.work)
    assert "?? Übung_讲义.tex" in r.out


def test_warnings_from_git_do_not_break_ahead_behind(world, run):
    # a damaged commit-graph makes git print "error: commit-graph file is too small" and exit 0;
    # that once got parsed as the ahead/behind counts
    a = world.repo("A")
    world.local_commit("A", {"x.tex": "x"})
    write(a / ".git" / "objects" / "info" / "commit-graph", "garbage" * 8)
    r = run("status", cwd=world.work)
    assert r.code == 0
    assert "== A (main, ahead 1)" in r.out

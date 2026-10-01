"""gitall switch/checkout <branch>: preview which repos have the branch, ask once, skip the rest."""
import re

import pytest

from conftest import git, write
from helpers import make_problem


def branch(repo):
    return git(repo, "rev-parse", "--abbrev-ref", "HEAD")


def plan_line(out, label, names):
    return re.search(rf"^  {re.escape(label)}:\s+{re.escape(names)}$", out, re.M)


def four_repos(world):
    """A has a local 'feature', B has it only on its remote, C doesn't have it, D is on it."""
    a = world.repo("A")
    git(a, "branch", "feature")
    b = world.repo("B")
    other = world.coauthor("B")
    git(other, "checkout", "-q", "-b", "feature")
    git(other, "push", "-q", "-u", "origin", "feature")
    git(b, "fetch", "-q")
    c = world.repo("C")
    d = world.repo("D")
    git(d, "checkout", "-q", "-b", "feature")
    return a, b, c, d


@pytest.mark.parametrize("cmd", ["switch", "checkout"])
def test_plan_switches_tracks_and_skips(world, run, cmd):
    a, b, c, d = four_repos(world)
    r = run("-y", cmd, "feature", cwd=world.work)
    assert r.code == 0, r
    assert "switch to feature:" in r.out
    assert plan_line(r.out, "switch", "A")
    assert plan_line(r.out, "already on it", "D")
    assert plan_line(r.out, "no such branch, skipped", "C")
    assert "Skipped:\n  C: no branch 'feature'" in r.out
    assert f"{cmd}: 2 switched, 1 skipped" in r.out
    assert [branch(x) for x in (a, b, c, d)] == ["feature", "feature", "main", "feature"]
    assert git(b, "rev-parse", "--abbrev-ref", "@{u}") == "origin/feature"


def test_plan_line_for_a_new_tracking_branch(world, run):
    four_repos(world)
    r = run("-y", "switch", "feature", cwd=world.work)
    assert re.search(r"^  new branch tracking origin/feature:\s*B$", r.out, re.M), r


def test_plan_labels_are_separated_from_the_names(world, run):
    four_repos(world)
    r = run("-y", "switch", "feature", cwd=world.work)
    assert plan_line(r.out, "new branch tracking origin/feature", "B"), r


def test_switch_asks_first(world, run):
    a, b, c, d = four_repos(world)
    r = run("switch", "feature", cwd=world.work, tty=False)
    assert r.code == 2 and "not running interactively" in r.err
    assert branch(a) == "main"


def test_dirty_repos_are_marked_and_take_their_changes_along(world, run):
    a = world.repo("A")
    git(a, "branch", "feature")
    write(a / "notes.tex", "draft\n")
    git(a, "add", "notes.tex")
    r = run("-y", "switch", "feature", cwd=world.work)
    assert r.code == 0, r
    assert plan_line(r.out, "switch", "A*")
    assert "(* has uncommitted changes" in r.out
    assert branch(a) == "feature" and (a / "notes.tex").exists()


@pytest.mark.parametrize("argv", [["switch", "-c", "new"], ["checkout", "-b", "new"]])
def test_create_in_every_repo_except_where_it_exists(world, run, argv):
    a, b, c = world.repo("A"), world.repo("B"), world.repo("C")
    git(a, "branch", "new")
    r = run("-y", *argv, cwd=world.work)
    assert r.code == 0, r
    assert "create new:" in r.out and plan_line(r.out, "create", "B C")
    assert "Skipped:\n  A: already has a branch 'new'" in r.out
    assert [branch(x) for x in (a, b, c)] == ["main", "new", "new"]


def test_switch_to_each_repos_default_branch(world, run):
    a = world.repo("A")
    b = world.repo("B", remote=False)
    git(b, "branch", "-m", "main", "master")
    for repo in (a, b):
        git(repo, "checkout", "-q", "-b", "feature")
    r = run("-y", "switch", "{default}", cwd=world.work)
    assert r.code == 0, r
    assert "switch to {default}:" in r.out
    assert branch(a) == "main" and branch(b) == "master"


def test_when_no_repo_has_the_branch_git_decides(world, run):
    a, b = world.repo("A"), world.repo("B")
    for repo in (a, b):
        git(repo, "tag", "v1")
    r = run("-y", "checkout", "v1", cwd=world.work)
    assert r.code == 0, r
    assert "Will run:  git checkout v1" in r.out and "Skipped" not in r.out
    assert branch(a) == branch(b) == "HEAD"  # detached at the tag, as git does


def test_repo_mid_merge_is_skipped(world, run):
    a, b = world.repo("A"), world.repo("B")
    make_problem(a, "merge")
    git(b, "branch", "feature")
    git(a, "branch", "feature")
    r = run("-y", "switch", "feature", cwd=world.work)
    assert "Skipped:\n  A: merge in progress" in r.out
    assert branch(b) == "feature"


def test_detached_repo_can_switch(world, run):
    a = world.repo("A")
    git(a, "branch", "feature")
    make_problem(a, "detached")
    r = run("-y", "switch", "feature", cwd=world.work)
    assert r.code == 0, r
    assert branch(a) == "feature"


def test_nothing_to_do_when_all_are_on_it(world, run):
    world.repo("A")
    r = run("switch", "main", cwd=world.work, tty=False)
    assert r.code == 0
    assert plan_line(r.out, "already on it", "A") and "nothing to do" in r.out

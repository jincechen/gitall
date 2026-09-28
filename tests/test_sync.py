"""push, pull and fetch against the bare remotes standing in for Overleaf."""
from conftest import git, write
from helpers import make_problem


# ---- push --------------------------------------------------------------------------------
def test_push_only_repos_that_are_ahead(world, run):
    world.repo("A")
    world.repo("B")
    world.local_commit("A", {"x.tex": "x"}, "Local slide")
    r = run("push", "-y", cwd=world.work)
    assert r.code == 0, r
    assert "== A (main, ahead 1)" in r.out and "Local slide" in r.out
    assert "A: pushed" in r.out and "B" not in r.out
    assert world.remote_head("A") == world.head("A")


def test_nothing_to_push(world, run):
    world.repo("A")
    r = run("push", cwd=world.work, tty=False)
    assert r.code == 0
    assert "nothing to push" in r.out


def test_push_skips_repo_without_upstream(world, run):
    world.repo("A", remote=False)
    r = run("push", "-y", cwd=world.work)
    assert "A: no upstream branch" in r.out


def test_push_answer_no_pushes_nothing(world, run):
    world.repo("A")
    world.local_commit("A", {"x.tex": "x"})
    before = world.remote_head("A")
    r = run("push", cwd=world.work, answer="n")
    assert r.code == 1 and "aborted" in r.out
    assert world.remote_head("A") == before


def test_push_dry_run_does_not_ask_or_push(world, run):
    world.repo("A")
    world.local_commit("A", {"x.tex": "x"})
    before = world.remote_head("A")
    r = run("push", "--dry-run", cwd=world.work, tty=False)
    assert r.code == 0, r
    assert "A: " in r.out and "pushed" not in r.out
    assert world.remote_head("A") == before


def test_push_with_explicit_refspec_goes_to_every_repo(world, run):
    world.repo("A")
    world.repo("B")
    world.local_commit("A", {"x.tex": "x"})
    r = run("push", "origin", "main", "-y", cwd=world.work)
    assert "A: pushed" in r.out and "B: pushed" in r.out
    assert world.remote_head("A") == world.head("A")


def test_rejected_push_suggests_pull_and_others_still_push(world, run):
    world.repo("A")
    world.repo("B")
    world.local_commit("A", {"local.tex": "x"})
    world.local_commit("B", {"local.tex": "x"})
    world.coauthor_edit("A", {"overleaf.tex": "y"})
    r = run("push", "-y", cwd=world.work)
    assert r.code == 1
    assert "A: rejected" in r.out and "B: pushed" in r.out
    assert "A: the remote has newer commits -> gitall -r A pull, then push again" in r.out


def test_rejected_then_pull_then_push(world, run):
    # the everyday Overleaf cycle: a co-author edited online while you edited locally
    world.repo("A")
    world.local_commit("A", {"local.tex": "x"})
    world.coauthor_edit("A", {"overleaf.tex": "y"})
    assert run("push", "-y", cwd=world.work).code == 1
    r = run("pull", cwd=world.work, tty=False)
    assert r.code == 0, r
    assert (world.work / "A" / "overleaf.tex").exists()
    r = run("push", "-y", cwd=world.work)
    assert r.code == 0 and "A: pushed" in r.out
    assert world.remote_head("A") == world.head("A")


def test_push_skips_detached_head(world, run):
    a = world.repo("A")
    world.local_commit("A", {"x.tex": "x"})
    make_problem(a, "detached")
    r = run("push", "-y", cwd=world.work)
    assert "Skipped:\n  A: detached HEAD" in r.out


def test_push_survives_git_warnings(world, run):
    a = world.repo("A")
    world.local_commit("A", {"x.tex": "x"})
    write(a / ".git" / "objects" / "info" / "commit-graph", "garbage" * 8)
    r = run("push", "-y", cwd=world.work)
    assert r.code == 0, r
    assert "A: pushed" in r.out


# ---- pull --------------------------------------------------------------------------------
def test_pull_brings_in_overleaf_edits_and_lists_up_to_date_repos(world, run):
    world.repo("A")
    world.repo("B")
    world.repo("C")
    world.coauthor_edit("B", {"main.tex": "edited on Overleaf\n"})
    r = run("pull", cwd=world.work, tty=False)  # pull doesn't ask
    assert r.code == 0, r
    assert "== B" in r.out and "up to date: A C" in r.out
    assert world.head("B") == world.remote_head("B")


def test_pull_conflict_is_reported_and_then_blocks_commit(world, run):
    a = world.repo("A")
    world.repo("B")
    world.local_commit("A", {"main.tex": "local line\n"})
    world.coauthor_edit("A", {"main.tex": "overleaf line\n"})
    r = run("pull", cwd=world.work)
    assert r.code == 1
    assert "CONFLICT" in r.out
    assert "A: CONFLICT -- fix the files listed above" in r.out
    assert (a / ".git" / "MERGE_HEAD").exists()
    assert "MERGE IN PROGRESS" in run("status", cwd=world.work).out
    r = run("commit", "-am", "x", "-y", cwd=world.work)
    assert "A: merge in progress" in r.out


def test_pull_blocked_by_local_changes(world, run):
    a = world.repo("A")
    world.coauthor_edit("A", {"main.tex": "overleaf\n"})
    write(a / "main.tex", "uncommitted local\n")
    r = run("pull", cwd=world.work)
    assert r.code == 1
    assert "A: pull failed (if local changes block it, commit them first)" in r.out
    assert not (a / ".git" / "MERGE_HEAD").exists()


def test_pull_skips_unsafe_repo(world, run):
    a = world.repo("A")
    world.coauthor_edit("A", {"main.tex": "overleaf\n"})
    make_problem(a, "index.lock")
    before = world.head("A")
    r = run("pull", cwd=world.work)
    assert "Skipped:\n  A: index.lock exists" in r.out
    assert world.head("A") == before


# ---- fetch -------------------------------------------------------------------------------
def test_fetch_shows_ahead_and_behind(world, run):
    world.repo("A")
    world.repo("Bee")
    world.coauthor_edit("A", {"main.tex": "overleaf\n"})
    world.local_commit("Bee", {"x.tex": "x"})
    r = run("fetch", cwd=world.work, tty=False)
    assert r.code == 0, r
    assert "A    main, behind 1" in r.out
    assert "Bee  main, ahead 1" in r.out


def test_fetch_failure_does_not_stop_the_others(world, run):
    world.repo("A")
    b = world.repo("B")
    world.coauthor_edit("A", {"main.tex": "overleaf\n"})
    git(b, "remote", "set-url", "origin", str(world.root / "gone.git"))
    r = run("fetch", cwd=world.work)
    assert r.code == 1
    assert "behind 1" in r.out
    assert "B: fetch failed" in r.out and "Failed:\n  B: fetch failed" in r.out

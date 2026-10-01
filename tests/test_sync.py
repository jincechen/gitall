"""push, pull and fetch against the bare remotes standing in for Overleaf."""
import re


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
    assert re.search(r"^A: pushed main [0-9a-f]+\.\.[0-9a-f]+$", r.out, re.M), r
    assert "== B" not in r.out and "B:" not in r.out
    assert "push: 1 up to date, 1 pushed" in r.out
    assert world.remote_head("A") == world.head("A")


def test_nothing_to_push(world, run):
    world.repo("A")
    r = run("push", cwd=world.work, tty=False)
    assert r.code == 0
    assert "nothing to push" in r.out


def test_push_skips_repo_without_upstream(world, run):
    world.repo("A", remote=False)
    r = run("push", "-y", cwd=world.work)
    assert "A: no upstream branch (to publish it: gitall -r A push -u origin HEAD)" in r.out


def test_push_skips_repo_whose_upstream_is_gone(world, run):
    a = world.repo("A")
    git(a, "checkout", "-q", "-b", "feature")
    git(a, "push", "-q", "-u", "origin", "feature")
    git(a, "push", "-q", "origin", "--delete", "feature")
    world.local_commit("A", {"x.tex": "x"})
    r = run("push", "-y", cwd=world.work)
    assert "A: its upstream branch is gone (to publish it: gitall -r A push -u origin HEAD)" in r.out


def test_push_publishes_new_branches_with_auto_setup_remote(world, run):
    a = world.repo("A")
    git(a, "config", "push.autoSetupRemote", "true")
    git(a, "checkout", "-q", "-b", "feature")
    world.local_commit("A", {"x.tex": "x"})
    r = run("push", "-y", cwd=world.work)
    assert r.code == 0, r
    assert "== A (feature, new on the remote)" in r.out
    assert "A: pushed feature [new branch]" in r.out
    assert git(world.remotes / "A.git", "rev-parse", "feature") == world.head("A")
    assert git(a, "rev-parse", "--abbrev-ref", "@{u}") == "origin/feature"


def test_push_answer_no_pushes_nothing(world, run):
    world.repo("A")
    world.local_commit("A", {"x.tex": "x"})
    before = world.remote_head("A")
    r = run("push", cwd=world.work, answer="n")
    assert r.code == 1 and "Push 1 repo? [y/N]" in r.out and "aborted" in r.out
    assert world.remote_head("A") == before


def test_push_dry_run_does_not_ask_or_push(world, run):
    world.repo("A")
    world.local_commit("A", {"x.tex": "x"})
    before = world.remote_head("A")
    r = run("push", "--dry-run", cwd=world.work, tty=False)
    assert r.code == 0, r
    assert "A: would push main" in r.out
    assert world.remote_head("A") == before


def test_force_push_warns_and_asks_differently(world, run):
    world.repo("A")
    world.local_commit("A", {"x.tex": "x"})
    before = world.remote_head("A")
    r = run("push", "--force-with-lease", cwd=world.work, answer="n")
    assert "This is a force push: it can overwrite commits on the remote." in r.out
    assert "Force-push 1 repo? [y/N]" in r.out
    assert world.remote_head("A") == before


def test_push_with_explicit_refspec_goes_to_every_repo(world, run):
    world.repo("A")
    world.repo("B")
    world.local_commit("A", {"x.tex": "x"})
    r = run("push", "origin", "main", "-y", cwd=world.work)
    assert "Will run:  git push origin main\nin: A B" in r.out
    assert "A: pushed main" in r.out and "B: up to date" in r.out
    assert world.remote_head("A") == world.head("A")


def test_push_tags_goes_to_every_repo(world, run):
    a = world.repo("A")
    world.repo("B")
    git(a, "tag", "v1")
    r = run("push", "--tags", "-y", cwd=world.work)
    assert r.code == 0, r
    assert "in: A B" in r.out
    assert "A: pushed v1 [new tag]" in r.out and "B: up to date" in r.out
    assert git(world.remotes / "A.git", "tag") == "v1"


def test_push_with_placeholder_shows_each_command(world, run):
    world.repo("A")
    world.repo("B")
    r = run("push", "origin", "main:{repo}-copy", "-y", cwd=world.work)
    assert r.code == 0, r
    assert "Will run:\n  A: git push origin main:A-copy\n  B: git push origin main:B-copy" in r.out
    assert git(world.remotes / "B.git", "branch", "--list", "B-copy").strip() == "B-copy"


def test_rejected_push_suggests_pull_and_others_still_push(world, run):
    world.repo("A")
    world.repo("B")
    world.local_commit("A", {"local.tex": "x"})
    world.local_commit("B", {"local.tex": "x"})
    world.coauthor_edit("A", {"overleaf.tex": "y"})
    r = run("push", "-y", cwd=world.work)
    assert r.code == 1
    assert "A: rejected (fetch first)" in r.out and "B: pushed main" in r.out
    assert "Failed:\n  A: rejected: the remote has newer commits (pull first, then push again)" in r.out
    assert "  retry:  gitall -r A pull" in r.out
    assert "push: 1 pushed, 1 failed" in r.out


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
    assert r.code == 0 and "A: pushed main" in r.out
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
    assert "B  fast-forward, 1 commit, 1 file changed" in r.out
    assert "up to date: A C" in r.out
    assert "pull: 2 up to date, 1 updated" in r.out
    assert world.head("B") == world.remote_head("B")


def test_pull_merge(world, run):
    world.repo("A")
    world.local_commit("A", {"local.tex": "x"})
    world.coauthor_edit("A", {"overleaf.tex": "y"})
    r = run("pull", cwd=world.work)
    assert r.code == 0, r
    assert "A  merged, 2 commits, 1 file changed" in r.out


def test_pull_rebase(world, run):
    world.repo("A")
    world.local_commit("A", {"local.tex": "x"})
    world.coauthor_edit("A", {"overleaf.tex": "y"})
    r = run("pull", "--rebase", cwd=world.work)
    assert r.code == 0, r
    assert re.search(r"^A  rebased, ", r.out, re.M), r
    assert git(world.work / "A", "rev-list", "--count", "HEAD") == "3"


def test_pull_skips_repos_without_upstream(world, run):
    world.repo("A", remote=False)
    b = world.repo("B")
    git(b, "checkout", "-q", "-b", "feature")
    r = run("pull", cwd=world.work)
    assert r.code == 0, r
    assert "A: no upstream branch, nothing to pull from" in r.out
    assert "B: no upstream branch, nothing to pull from" in r.out


def test_pull_conflict_is_reported_and_then_blocks_commit(world, run):
    a = world.repo("A")
    world.repo("B")
    world.local_commit("A", {"main.tex": "local line\n"})
    world.coauthor_edit("A", {"main.tex": "overleaf line\n"})
    r = run("pull", cwd=world.work)
    assert r.code == 1
    assert "CONFLICT (content)" in r.out
    assert "A: CONFLICT in main.tex: fix them, then git add <files> and git commit --no-edit" in r.out
    assert "retry" not in r.out
    assert (a / ".git" / "MERGE_HEAD").exists()
    assert "MERGE IN PROGRESS" in run("status", cwd=world.work).out
    r = run("commit", "-am", "x", "-y", cwd=world.work)
    assert "A: merge in progress" in r.out


def test_pull_rebase_conflict_says_rebase_continue(world, run):
    world.repo("A")
    world.local_commit("A", {"main.tex": "local line\n"})
    world.coauthor_edit("A", {"main.tex": "overleaf line\n"})
    r = run("pull", "--rebase", cwd=world.work)
    assert r.code == 1
    assert "A: CONFLICT in main.tex: fix them, then git add <files> and git rebase --continue" in r.out


def test_pull_blocked_by_local_changes(world, run):
    a = world.repo("A")
    world.coauthor_edit("A", {"main.tex": "overleaf\n"})
    write(a / "main.tex", "uncommitted local\n")
    r = run("pull", cwd=world.work)
    assert r.code == 1
    assert "A: error: Your local changes to the following files would be overwritten by merge:" in r.out
    assert "retry:  gitall -r A pull" in r.out
    assert not (a / ".git" / "MERGE_HEAD").exists()


def test_pull_skips_unsafe_repo(world, run):
    a = world.repo("A")
    world.coauthor_edit("A", {"main.tex": "overleaf\n"})
    make_problem(a, "index.lock")
    before = world.head("A")
    r = run("pull", cwd=world.work)
    assert "Skipped:\n  A: index.lock exists" in r.out
    assert world.head("A") == before


def test_quiet_pull_leaves_out_up_to_date_repos(world, run):
    world.repo("A")
    world.repo("B")
    world.coauthor_edit("B", {"main.tex": "edited\n"})
    r = run("-q", "pull", cwd=world.work)
    assert "B  fast-forward" in r.out
    assert "up to date" not in r.out and "pull:" not in r.out


# ---- fetch -------------------------------------------------------------------------------
def test_fetch_shows_ahead_and_behind(world, run):
    world.repo("A")
    world.repo("Bee")
    world.coauthor_edit("A", {"main.tex": "overleaf\n"})
    world.local_commit("Bee", {"x.tex": "x"})
    r = run("fetch", cwd=world.work, tty=False)
    assert r.code == 0, r
    assert "A    main  behind 1  (1 updated)" in r.out
    assert "Bee  main  ahead 1" in r.out
    assert "fetch: 1 fetched, 1 nothing new" in r.out


def test_fetch_reports_new_branches_and_tags(world, run):
    world.repo("A")
    c = world.coauthor("A")
    git(c, "branch", "feature")
    git(c, "tag", "v1")
    git(c, "push", "-q", "origin", "feature", "v1")
    r = run("fetch", cwd=world.work)
    assert "(1 new branch, 1 new tag)" in r.out


def test_fetch_prune_reports_pruned_branches(world, run):
    a = world.repo("A")
    git(a, "push", "-q", "origin", "main:old")
    git(world.remotes / "A.git", "branch", "-D", "old")
    r = run("fetch", "--prune", cwd=world.work)
    assert r.code == 0, r
    assert "(1 pruned)" in r.out
    assert "origin/old" not in git(a, "branch", "-r")


def test_fetch_does_not_call_a_changed_repo_clean(world, run):
    a = world.repo("A")
    write(a / "main.tex", "changed\n")
    r = run("fetch", cwd=world.work)
    assert "clean" not in r.out


def test_fetch_failure_does_not_stop_the_others(world, run):
    world.repo("A")
    b = world.repo("B")
    world.coauthor_edit("A", {"main.tex": "overleaf\n"})
    git(b, "remote", "set-url", "origin", str(world.root / "gone.git"))
    r = run("fetch", cwd=world.work)
    assert r.code == 1
    assert "A  main  behind 1  (1 updated)" in r.out
    assert "B: fetch failed" in r.out
    assert re.search(r"Failed:\n  B: fatal: .*gone\.git", r.out), r
    assert "retry:  gitall -r B fetch" in r.out
    assert "fetch: 1 fetched, 1 failed" in r.out

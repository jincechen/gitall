"""One command, adapted per repo: placeholders, GITALL_* variables, git aliases."""
from conftest import git, write
from helpers import make_problem


def test_shell_alias_asks_first(world, run):
    world.repo("A")
    r = run("-c", "alias.hi=!echo hi", "hi", cwd=world.work, tty=False)
    assert r.code == 2
    assert "'hi' is a shell alias: hi = !echo hi" in r.out and "Will run:  git hi" in r.out


# ---- git aliases ----------------------------------------------------------------------------
def test_alias_for_commit_gets_the_preview_and_safety_skips(world, run):
    a, b = world.repo("A"), world.repo("B")
    write(a / "new.tex")
    git(a, "add", "new.tex")
    make_problem(b, "merge")
    r = run("-c", "alias.ci=commit", "ci", "-m", "Via alias", "-y", cwd=world.work)
    assert r.code == 0, r
    assert "== A (main)" in r.out and "A  new.tex" in r.out
    assert "Skipped:\n  B: merge in progress" in r.out
    assert git(a, "log", "-1", "--format=%s") == "Via alias"


def test_alias_with_options_and_alias_of_an_alias(world, run):
    world.repo("A")
    r = run("-c", "alias.last=log -1 --format=%s", "-c", "alias.l2=last", "l2", cwd=world.work)
    assert r.code == 0, r
    assert r.out.strip() == "A  initial"


def test_alias_with_a_builtins_name_is_ignored_like_git_does(world, run):
    world.repo("A")
    r = run("-y", "-c", "alias.prune=log --format=%s", "prune", cwd=world.work)
    assert r.code == 0, r
    assert "initial" not in r.out and "done in 1 repo" in r.out

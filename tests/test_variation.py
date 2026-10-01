"""One command, adapted per repo: placeholders, GITALL_* variables, git aliases."""
from conftest import git, write
from helpers import make_problem


def tags(repo):
    return git(repo, "tag").split()


# ---- placeholders -------------------------------------------------------------------------
def test_placeholders_are_expanded_in_the_preview(world, run):
    world.repo("A")
    world.repo("B")
    r = run("tag", "{repo}-v1", cwd=world.work, tty=False)
    assert r.code == 2
    assert "Will run:\n  A: git tag A-v1\n  B: git tag B-v1" in r.out
    r = run("-y", "tag", "{repo}-v1", cwd=world.work)
    assert r.code == 0, r
    assert tags(world.work / "A") == ["A-v1"] and tags(world.work / "B") == ["B-v1"]


def test_path_placeholder(world, run):
    world.repo("A")
    world.repo("C", where=world.work / "nested")
    write(world.work / ".gitall", "A\nnested/C\n")
    r = run("-y", "tag", "at/{path}", cwd=world.work)
    assert r.code == 0, r
    assert tags(world.work / "A") == ["at/A"]
    assert tags(world.work / "nested" / "C") == ["at/nested/C"]


def test_branch_placeholder_skips_detached_repos(world, run):
    a, b, d = world.repo("A"), world.repo("B"), world.repo("D")
    git(b, "checkout", "-q", "-b", "feature")
    make_problem(d, "detached")
    r = run("-y", "tag", "at-{branch}", cwd=world.work)
    assert r.code == 0, r
    assert tags(a) == ["at-main"] and tags(b) == ["at-feature"] and tags(d) == []
    assert "Skipped:\n  D: detached HEAD, so no {branch}" in r.out


def test_upstream_placeholder_skips_repos_without_one(world, run):
    world.repo("A")
    world.repo("B", remote=False)
    r = run("log", "-1", "--format=%s", "{upstream}", cwd=world.work, tty=False)
    assert r.code == 0, r
    assert "A  initial" in r.out
    assert "Skipped:\n  B: no upstream branch, so no {upstream}" in r.out


def test_gits_own_brace_syntax_is_left_alone(world, run):
    world.repo("A")
    r = run("rev-parse", "--abbrev-ref", "@{upstream}", cwd=world.work)
    assert r.out.strip() == "A  origin/main"
    r = run("log", "-1", "--format=%s {foo}", cwd=world.work)
    assert r.out.strip() == "A  initial {foo}"


# ---- GITALL_* variables, for aliases and hooks ------------------------------------------------
def test_variables_reach_shell_aliases(world, run):
    a, b = world.repo("A"), world.repo("B")
    alias = "alias.where=!printf '%s %s/%s %s\\n' \"$GITALL_REPO\" \"$GITALL_I\" \"$GITALL_COUNT\" \"$GITALL_PATH\""
    r = run("-y", "-c", alias, "where", cwd=world.work)
    assert r.code == 0, r
    lines = r.out.strip().splitlines()[-2:]   # after the shell-alias preview
    assert lines[0].split()[:3] == ["A", "A", "1/2"] and str(a) in lines[0]
    assert lines[1].split()[:3] == ["B", "B", "2/2"] and str(b) in lines[1]


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

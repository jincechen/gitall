"""Every other git command: run in each repo, quiet repos left out, changes confirmed first."""
from conftest import git, write


def headers(result):
    return [ln[3:] for ln in result.out.splitlines() if ln.startswith("== ")]


def test_output_per_repo(world, run):
    world.repo("A")
    world.repo("B")
    r = run("log", "-1", "--format=%s", cwd=world.work)
    assert r.code == 0
    assert r.out.strip() == "== A\ninitial\n\n== B\ninitial"


def test_repos_without_output_are_left_out(world, run):
    world.repo("A")
    world.repo("B")
    world.local_commit("B", {"x.tex": "x"}, "Unpushed")
    r = run("log", "--format=%s", "@{u}..HEAD", cwd=world.work)
    assert headers(r) == ["B"]


def test_no_output_at_all(world, run):
    world.repo("A")
    r = run("diff", cwd=world.work)
    assert r.out.strip() == "(no output)"


def test_changes_need_confirmation(world, run):
    world.repo("A")
    world.repo("B")
    r = run("tag", "v1", cwd=world.work, tty=False)
    assert r.code == 2
    assert "Will run:  git tag v1\nin: A B" in r.out
    assert git(world.work / "A", "tag") == ""


def test_changes_with_yes(world, run):
    world.repo("A")
    world.repo("B")
    r = run("-y", "tag", "v1", cwd=world.work)
    assert r.code == 0
    assert "done in 2 repo(s)" in r.out
    assert git(world.work / "B", "tag") == "v1"


def test_add_does_not_ask(world, run):
    a = world.repo("A")
    write(a / "new.tex")
    r = run("add", "-A", cwd=world.work, tty=False)
    assert r.code == 0
    assert "A  new.tex" in git(a, "status", "--porcelain")


def test_grep_without_match_and_diff_exit_code_are_not_failures(world, run):
    a = world.repo("A")
    world.repo("B")
    write(a / "main.tex", "changed\n")
    r = run("grep", "no-such-text", cwd=world.work)
    assert r.code == 0 and "(no output)" in r.out
    r = run("diff", "--exit-code", "--stat", cwd=world.work)
    assert r.code == 0 and "Failed" not in r.out


def test_one_failure_does_not_stop_the_others(world, run):
    world.repo("A")
    b = world.repo("B")
    git(b, "branch", "feature")
    r = run("rev-parse", "--verify", "-q", "feature", cwd=world.work)
    assert r.code == 1
    assert headers(r) == ["B"]
    assert "Failed:\n  A: git rev-parse exited with 1" in r.out


def test_branch_config_stash_changes_ask(world, run):
    a = world.repo("A")
    git(a, "branch", "old")
    write(a / "main.tex", "changed\n")
    for argv in (["branch", "-d", "old"], ["branch", "new"], ["config", "user.name", "X"],
                 ["stash"], ["stash", "pop"], ["remote", "remove", "origin"]):
        r = run(*argv, cwd=world.work, tty=False)
        assert r.code == 2 and "Will run" in r.out, argv
    assert "old" in git(a, "branch")


def test_stash_show_patch_does_not_ask(world, run):
    a = world.repo("A")
    write(a / "main.tex", "stashed\n")
    git(a, "stash", "-q")
    r = run("stash", "show", "-p", cwd=world.work, tty=False)
    assert r.code == 0 and headers(r) == ["A"] and "+stashed" in r.out


def test_non_ascii_filenames_are_not_quoted(world, run):
    world.repo("A", {"Übung_讲义.tex": "x\n"})
    r = run("ls-files", cwd=world.work)
    assert "Übung_讲义.tex" in r.out and "\\" not in r.out

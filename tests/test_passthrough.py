"""Every other git command: run in each repo, quiet repos left out, changes confirmed first."""
from conftest import git, write


def headers(result):
    return [ln[3:] for ln in result.out.splitlines() if ln.startswith("== ")]


def shown_repos(result):
    """The repos that printed something: block headers, or the names starting compact rows."""
    if headers(result):
        return headers(result)
    return [ln.split()[0] for ln in result.out.splitlines() if ln.strip()]


def test_one_line_per_repo_prints_aligned_rows(world, run):
    world.repo("A")
    world.repo("Bee")
    r = run("log", "-1", "--format=%s", cwd=world.work)
    assert r.code == 0
    assert r.out.strip() == "A    initial\nBee  initial"


def test_longer_output_prints_blocks(world, run):
    world.repo("A")
    world.repo("B")
    world.local_commit("B", {"x.tex": "x"}, "second")
    r = run("log", "-2", "--format=%s", cwd=world.work)
    assert r.out.strip() == "== A\ninitial\n\n== B\nsecond\ninitial"


def test_repos_without_output_are_left_out(world, run):
    world.repo("A")
    world.repo("B")
    world.local_commit("B", {"x.tex": "x"}, "Unpushed")
    r = run("log", "--format=%s", "@{u}..HEAD", cwd=world.work)
    assert r.out.strip() == "B  Unpushed"


def test_git_messages_go_to_stderr(world, run):
    world.repo("A")
    world.repo("B")
    r = run("-y", "branch", "-d", "no-such-branch", cwd=world.work)
    assert r.code == 1
    assert "error: branch 'no-such-branch' not found" in r.err
    assert "A, B: error: branch 'no-such-branch' not found" in r.out  # same error, grouped


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
    assert "done in 2 repos" in r.out
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
    assert shown_repos(r)[:1] == ["B"]
    assert "Failed:\n  A: git rev-parse exited with 1" in r.out
    assert "retry:  gitall -r A rev-parse --verify -q feature" in r.out


def test_changes_ask(world, run):
    a = world.repo("A")
    git(a, "branch", "old")
    write(a / "main.tex", "changed\n")
    for argv in (["branch", "-d", "old"], ["branch", "new"], ["config", "user.name", "X"],
                 ["stash"], ["stash", "pop"], ["remote", "remove", "origin"],
                 ["reflog", "expire", "--expire=now", "--all"], ["reflog", "delete", "HEAD@{0}"],
                 ["tag", "v1"], ["clean", "-fd"], ["worktree", "prune"]):
        r = run(*argv, cwd=world.work, tty=False)
        assert r.code == 2 and "Will run" in r.out, argv
    assert "old" in git(a, "branch")
    assert git(a, "reflog") != ""


def test_reflog_listing_does_not_ask(world, run):
    world.repo("A")
    for argv in (["reflog"], ["reflog", "-1"], ["reflog", "show", "-1"]):
        r = run(*argv, cwd=world.work, tty=False)
        assert r.code == 0 and "Will run" not in r.out, argv


def test_read_only_commands_do_not_ask(world, run):
    a = world.repo("A")
    git(a, "tag", "v1")
    write(a / "junk.tmp")
    for argv in (["branch", "--show-current"], ["branch", "-a"], ["branch", "-vv"],
                 ["remote", "-v"], ["remote", "get-url", "origin"],
                 ["config", "user.name"], ["config", "--get", "user.name"], ["config", "-l"],
                 ["stash", "list"], ["tag"], ["tag", "-l"], ["tag", "-n"],
                 ["show-ref"], ["ls-remote", "origin"], ["merge-base", "HEAD", "HEAD"],
                 ["worktree", "list"], ["clean", "-n"], ["rm", "-n", "main.tex"]):
        r = run(*argv, cwd=world.work, tty=False)
        assert r.code == 0, (argv, r)
        assert "Will run" not in r.out, argv
    assert (a / "junk.tmp").exists() and (a / "main.tex").exists()
    assert "main" in run("branch", "--show-current", cwd=world.work).out
    assert "Test" in run("config", "user.name", cwd=world.work).out


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


def test_log_patch_is_captured_not_interactive(world, run):
    world.repo("A")
    world.repo("B")
    world.local_commit("B", {"x.tex": "slide\n"})
    r = run("log", "-p", "@{u}..HEAD", cwd=world.work)
    assert headers(r) == ["B"]
    assert "+slide" in r.out


def test_grep_ignore_case_and_pattern_are_captured(world, run):
    world.repo("A", {"main.tex": "Hello\n"})
    world.repo("B")
    assert shown_repos(run("grep", "-i", "hello", cwd=world.work)) == ["A"]
    assert shown_repos(run("grep", "-e", "Hello", cwd=world.work)) == ["A"]

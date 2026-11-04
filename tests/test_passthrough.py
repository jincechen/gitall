"""Every other git command: run in each repo, quiet repos left out, changes confirmed first."""
import os
import shlex
import shutil
import subprocess
import zipfile

import pytest

import gitall
from conftest import git, write
from gitall import quote, width
from helpers import make_problem


def headers(result):
    return [ln[3:] for ln in result.out.splitlines() if ln.startswith("== ")]


def shown_repos(result):
    """The repos that printed something: block headers, or the names starting compact rows."""
    if headers(result):
        return headers(result)
    return [ln.split()[0] for ln in result.out.splitlines() if ln.strip()]


# ---- output -----------------------------------------------------------------------------
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


def test_no_output_at_all(world, run):
    world.repo("A")
    r = run("diff", cwd=world.work)
    assert r.out.strip() == "(no output)"


def test_quiet_leaves_out_the_no_output_note(world, run):
    world.repo("A")
    r = run("-q", "diff", cwd=world.work)
    assert r.code == 0 and r.out == ""


def test_git_messages_go_to_stderr(world, run):
    world.repo("A")
    world.repo("B")
    r = run("-y", "branch", "-d", "no-such-branch", cwd=world.work)
    assert r.code == 1
    assert "error: branch 'no-such-branch' not found" in r.err
    assert "A, B: error: branch 'no-such-branch' not found" in r.out  # same error, grouped


def test_prefix_puts_the_repo_path_in_front_of_each_line(world, run):
    world.repo("A", {"main.tex": "x\n", "sub/b.tex": "y\n"})
    world.repo("B")
    r = run("--prefix", "ls-files", cwd=world.work)
    assert r.code == 0
    assert r.out.splitlines() == ["A/main.tex", "A/sub/b.tex", "B/main.tex"]


def test_prefix_is_relative_to_where_you_are(world, run):
    world.repo("A")
    world.repo("B")
    r = run("--prefix", "ls-files", cwd=world.work / "A")
    assert r.out.splitlines() == ["main.tex", "../B/main.tex"]


def test_prefix_with_grep(world, run):
    world.repo("A", {"main.tex": "TODO here\n"})
    world.repo("B")
    r = run("--prefix", "grep", "-n", "TODO", cwd=world.work)
    assert r.out.strip() == "A/main.tex:1:TODO here"


def test_nul_separated_output(world, run):
    for name in ("A", "B"):
        world.repo(name, {"x.tex": "x\n", "y.tex": "y\n"}, remote=False)
    r = run("--prefix", "ls-files", "-z", cwd=world.work)
    assert r.out.split("\0") == ["A/x.tex", "A/y.tex", "B/x.tex", "B/y.tex", ""]
    r = run("-r", "A", "ls-files", "-z", cwd=world.work)
    assert "A  x.tex" not in r.out and "x.tex\0y.tex" in r.out
    write(world.work / "A" / "x.tex", "TODO\n")
    r = run("--prefix", "grep", "-z", "-n", "TODO", cwd=world.work)   # NUL after the file name only
    assert r.out == "A/x.tex\x001\x00TODO\n"


def test_rows_line_up_for_wide_and_accented_names(world, run):
    for name in ("Deck", "\u6570\u5b66", "U\u0308bung"):    # CJK takes two columns, the accent none
        world.repo(name, remote=False)
    for argv in (["-l"], ["rev-parse", "--abbrev-ref", "HEAD"]):
        lines = [ln for ln in run(*argv, cwd=world.work).out.splitlines() if "main" in ln]
        assert len(lines) == 3 and len({width(ln[:ln.index("main")]) for ln in lines}) == 1, lines
    assert width("\U0001f44d\ufe0f") == 2 and width("a\u200db") == 2  # emoji + selector; joiner


def test_on_a_terminal_git_output_looks_as_in_git(world, run, monkeypatch):
    # git writes to a pipe here, so it would drop log's branch names and use 80 columns
    a = world.repo("A")
    monkeypatch.setattr(gitall, "TTY", True)
    monkeypatch.setattr(gitall, "NO_COLOR", True)
    assert "(HEAD -> main, origin/main)" in run("log", "-1", "--oneline", cwd=world.work).out
    r = run("-c", "log.decorate=no", "log", "-1", "--oneline", cwd=world.work)
    assert "HEAD" not in r.out
    git(a, "config", "log.decorate", "no")      # set in the repo itself
    assert "HEAD" not in run("log", "-1", "--oneline", cwd=world.work).out
    long = "chapter-three/figures-and-tables/supplementary-figures-and-tables-for-the-appendix.tex"
    write(a / long)
    git(a, "add", "-A")
    monkeypatch.setenv("COLUMNS", "")
    monkeypatch.delenv("COLUMNS")
    monkeypatch.setattr(shutil, "get_terminal_size", lambda *a: os.terminal_size((200, 40)))
    assert long in run("diff", "--cached", "--stat", cwd=world.work).out


def test_non_ascii_filenames_are_not_quoted(world, run):
    world.repo("A", {"Übung_讲义.tex": "x\n"})
    r = run("ls-files", cwd=world.work)
    assert "Übung_讲义.tex" in r.out and "\\" not in r.out


# ---- confirmation -------------------------------------------------------------------------
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


def test_read_only_commands_do_not_ask(world, run):
    a = world.repo("A")
    git(a, "tag", "v1")
    write(a / "junk.tmp")
    for argv in (["branch", "--show-current"], ["branch", "-a"], ["branch", "-vv"],
                 ["remote", "-v"], ["remote", "get-url", "origin"],
                 ["config", "user.name"], ["config", "--get", "user.name"], ["config", "-l"],
                 ["stash", "list"], ["tag"], ["tag", "-l"], ["tag", "-n"], ["reflog", "-1"],
                 ["show-ref"], ["ls-remote", "origin"], ["merge-base", "HEAD", "HEAD"],
                 ["worktree", "list"], ["clean", "-n"], ["rm", "-n", "main.tex"]):
        r = run(*argv, cwd=world.work, tty=False)
        assert r.code == 0, (argv, r)
        assert "Will run" not in r.out, argv
    assert (a / "junk.tmp").exists() and (a / "main.tex").exists()
    assert "main" in run("branch", "--show-current", cwd=world.work).out
    assert "Test" in run("config", "user.name", cwd=world.work).out


def test_changes_ask(world, run):
    a = world.repo("A")
    git(a, "branch", "old")
    write(a / "main.tex", "changed\n")
    for argv in (["branch", "-d", "old"], ["branch", "new"], ["config", "user.name", "X"],
                 ["stash"], ["stash", "pop"], ["remote", "remove", "origin"], ["tag", "v1"],
                 ["reflog", "expire", "--expire=now", "--all"], ["reflog", "delete", "HEAD@{0}"],
                 ["clean", "-fd"], ["worktree", "prune"]):
        r = run(*argv, cwd=world.work, tty=False)
        assert r.code == 2 and "Will run" in r.out, argv
    assert "old" in git(a, "branch")
    assert git(a, "reflog") != ""


def test_stash_show_patch_does_not_ask(world, run):
    a = world.repo("A")
    write(a / "main.tex", "stashed\n")
    git(a, "stash", "-q")
    r = run("stash", "show", "-p", cwd=world.work, tty=False)
    assert r.code == 0 and headers(r) == ["A"] and "+stashed" in r.out


# ---- exit codes -----------------------------------------------------------------------------
def test_grep_exits_like_git(world, run):
    world.repo("A", {"main.tex": "Hello\n"})
    world.repo("B")
    r = run("grep", "no-such-text", cwd=world.work)
    assert r.code == 1 and "(no output)" in r.out and "Failed" not in r.out
    r = run("grep", "Hello", cwd=world.work)
    assert r.code == 0 and shown_repos(r) == ["A"]


def test_diff_exit_code_and_quiet_exit_like_git(world, run):
    a = world.repo("A")
    world.repo("B")
    r = run("diff", "--quiet", cwd=world.work)
    assert r.code == 0 and r.out == ""
    write(a / "main.tex", "changed\n")
    r = run("diff", "--quiet", cwd=world.work)
    assert r.code == 1 and r.out == "" and "Failed" not in r.out
    r = run("diff", "--exit-code", "--stat", cwd=world.work)
    assert r.code == 1 and "main.tex" in r.out and "Failed" not in r.out


def test_one_failure_does_not_stop_the_others(world, run):
    world.repo("A")
    b = world.repo("B")
    git(b, "branch", "feature")
    r = run("rev-parse", "--verify", "-q", "feature", cwd=world.work)
    assert r.code == 1
    assert shown_repos(r)[:1] == ["B"]
    assert "Failed:\n  A: git rev-parse exited with 1" in r.out
    assert "retry:  gitall -r A rev-parse --verify -q feature" in r.out


def retry_line(result):
    return next(ln for ln in result.out.splitlines() if "retry:" in ln).split("retry:", 1)[1].strip()


@pytest.mark.skipif(os.name == "nt", reason="sh quoting")
def test_retry_line_pastes_back_into_sh_unchanged(world, run):
    # a LaTeX-style argument: in "..." the shell would expand $x and run `...`
    world.repo("A")
    arg = "Fix $x^2$ and `\\cite{k}`: it's done! #3 ~me \\\\"
    r = run("rev-parse", "--verify", "-q", arg, cwd=world.work)
    line = retry_line(r)
    assert shlex.split(line) == ["gitall", "-r", "A", "rev-parse", "--verify", "-q", arg]
    p = subprocess.run(["sh", "-c", "printf '%s\\0' " + line], stdout=subprocess.PIPE)
    assert p.stdout.decode("utf-8").split("\0")[-2] == arg


def test_commands_are_quoted_for_powershell_on_windows(monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(os, "name", "nt")
        assert quote("Deck2") == "Deck2"
        assert quote("Fix $x$ `a` it's") == "'Fix $x$ `a` it''s'"
        assert quote("a,b") == "'a,b'" and quote("@x") == "'@x'" and quote("") == "''"


def test_names_with_a_comma(world, run):
    for name in ("Deck", "v2", "Deck, v2", "Smith, Jones"):
        world.repo(name, remote=False)
    r = run("-r", "Deck, v2", "-l", cwd=world.work)     # the whole name, not Deck and v2
    assert r.out.startswith("1 of 4 repo(s)") and "Deck, v2" in r.out
    r = run("-x", "Deck, v2", "-l", cwd=world.work)
    assert r.out.startswith("3 of 4 repo(s)") and "Deck, v2" not in r.out
    for name in ("Deck", "v2"):
        git(world.work / name, "branch", "feature")
    r = run("rev-parse", "--verify", "-q", "feature", cwd=world.work)
    if os.name != "nt":   # one -r each, as a comma would split the name
        assert shlex.split(retry_line(r))[:5] == ["gitall", "-r", "Deck, v2", "-r", "Smith, Jones"]
    r = run("-r", "Deck, v2", "-r", "Smith, Jones", "-l", cwd=world.work)
    assert r.out.startswith("2 of 4 repo(s)") and "Deck, v2" in r.out and "Smith, Jones" in r.out


# ---- which options make a command interactive ------------------------------------------------
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


# ---- paths and files ------------------------------------------------------------------------------
def test_relative_output_file_is_written_where_you_are(world, run):
    world.repo("A")
    world.repo("B")
    r = run("-y", "archive", "-o", "out-{repo}.zip", "HEAD", cwd=world.work)
    assert r.code == 0, r
    for name in ("A", "B"):
        assert zipfile.ZipFile(world.work / f"out-{name}.zip").namelist() == ["main.tex"]
        assert not (world.work / name / f"out-{name}.zip").exists()


def test_checkout_of_a_file_is_not_skipped_in_a_repo_mid_merge(world, run):
    a = world.repo("A")
    make_problem(a, "merge")
    r = run("-y", "checkout", "--theirs", "--", "main.tex", cwd=world.work)
    assert r.code == 0, r
    assert "Skipped" not in r.out
    assert (a / "main.tex").read_text() == "other side\n"


# ---- commands that run once, not per repo ----------------------------------------------------
def test_global_config_is_set_once(world, run):
    world.repo("A")
    world.repo("B")
    r = run("config", "--global", "--add", "test.multi", "x", cwd=world.work)
    assert r.code == 0, r
    assert git(world.work / "A", "config", "--global", "--get-all", "test.multi") == "x"
    r = run("config", "--global", "user.name", cwd=world.work)
    assert r.out.count("Test") == 1


def test_clone_with_a_url_runs_once_where_you_are(world, run):
    world.repo("A")
    world.repo("B")
    r = run("clone", "-q", str(world.remotes / "A.git"), "copy", cwd=world.work)
    assert r.code == 0, r
    assert (world.work / "copy" / "main.tex").exists()
    assert not (world.work / "A" / "copy").exists()


def test_init_with_a_folder_runs_once(world, run):
    world.repo("A")
    world.repo("B")
    r = run("init", "-q", "newrepo", cwd=world.work)
    assert r.code == 0, r
    assert (world.work / "newrepo" / ".git").is_dir()
    assert not (world.work / "A" / "newrepo").exists()


def test_bare_init_is_refused(world, run):
    world.repo("A")
    r = run("init", cwd=world.work)
    assert r.code == 2 and "give its folder" in r.err
    assert not (world.work / ".git").exists()


def test_command_help_runs_once(world, run):
    # (not --help: on Windows that opens the help page in a browser)
    world.repo("A")
    world.repo("B")
    r = run("log", "-h", cwd=world.work)
    assert r.all.count("usage: git log") == 1


def test_add_asks_before_marking_conflicts_resolved(world, run):
    a, b = world.repo("A"), world.repo("B")
    make_problem(a, "merge")
    write(b / "new.tex")
    r = run("add", "-A", cwd=world.work, answer="n")
    assert r.code == 1 and "A: unresolved conflict in main.tex" in r.out
    assert git(a, "ls-files", "-u") and not git(b, "diff", "--cached", "--name-only")
    r = run("add", "-A", cwd=world.work, answer="y")
    assert r.code == 0, r
    assert not git(a, "ls-files", "-u") and git(b, "diff", "--cached", "--name-only") == "new.tex"


def test_add_does_not_ask_once_conflicts_are_resolved(world, run):
    a = world.repo("A")
    make_problem(a, "merge")
    write(a / "main.tex", "both sides\n")
    r = run("add", "-A", cwd=world.work, tty=False)
    assert r.code == 0, r
    assert not git(a, "ls-files", "-u")

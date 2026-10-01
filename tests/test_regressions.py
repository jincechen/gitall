"""Bugs found by reviewing the rewrite: each test reproduces one."""
import pytest

from conftest import git, write
from gitall import absolutize, read_only


@pytest.mark.parametrize("args", [["-am", "-Fix typo"], ["-am", "-tidy up"], ["-m", "-Fix"],
                                  ["--message", "-Fix"], ["-e", "-m", "-Fix"]])
def test_absolutize_leaves_messages_alone(args, tmp_path):
    assert absolutize("commit", args, tmp_path) == args


def test_absolutize_still_fixes_files_after_flags(tmp_path):
    out = absolutize("commit", ["-e", "-F", "msg.txt"], tmp_path)
    assert out[:2] == ["-e", "-F"] and out[2] == str(tmp_path / "msg.txt")
    out = absolutize("commit", ["-aFmsg.txt"], tmp_path)
    assert out == [f"-aF{tmp_path / 'msg.txt'}"]


def test_commit_message_starting_with_dash_f(world, run):
    a = world.repo("A")
    write(a / "main.tex", "changed\n")
    r = run("commit", "-am", "-Fix typo", "-y", cwd=world.work)
    assert r.code == 0, r
    assert git(a, "log", "-1", "--format=%s") == "-Fix typo"


def test_push_with_arguments_does_not_crash(world, run):
    world.repo("A")
    world.local_commit("A", {"x.tex": "x"})
    r = run("push", "origin", "HEAD", "-y", cwd=world.work)
    assert r.code == 0, r
    assert world.remote_head("A") == world.head("A")


def test_one_message_with_a_placeholder_some_repo_lacks(world, run, monkeypatch):
    monkeypatch.setenv("GIT_EDITOR", "echo 'msg {upstream}' >")
    a = world.repo("A")
    b = world.repo("B", remote=False)
    for repo in (a, b):
        write(repo / "main.tex", "changed\n")
    r = run("commit", "-a", "-y", cwd=world.work)
    assert r.code == 0, r
    assert git(a, "log", "-1", "--format=%s") == "msg origin/main"
    assert "B: no upstream branch, so no {upstream}" in r.out
    assert git(b, "log", "-1", "--format=%s") == "initial"


def test_broken_repo_is_a_failure_not_a_skip(world, run):
    world.repo("A")
    broken = world.work / "B"
    broken.mkdir()
    write(broken / ".git", "gitdir: ../nowhere\n")
    write(world.work / "A" / "main.tex", "changed\n")
    r = run("commit", "-am", "x", "-y", cwd=world.work)
    assert r.code == 1
    assert "Failed:\n  B:" in r.out


def test_pathspec_matching_nothing_anywhere_is_an_error(world, run):
    world.repo("A")
    world.repo("B")
    r = run("-y", "commit", "-m", "x", "--", "*.txe", cwd=world.work)
    assert r.code == 1
    assert "did not match any file(s) known to git" in r.err


def test_misplaced_yes_gets_a_hint(world, run):
    a = world.repo("A")
    write(a / "main.tex", "changed\n")
    r = run("commit", "-m", "x", "-y", "--", "main.tex", cwd=world.work, tty=False)
    assert r.code == 1
    assert "-y goes before the git command, or last" in r.out
    assert "usage:" not in r.all


def test_retry_line_keeps_dash_C(world, run):
    world.repo("A")
    world.repo("B")
    git(world.work / "B", "branch", "feature")
    r = run("-C", "work", "rev-parse", "--verify", "-q", "feature", cwd=world.root)
    retry = next(line for line in r.out.splitlines() if "retry:" in line)
    assert retry.strip().startswith("retry:  gitall -C ") and str(world.work) in retry
    assert retry.endswith(" -r A rev-parse --verify -q feature")


@pytest.mark.parametrize("cmd, args", [("branch", ["--sort", "-committerdate"]),
                                       ("branch", ["--format", "%(refname)"]),
                                       ("tag", ["--sort", "-v:refname"]),
                                       ("bisect", ["log"])])
def test_more_read_only_forms(cmd, args):
    assert read_only(cmd, args)


def test_gitall_file_hash_and_dot_git_in_names(world, run):
    world.repo("C# tools", remote=False)
    world.repo("my repo.git", remote=False)
    write(world.work / ".gitall", "C# tools   # a comment\nmy repo.git\n")
    r = run("-l", cwd=world.work)
    assert "C# tools" in r.out and "my repo.git" in r.out
    assert "missing" not in r.out and not r.err


def test_gitall_file_empty_brackets_end_a_group(world, run):
    for name in ("A", "B", "C"):
        world.repo(name, remote=False)
    write(world.work / ".gitall", "[g]\nA\n[]\nB\n")
    r = run("-r", "g", "-l", cwd=world.work)
    assert r.out.startswith("1 of 2 repo(s)")
    assert "groups: g (1)" in r.out


def test_quiet_status_says_when_all_is_clean(world, run):
    world.repo("A")
    world.repo("B")
    assert run("-q", "status", cwd=world.work).out.strip() == "all 2 repos clean"

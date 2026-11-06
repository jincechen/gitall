"""Bugs found in reviews: each test reproduces one."""
import os
import re
import subprocess

import pytest

from conftest import git, write
from helpers import make_problem


def test_commit_message_starting_with_dash_f(world, run):
    a = world.repo("A")
    write(a / "main.tex", "changed\n")
    r = run("commit", "-am", "-Fix typo", "-y", cwd=world.work)
    assert r.code == 0, r
    assert git(a, "log", "-1", "--format=%s") == "-Fix typo"


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


def test_misplaced_yes_gets_a_hint(world, run):
    a = world.repo("A")
    write(a / "main.tex", "changed\n")
    r = run("commit", "-m", "x", "-y", "--", "main.tex", cwd=world.work, tty=False)
    assert r.code == 1
    assert "-y goes before the git command, or last" in r.out
    assert "usage:" not in r.all


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


def test_mistyped_command_is_reported_once_like_git(world, run):
    world.repo("A", remote=False)
    world.repo("B", remote=False)
    r = run("stauts", cwd=world.work, tty=False)
    assert r.code == 1
    assert r.all.count("is not a git command") == 1 and "status" in r.err
    assert "Will run" not in r.out and "not running interactively" not in r.err


def test_a_repos_own_alias_is_not_taken_for_a_typo(world, run):
    for name in ("A", "B"):
        git(world.repo(name, remote=False), "config", "alias.hd", "rev-parse --short HEAD")
    r = run("hd", cwd=world.work, answer="y")
    assert r.code == 0, r
    assert "is not a git command" not in r.all
    assert len(re.findall(r"(?:^|\] )[AB]  [0-9a-f]{7,}$", r.out, re.M)) == 2   # after the prompt


def test_force_push_of_a_repo_that_is_only_behind(world, run):
    a = world.repo("A")
    world.local_commit("A", {"bad.tex": "x"})
    git(a, "push", "-q")
    git(a, "reset", "-q", "--hard", "HEAD~1")
    r = run("push", "-f", "-y", cwd=world.work)
    assert r.code == 0, r
    assert "replaces these commits on the remote:" in r.out
    assert world.remote_head("A") == world.head("A")


def test_push_refused_by_the_remote_does_not_say_pull(world, run):
    world.repo("A")
    world.local_commit("A", {"x.tex": "x"})
    hook = world.remotes / "A.git" / "hooks" / "pre-receive"
    write(hook, "#!/bin/sh\necho 'main is protected' >&2\nexit 1\n")
    hook.chmod(0o755)
    r = run("push", "-y", cwd=world.work)
    assert r.code == 1
    assert "A: rejected (pre-receive hook declined)" in r.out and "main is protected" in r.out
    assert "pull first" not in r.out and "retry:  gitall -r A push" in r.out


def test_option_values_are_not_taken_for_branches(world, run):
    world.repo("A")
    world.repo("local", remote=False)
    r = run("pull", "-X", "theirs", cwd=world.work)
    assert r.code == 0, r
    assert "local: no upstream branch, nothing to pull from" in r.out
    r = run("push", "-o", "ci.skip", "-y", cwd=world.work)
    assert r.code == 0 and "nothing to push" in r.out


def test_push_skips_a_repo_without_a_remote(world, run):
    world.repo("A", remote=False)
    world.local_commit("A", {"x.tex": "x"})
    r = run("-c", "push.autoSetupRemote=true", "push", "-y", cwd=world.work)
    assert r.code == 0 and "A: no remote to push to" in r.out


@pytest.mark.parametrize("spec", ["", ","])
def test_empty_r_is_an_error_not_every_repo(world, run, spec):
    world.repo("A", remote=False)
    r = run("-r", spec, "-l", cwd=world.work)
    assert r.code == 2 and "names no repo" in r.err


def test_clone_takes_r_and_git_options(world, run):
    urls = {}
    for name in ("A", "B", "C"):
        world.repo(name, where=world.root / "seed")
        urls[name] = (world.remotes / f"{name}.git").as_uri()      # file://, so --depth works
    write(world.work / ".gitall", "".join(f"{n}  {u}\n" for n, u in urls.items()))
    r = run("-r", "B", "clone", "--depth", "1", "-y", cwd=world.work)
    assert r.code == 0, r
    assert [p.name for p in world.work.iterdir() if p.is_dir()] == ["B"]
    assert git(world.work / "B", "rev-parse", "--is-shallow-repository") == "true"


def test_gitall_file_takes_absolute_paths(world, run):
    world.repo("A", remote=False)
    world.repo("X", remote=False, where=world.root / "elsewhere")
    write(world.work / ".gitall", f"A\n{(world.root / 'elsewhere' / 'X').as_posix()}\n")
    r = run("-l", cwd=world.work)
    assert r.out.startswith("2 repo(s)") and not r.err


@pytest.mark.skipif(os.name != "nt", reason="junctions")
def test_junction_to_a_repo_is_listed_once(world, run):
    world.repo("A", remote=False)
    subprocess.run(["cmd", "/c", "mklink", "/J", str(world.work / "A-link"), str(world.work / "A")],
                   check=True, capture_output=True)
    r = run("-l", cwd=world.work)
    assert r.out.startswith("1 repo(s)") and "A-link (same repo as A)" in r.out


def test_commit_message_that_looks_like_help(world, run):
    a, b = world.repo("A"), world.repo("B")
    for repo in (a, b):
        write(repo / "main.tex", "changed\n")
    r = run("commit", "-am", "--help", "-y", cwd=world.work)
    assert r.code == 0, r
    assert git(a, "log", "-1", "--format=%s") == git(b, "log", "-1", "--format=%s") == "--help"


def test_malformed_alias_is_reported_like_git(world, run):
    world.repo("A", remote=False)
    r = run("-c", "alias.lg=log --format='%h", "lg", cwd=world.work)
    assert r.code == 2 and "bad alias.lg string" in r.err and "Traceback" not in r.all


def test_quiet_status_does_not_call_a_flagged_repo_clean(world, run):
    a = world.repo("A")
    world.repo("B")
    make_problem(a, "index.lock")
    r = run("-q", "status", cwd=world.work)
    assert "index.lock" in r.out and "clean" not in r.out


def test_switch_falling_back_to_git_reports_a_broken_repo_once(world, run):
    world.repo("A")
    write(world.work / "B" / ".git", "gitdir: ../nowhere\n")
    r = run("-y", "switch", "nosuch", cwd=world.work)
    assert r.code == 1 and "B, B" not in r.out


def test_status_hint_keeps_dash_C(world, run):
    a = world.repo("A")
    for i in range(12):
        write(a / f"f{i}.tex")
    r = run("-C", "work", "status", cwd=world.root)
    hint = next(ln for ln in r.out.splitlines() if "more (" in ln)
    assert " -C " in hint and hint.endswith(" -r A status -s)")


def test_pull_counts_only_the_commits_that_came_in(world, run):
    world.repo("A")
    world.local_commit("A", {"local.tex": "x"})
    world.coauthor_edit("A", {"overleaf.tex": "y"})
    r = run("pull", "--rebase", cwd=world.work)
    assert r.code == 0, r
    assert "rebased, 1 commit" in r.out

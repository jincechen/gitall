"""Bugs found by reviewing the rewrite: each test reproduces one."""
import pytest

from conftest import git, write
from gitall import read_only


def test_broken_repo_is_a_failure_not_a_skip(world, run):
    world.repo("A")
    broken = world.work / "B"
    broken.mkdir()
    write(broken / ".git", "gitdir: ../nowhere\n")
    write(world.work / "A" / "main.tex", "changed\n")
    r = run("commit", "-am", "x", "-y", cwd=world.work)
    assert r.code == 1
    assert "Failed:\n  B:" in r.out


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

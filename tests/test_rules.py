"""The tables behind confirmation, interactive runs, the commit editor and argument handling."""
import pytest

from gitall import commit_opens_editor, interactive, read_only, strip_yes


@pytest.mark.parametrize("cmd, args, expected", [
    ("reflog", [], True),
    ("reflog", ["show", "-3"], True),
    ("reflog", ["HEAD"], True),
    ("reflog", ["expire", "--expire=now", "--all"], False),
    ("reflog", ["delete", "HEAD@{0}"], False),
    ("reflog", ["drop"], False),
    ("tag", [], True),
    ("tag", ["-l"], True),
    ("tag", ["-l", "v*"], True),
    ("tag", ["-n"], True),
    ("tag", ["-n5"], True),
    ("tag", ["--contains", "HEAD"], True),
    ("tag", ["v1"], False),
    ("tag", ["-a", "v1", "-m", "x"], False),
    ("tag", ["-d", "v1"], False),
    ("tag", ["-f", "v1"], False),
    ("show-ref", [], True),
    ("ls-remote", ["origin"], True),
    ("merge-base", ["a", "b"], True),
    ("cherry", ["-v"], True),
    ("worktree", ["list"], True),
    ("worktree", ["add", "x"], False),
    ("worktree", [], False),
    ("notes", [], True),
    ("notes", ["show"], True),
    ("notes", ["add", "-m", "x"], False),
    ("submodule", [], True),
    ("submodule", ["status"], True),
    ("submodule", ["update", "--init"], False),
    ("clean", ["-n"], True),
    ("clean", ["-nd"], True),
    ("clean", ["--dry-run"], True),
    ("clean", ["-fd"], False),
    ("clean", ["-n", "-i"], False),
    ("rm", ["-n", "x"], True),
    ("rm", ["x"], False),
    ("mv", ["--dry-run", "a", "b"], True),
    ("lfs", ["ls-files"], True),
    ("lfs", ["pull"], False),
    ("log", ["-p"], True),
    ("fetch", [], True),
    ("checkout", ["main"], False),
    ("reset", ["--hard"], False),
    ("stash", [], False),
    ("stash", ["list"], True),
    ("stash", ["show", "-p"], True),
    ("stash", ["pop"], False),
    ("branch", [], True),
    ("branch", ["-a"], True),
    ("branch", ["-vv"], True),
    ("branch", ["--show-current"], True),
    ("branch", ["--list", "feat*"], True),
    ("branch", ["--contains", "HEAD"], True),
    ("branch", ["--merged", "main"], True),
    ("branch", ["feature"], False),
    ("branch", ["-d", "feature"], False),
    ("branch", ["-rd", "origin/x"], False),
    ("branch", ["-v", "-d", "x"], False),
    ("branch", ["--set-upstream-to=origin/main"], False),
    ("branch", ["-u", "origin/main"], False),
    ("remote", [], True),
    ("remote", ["-v"], True),
    ("remote", ["get-url", "origin"], True),
    ("remote", ["show", "origin"], True),
    ("remote", ["add", "x", "url"], False),
    ("remote", ["set-url", "origin", "url"], False),
    ("config", ["user.name"], True),
    ("config", ["--global", "user.name"], True),
    ("config", ["--get", "user.name"], True),
    ("config", ["-l"], True),
    ("config", ["get", "user.name"], True),
    ("config", ["list"], True),
    ("config", ["user.name", "X"], False),
    ("config", ["set", "user.name", "X"], False),
    ("config", ["--unset", "user.name"], False),
    ("config", ["unset", "user.name"], False),
    ("config", ["-e"], False),
])
def test_read_only(cmd, args, expected):
    assert read_only(cmd, args) is expected


@pytest.mark.parametrize("cmd, args, expected", [
    ("add", ["-p"], True),
    ("add", ["-i"], True),
    ("add", ["-e"], True),
    ("checkout", ["-p"], True),
    ("reset", ["--patch"], True),
    ("restore", ["-p"], True),
    ("stash", ["-p"], True),
    ("stash", ["push", "-p"], True),
    ("clean", ["-i"], True),
    ("rebase", ["-i", "HEAD~2"], True),
    ("merge", ["--edit", "x"], True),
    ("mergetool", [], True),
    ("difftool", [], True),
    ("config", ["-e"], True),
    ("config", ["--global", "--edit"], True),
    ("config", ["edit"], True),
    ("am", ["-i", "patch.mbox"], True),
    ("config", ["-l"], False),
    ("tag", ["-a", "v1"], True),
    ("tag", ["-s", "v1"], True),
    ("tag", ["-a", "v1", "-m", "x"], False),
    ("tag", ["-a", "v1", "-mx"], False),
    ("tag", ["-a", "v1", "-F", "msg.txt"], False),
    ("tag", ["v1"], False),
    ("commit", ["-p"], True),
    ("commit", ["--interactive"], True),
    ("commit", ["-i", "x"], False),            # -i is --include, not interactive
    ("pull", ["--rebase=interactive"], True),
    ("pull", ["--rebase"], False),
    ("notes", ["edit"], True),
    ("log", ["-p"], False),
    ("diff", ["-p"], False),
    ("show", ["-p"], False),
    ("grep", ["-i", "x"], False),
    ("grep", ["-e", "x"], False),
    ("stash", ["show", "-p"], False),
    ("clean", ["-n"], False),
])
def test_interactive(cmd, args, expected):
    assert interactive(cmd, args) is expected


@pytest.mark.parametrize("args, expected", [
    ([], True),
    (["-a"], True),
    (["-m", "x"], False),
    (["-am", "x"], False),
    (["-amx"], False),
    (["-m", "Fixed -e typo"], False),       # a message isn't an option
    (["-mEdited"], False),
    (["--message=x"], False),
    (["--message", "-e"], False),
    (["-F", "f"], False),
    (["--file=f"], False),
    (["-C", "HEAD"], False),
    (["--reuse-message", "HEAD"], False),
    (["-c", "HEAD"], True),
    (["-ac", "HEAD"], True),
    (["--reedit-message=HEAD"], True),
    (["-c", "HEAD", "--no-edit"], False),
    (["-m", "x", "-e"], True),
    (["-m", "x", "--edit"], True),
    (["--amend"], True),
    (["--amend", "--no-edit"], False),
    (["--fixup", "HEAD"], False),
    (["--fixup=HEAD"], False),
    (["--fixup=amend:HEAD"], True),
    (["--fixup", "reword:HEAD"], True),
    (["--squash", "HEAD"], True),
    (["--squash=HEAD", "-m", "x"], False),
    (["-Skeyid", "-m", "x"], False),        # -S<keyid>: the 'e' is part of the key id
    (["-m", "x", "--", "-e"], False),       # after -- it's a path
])
def test_commit_opens_editor(args, expected):
    assert commit_opens_editor(args) is expected


@pytest.mark.parametrize("args, expected", [
    (["-m", "x", "-y"], (["-m", "x"], True)),
    (["-m", "x", "--yes"], (["-m", "x"], True)),
    (["-y", "-m", "x"], (["-y", "-m", "x"], False)),      # only as the last argument
    (["-m", "-y"], (["-m", "-y"], False)),                # the message is "-y"
    (["--", "-y"], (["--", "-y"], False)),                # a path called "-y"
    (["-e", "-y"], (["-e"], True)),                       # commit -e takes no value
    ([], ([], False)),
])
def test_strip_yes(args, expected):
    assert strip_yes(args) == expected

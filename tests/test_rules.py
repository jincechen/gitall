"""The tables behind confirmation, interactive runs and the commit editor."""
import pytest

from gitall import commit_opens_editor


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

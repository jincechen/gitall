"""Which repos gitall picks: .gitall file, repos in the folder, or the repo and its siblings."""
import os

import pytest

from conftest import write
from helpers import listed


def test_repos_in_folder_sorted_naturally(world, run):
    for name in ("Deck10", "deck1", "Deck2"):
        world.repo(name, remote=False)
    r = run("-l", cwd=world.work)
    assert r.code == 0
    assert listed(r) == ["deck1", "Deck2", "Deck10"]
    assert r.out.startswith(f"3 repo(s) in {world.work}")


def test_folder_names_with_other_digits(world, run):
    # '²' and '①' are digits to str.isdigit() but not to int(): sorting used to crash
    world.repo("Deck2", remote=False)
    for name in ("Kapitel 1²", "①"):
        (world.work / name).mkdir()
    assert listed(run("-l", cwd=world.work)) == ["Deck2"]


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="POSIX permissions, not as root")
def test_folder_that_cannot_be_opened_is_ignored(world, run):
    world.repo("A", remote=False)
    locked = world.work / "lost+found"
    locked.mkdir()
    locked.chmod(0)
    try:
        r = run("-l", cwd=world.work)
    finally:
        locked.chmod(0o755)
    assert r.code == 0, r
    assert listed(r) == ["A"]


def test_list_rows_show_position_branch_and_state(world, run):
    world.repo("A", remote=False)
    world.repo("Bee")
    r = run("-l", cwd=world.work)
    assert "  1  A    main  local only" in r.out
    assert "  2  Bee  main  clean" in r.out


def test_folders_and_files_that_are_not_repos_are_ignored(world, run):
    world.repo("A", remote=False)
    (world.work / "notes").mkdir()
    write(world.work / "readme.txt")
    assert listed(run("-l", cwd=world.work)) == ["A"]


def test_inside_a_repo_uses_it_and_its_siblings(world, run):
    world.repo("A", remote=False)
    world.repo("B", remote=False)
    deep = world.work / "B" / "figs" / "raw"   # any depth below the repo's top
    deep.mkdir(parents=True)
    assert listed(run("-l", cwd=deep)) == ["A", "B"]


def test_gitall_file_sets_the_list_and_its_order(world, run):
    for name in ("A", "B", "C"):
        world.repo(name, remote=False)
    write(world.work / ".gitall", "C\nA\n")
    r = run("-l", cwd=world.work)
    assert listed(r) == ["C", "A"]
    assert "(from .gitall)" in r.out


def test_gitall_file_globs_are_case_sensitive(world, run):
    for name in ("Deck1", "Deck2", "deck-tools"):
        world.repo(name, remote=False)
    write(world.work / ".gitall", "Deck*\n")
    assert listed(run("-l", cwd=world.work)) == ["Deck1", "Deck2"]


def test_gitall_file_comments_blank_lines_and_trailing_slashes(world, run):
    for name in ("A", "B", "C"):
        world.repo(name, remote=False)
    write(world.work / ".gitall", "# my repos\n\nA/   # first\n  B\\\n#C\n")
    assert listed(run("-l", cwd=world.work)) == ["A", "B"]


def test_gitall_file_in_a_parent_is_found_from_inside_a_repo(world, run):
    for name in ("A", "B", "tools"):
        world.repo(name, remote=False)
    write(world.work / ".gitall", "A\nB\n")
    sub = world.work / "B" / "sub"
    sub.mkdir()
    assert listed(run("-l", cwd=sub)) == ["A", "B"]


def test_gitall_file_entry_that_is_not_a_repo_is_left_out_with_a_warning(world, run):
    world.repo("A", remote=False)
    (world.work / "plain").mkdir()
    write(world.work / ".gitall", "A\n\nplain\n")
    r = run("-l", cwd=world.work)
    assert r.code == 0
    assert "line 3: 'plain' is not a git repo, left out" in r.err
    assert listed(r) == ["A"]
    r = run("status", cwd=world.work)  # commands still run in the others
    assert r.code == 0 and "A  main  local only" in r.out


def test_gitall_file_glob_matching_nothing(world, run):
    world.repo("A", remote=False)
    write(world.work / ".gitall", "Missing*\n")
    r = run("-l", cwd=world.work)
    assert r.code == 2
    assert "'Missing*' is not a git repo" in r.err
    assert "no git repos found" in r.err


def test_hidden_folders_are_left_out_unless_you_are_in_one(world, run):
    # running gitall in ~ shouldn't pick up ~/.oh-my-zsh; a * in .gitall leaves them out too
    world.repo("A", remote=False)
    hidden = world.repo(".dotfiles", remote=False)
    assert listed(run("-l", cwd=world.work)) == ["A"]
    assert listed(run("-l", cwd=hidden)) == [".dotfiles", "A"]


def test_gitall_file_repo_matched_twice_is_listed_once(world, run):
    for name in ("A1", "A2", "B"):
        world.repo(name, remote=False)
    write(world.work / ".gitall", "A2\nA*\nB\n")
    assert listed(run("-l", cwd=world.work)) == ["A2", "A1", "B"]


def test_gitall_file_entry_in_another_case_or_unicode_form(world, run):
    # macOS and Windows find 'deck1' for the folder Deck1; macOS lists accents decomposed
    for name in ("Deck1", "Deck2", "U\u0308bung"):
        world.repo(name, remote=False)
    write(world.work / ".gitall", "deck1\n\u00dcbung\n")
    assert listed(run("-l", cwd=world.work)) == ["Deck1", "U\u0308bung"]
    write(world.work / ".gitall", "Deck*\n!deck1\n")
    assert listed(run("-l", cwd=world.work)) == ["Deck2"]


@pytest.mark.skipif(os.name == "nt", reason="symlinks")
def test_link_to_a_repo_is_not_a_second_repo(world, run):
    world.repo("Deck1", remote=False)
    (world.work / "current").symlink_to("Deck1")
    r = run("-l", cwd=world.work)
    assert listed(r) == ["Deck1"] and "left out: current (same repo as Deck1)" in r.out


def test_no_repos_found(world, run):
    r = run("status", cwd=world.work)
    assert r.code == 2
    assert "no git repos found" in r.err


def test_git_error_finding_the_repo_is_shown(world, run, monkeypatch):
    # e.g. a git option this git doesn't know, or "dubious ownership": not "no git repos found"
    sub = world.repo("A", remote=False) / "sub"
    sub.mkdir()
    monkeypatch.delenv("GITALL_NOPE", raising=False)
    r = run("--config-env=foo.bar=GITALL_NOPE", "-l", cwd=sub)
    assert r.code == 2 and "GITALL_NOPE" in r.err and "no git repos found" not in r.err


def test_dash_C_starts_in_another_folder(world, run):
    world.repo("A", remote=False)
    r = run("-C", "work", "-l", cwd=world.root)
    assert listed(r) == ["A"]


def test_dash_C_missing_folder(world, run):
    r = run("-C", "nowhere", "status", cwd=world.root)
    assert r.code == 2
    assert "no such directory" in r.err

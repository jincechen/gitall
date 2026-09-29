"""gitall commit: preview every repo, ask once, commit; skip repos that aren't safe."""
import pytest

from conftest import git, write
from helpers import PROBLEMS, make_problem


def last_message(repo):
    return git(repo, "log", "-1", "--format=%s")


def two_repos_one_staged(world):
    a, b = world.repo("A"), world.repo("B")
    write(a / "intro.tex", "new slide\n")
    git(a, "add", "intro.tex")
    return a, b


def test_commits_staged_changes_and_skips_repos_with_nothing(world, run):
    a, b = two_repos_one_staged(world)
    before_b = world.head("B")
    r = run("commit", "-m", "Add intro", "-y", cwd=world.work)
    assert r.code == 0, r
    assert "== A (main)" in r.out and "A  intro.tex" in r.out
    assert "== B" not in r.out
    assert "A: committed" in r.out and "Add intro (1 file(s))" in r.out
    assert "commit: 1 committed" in r.out
    assert last_message(a) == "Add intro"
    assert world.head("B") == before_b


def test_nothing_to_commit_anywhere(world, run):
    world.repo("A")
    write(world.work / "A" / "untracked.tex")
    r = run("commit", "-m", "x", "-y", cwd=world.work)
    assert r.code == 0
    assert "nothing to commit" in r.out


def test_repo_placeholder_in_message(world, run):
    a, b = world.repo("Deck1"), world.repo("Deck2")
    for repo in (a, b):
        write(repo / "main.tex", "changed\n")
    run("commit", "-am", "Weekly edits ({repo})", "-y", cwd=world.work)
    assert last_message(a) == "Weekly edits (Deck1)"
    assert last_message(b) == "Weekly edits (Deck2)"


def test_dry_run_only_previews(world, run):
    a, _ = two_repos_one_staged(world)
    before = world.head("A")
    r = run("commit", "-m", "x", "--dry-run", cwd=world.work, tty=False)
    assert r.code == 0
    assert "A  intro.tex" in r.out and "(dry run: 1 repo would be committed)" in r.out
    assert world.head("A") == before


def test_commit_all_tracked_changes(world, run):
    a = world.repo("A")
    write(a / "main.tex", "changed\n")
    write(a / "untracked.tex")
    r = run("commit", "-a", "-m", "All", "-y", cwd=world.work)
    assert "M  main.tex" in r.out and "untracked.tex" not in r.out
    assert last_message(a) == "All"
    assert "?? untracked.tex" in git(a, "status", "--porcelain")


def test_preview_leaves_out_unstaged_and_untracked_files(world, run):
    a, _ = two_repos_one_staged(world)
    write(a / "main.tex", "unstaged change\n")
    write(a / "scratch.txt")
    r = run("commit", "-m", "x", "--dry-run", cwd=world.work)
    assert "A  intro.tex" in r.out
    assert "main.tex" not in r.out and "scratch.txt" not in r.out


def test_pathspec_commits_matching_files_and_no_match_is_not_an_error(world, run):
    files = {"main.tex": "1\n", "notes.md": "1\n"}
    a, b = world.repo("A", files), world.repo("B", files)
    write(a / "main.tex", "2\n")
    write(a / "notes.md", "2\n")
    write(b / "notes.md", "2\n")
    r = run("-y", "commit", "-m", "Fix decks", "--", "*.tex", cwd=world.work)
    assert r.code == 0, r
    assert "Failed" not in r.out
    assert git(a, "show", "--name-only", "--format=", "HEAD") == "main.tex"
    assert " M notes.md" in git(a, "status", "--porcelain")
    assert last_message(b) == "initial"


def test_a_real_git_error_is_reported_with_gits_message(world, run):
    world.repo("A")
    write(world.work / "A" / "main.tex", "changed\n")
    r = run("commit", "-am", "x", "--no-such-option", "-y", cwd=world.work)
    assert r.code == 1
    assert "Failed:\n  A: error: unknown option `no-such-option'" in r.out
    assert "nothing to commit" not in r.out


def test_answer_no_aborts(world, run):
    a, _ = two_repos_one_staged(world)
    before = world.head("A")
    r = run("commit", "-m", "x", cwd=world.work, answer="n")
    assert r.code == 1
    assert "Commit 1 repo? [y/N]" in r.out and "aborted, nothing changed" in r.out
    assert world.head("A") == before


def test_answer_yes_commits(world, run):
    a, _ = two_repos_one_staged(world)
    r = run("commit", "-m", "Yes", cwd=world.work, answer="y")
    assert r.code == 0
    assert last_message(a) == "Yes"


def test_closed_input_aborts(world, run):
    # what happens on Windows when stdin is NUL: it claims to be a terminal, then gives EOF
    two_repos_one_staged(world)
    before = world.head("A")
    r = run("commit", "-m", "x", cwd=world.work, answer=None)
    assert r.code == 1
    assert "no answer (input closed): re-run with -y" in r.err
    assert world.head("A") == before


def test_non_interactive_without_yes_aborts(world, run):
    two_repos_one_staged(world)
    before = world.head("A")
    r = run("commit", "-m", "x", cwd=world.work, tty=False)
    assert r.code == 2
    assert "not running interactively: re-run with -y" in r.err
    assert world.head("A") == before


# ---- the commit message editor ---------------------------------------------------------
def counting_editor(monkeypatch, world, text):
    """GIT_EDITOR that writes text as the message and counts how often it ran."""
    count = world.root / "editor-runs"
    monkeypatch.setenv("GIT_EDITOR", f"echo run >> '{count.as_posix()}'; echo '{text}' >")
    return lambda: len(count.read_text().splitlines()) if count.exists() else 0


def test_no_message_opens_the_editor_in_each_repo(world, run, monkeypatch):
    runs = counting_editor(monkeypatch, world, "from-editor")
    a, b = world.repo("A"), world.repo("B")
    for repo in (a, b):
        write(repo / "main.tex", "changed\n")
    r = run("commit", "-a", "-y", cwd=world.work)
    assert r.code == 0, r
    assert "git will open an editor (or ask questions) in each repo in turn." in r.out
    assert runs() == 2
    assert last_message(a) == last_message(b) == "from-editor"


@pytest.mark.parametrize("opts", [["-c", "HEAD"], ["--reedit-message=HEAD"], ["-m", "typed", "-e"],
                                  ["--squash", "HEAD"], ["--fixup=amend:HEAD"], ["--amend"]])
def test_options_that_need_gits_own_editor_open_it_per_repo(world, run, monkeypatch, opts):
    runs = counting_editor(monkeypatch, world, "from-editor")
    a, b = world.repo("A"), world.repo("B")
    for repo in (a, b):
        write(repo / "main.tex", "changed\n")
        git(repo, "add", "-A")
    r = run("commit", *opts, "-y", cwd=world.work)
    assert r.code == 0, r
    assert "git will open an editor (or ask questions) in each repo in turn." in r.out
    assert runs() == 2
    assert "from-editor" in git(a, "log", "-1", "--format=%B")


@pytest.mark.parametrize("opts", [["-C", "HEAD"], ["--fixup", "HEAD"], ["-c", "HEAD", "--no-edit"],
                                  ["-mEdited"], ["-F", "msg.txt"], ["--amend", "--no-edit"]])
def test_options_that_give_the_message_dont_open_an_editor(world, run, opts):
    a = world.repo("A")
    write(world.work / "msg.txt", "From file\n")
    write(a / "main.tex", "changed\n")
    git(a, "add", "-A")
    r = run("commit", *opts, "-y", cwd=world.work)
    assert r.code == 0, r  # GIT_EDITOR=false would have failed the commit
    assert "editor" not in r.out


def test_relative_message_file_is_read_from_the_starting_folder(world, run):
    a, b = world.repo("A"), world.repo("B")
    write(world.work / "msg.txt", "From the file\n")
    for repo in (a, b):
        write(repo / "main.tex", "changed\n")
    r = run("commit", "-a", "-F", "msg.txt", "-y", cwd=world.work)
    assert r.code == 0, r
    assert last_message(a) == last_message(b) == "From the file"


# ---- commits that don't need changes -----------------------------------------------------
def test_allow_empty_is_not_filtered_out(world, run):
    a, b = world.repo("A"), world.repo("B")
    r = run("commit", "--allow-empty", "-m", "Empty", "-y", cwd=world.work)
    assert r.code == 0, r
    assert last_message(a) == last_message(b) == "Empty"


def test_amend_rewords_every_repo(world, run):
    a, b = world.repo("A"), world.repo("B")
    world.local_commit("B", {"x.tex": "x"}, "local")
    r = run("commit", "--amend", "-m", "Reworded", "-y", cwd=world.work)
    assert r.code == 0, r
    assert last_message(a) == last_message(b) == "Reworded"


def test_commit_patch_runs_attached_and_only_where_there_are_changes(world, run_script):
    a = world.repo("A")
    world.repo("B")
    write(a / "main.tex", "changed\n")
    r = run_script("commit", "-p", "-m", "x", "-y", cwd=world.work)  # stdin closed: nothing picked
    assert "git will open an editor (or ask questions) in each repo in turn." in r.out
    assert "== A" in r.out and "== B" not in r.out
    assert last_message(a) == "initial"  # nothing was picked, so nothing committed


def test_commit_help_is_shown_once(world, run):
    world.repo("A")
    world.repo("B")
    r = run("commit", "-h", cwd=world.work)
    assert r.code == 129
    assert r.all.count("usage: git commit") == 1


def test_non_ascii_filenames_in_preview(world, run):
    a = world.repo("A")
    write(a / "Übung_讲义.tex")
    git(a, "add", "-A")
    r = run("commit", "-m", "x", "-y", cwd=world.work)
    assert "A  Übung_讲义.tex" in r.out


@pytest.mark.parametrize("kind", PROBLEMS)
def test_unsafe_repos_are_skipped(world, run, kind):
    a, b = world.repo("A"), world.repo("B")
    for repo in (a, b):
        write(repo / "new.tex")
        git(repo, "add", "new.tex")
    make_problem(a, kind)
    before = world.head("A")
    r = run("commit", "-m", "x", "-y", cwd=world.work)
    assert r.code == 0, r
    assert f"Skipped:\n  A: {PROBLEMS[kind]}" in r.out
    assert world.head("A") == before
    assert last_message(b) == "x"

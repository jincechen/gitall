"""Which repos gitall picks: .gitall file, repos in the folder, or the repo and its siblings."""
import re

from conftest import write


def listed(result):
    """Repo names from `gitall -l` output, in order."""
    lines = result.out.splitlines()[1:]  # the first line is "N repo(s) in ..."
    return [m.group(1) for m in (re.match(r"\s*\d+\s+(\S+)", ln) for ln in lines) if m]


def rows(result):
    """The repo names at the start of compact one-line-per-repo output."""
    return [line.split()[0] for line in result.out.splitlines() if line.strip()]


def test_repos_in_folder_sorted_naturally(world, run):
    for name in ("Deck10", "deck1", "Deck2"):
        world.repo(name, remote=False)
    r = run("-l", cwd=world.work)
    assert r.code == 0
    assert listed(r) == ["deck1", "Deck2", "Deck10"]
    assert r.out.startswith(f"3 repo(s) in {world.work}")


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
    for name in ("A", "B", "C"):
        world.repo(name, remote=False)
    assert listed(run("-l", cwd=world.work / "B")) == ["A", "B", "C"]


def test_deep_subfolder_of_a_repo(world, run):
    world.repo("A", remote=False)
    world.repo("B", remote=False)
    deep = world.work / "B" / "figs" / "raw"
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


def test_gitall_file_entry_that_is_not_a_repo(world, run):
    world.repo("A", remote=False)
    (world.work / "plain").mkdir()
    write(world.work / ".gitall", "A\n\nplain\n")
    r = run("status", cwd=world.work)
    assert r.code == 2
    assert "line 3: 'plain' is not a git repo" in r.err


def test_gitall_file_glob_matching_nothing(world, run):
    world.repo("A", remote=False)
    write(world.work / ".gitall", "Missing*\n")
    r = run("-l", cwd=world.work)
    assert r.code == 2
    assert "'Missing*' is not a git repo" in r.err


def test_gitall_file_repo_matched_twice_is_listed_once(world, run):
    for name in ("A1", "A2", "B"):
        world.repo(name, remote=False)
    write(world.work / ".gitall", "A2\nA*\nB\n")
    assert listed(run("-l", cwd=world.work)) == ["A2", "A1", "B"]


def test_no_repos_found(world, run):
    r = run("status", cwd=world.work)
    assert r.code == 2
    assert "no git repos found" in r.err


def test_dash_C_starts_in_another_folder(world, run):
    world.repo("A", remote=False)
    r = run("-C", "work", "-l", cwd=world.root)
    assert listed(r) == ["A"]


def test_dash_C_missing_folder(world, run):
    r = run("-C", "nowhere", "status", cwd=world.root)
    assert r.code == 2
    assert "no such directory" in r.err


def test_select_by_name_substring_ignoring_case(world, run):
    for name in ("Deck1_Intro", "Deck2_Methods", "Deck3_Results"):
        world.repo(name, remote=False)
    r = run("-r", "methods", "rev-parse", "--show-toplevel", cwd=world.work)
    assert rows(r) == ["Deck2_Methods"]


def test_select_by_position(world, run):
    for name in ("A", "B", "C"):
        world.repo(name, remote=False)
    r = run("-r", "3", "rev-parse", "--show-toplevel", cwd=world.work)
    assert rows(r) == ["C"]


def test_several_selections_keep_the_list_order(world, run):
    for name in ("A", "B", "C"):
        world.repo(name, remote=False)
    r = run("-r", "C", "--repo=1", "-r", "a", "rev-parse", "--show-toplevel", cwd=world.work)
    assert rows(r) == ["A", "C"]


def test_selection_matching_nothing_lists_the_repos(world, run):
    world.repo("A", remote=False)
    world.repo("B", remote=False)
    r = run("-r", "zzz", "status", cwd=world.work)
    assert r.code == 2
    assert "no repo matches 'zzz' (repos: 1:A, 2:B)" in r.err


def test_selection_position_out_of_range(world, run):
    world.repo("A", remote=False)
    r = run("-r", "5", "status", cwd=world.work)
    assert r.code == 2
    assert "no repo matches '5'" in r.err

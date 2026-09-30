"""Choosing repos: -r lists, globs, positions, groups, states, exclusions; .gitall groups etc."""
import re

import pytest

from conftest import git, write
from helpers import make_problem


def listed(result):
    """Repo names from `gitall -l` output, in order."""
    lines = result.out.splitlines()[1:]  # the first line is "N repo(s) in ..."
    return [m.group(1) for m in (re.match(r"\s*\d+\s+(\S+)", ln) for ln in lines) if m]


def pick(run, world, *opts):
    r = run(*opts, "-l", cwd=world.work)
    assert r.code == 0, r
    return listed(r)


@pytest.fixture
def decks(world):
    """Deck1, Deck2, Deck10, notes, tools -- all with remotes, all clean."""
    for name in ("Deck1", "Deck2", "Deck10", "notes", "tools"):
        world.repo(name)
    return world


# ---- names, globs, positions --------------------------------------------------------
def test_comma_list(decks, run):
    assert pick(run, decks, "-r", "tools,Deck2") == ["Deck2", "tools"]


def test_repeated_r_adds_up(decks, run):
    assert pick(run, decks, "-r", "notes", "--repo=Deck1") == ["Deck1", "notes"]


def test_glob_is_case_insensitive(decks, run):
    assert pick(run, decks, "-r", "deck*") == ["Deck1", "Deck2", "Deck10"]
    assert pick(run, decks, "-r", "DECK?") == ["Deck1", "Deck2"]


def test_substring_is_case_insensitive(decks, run):
    assert pick(run, decks, "-r", "OTE") == ["notes"]


def test_exact_name_wins_over_substring(world, run):
    for name in ("api", "api-wt", "api-gateway", "web"):
        world.repo(name, remote=False)
    assert pick(run, world, "-r", "api") == ["api"]
    assert pick(run, world, "-r", "api-") == ["api-gateway", "api-wt"]  # no exact match: substring


def test_positions_and_ranges(decks, run):
    # list order: Deck1 Deck2 Deck10 notes tools
    assert pick(run, decks, "-r", "2-4") == ["Deck2", "Deck10", "notes"]
    assert pick(run, decks, "-r", "5,1") == ["Deck1", "tools"]


@pytest.mark.parametrize("bad", ["0", "6", "4-2", "3-9"])
def test_position_out_of_range(decks, run, bad):
    r = run("-r", bad, "-l", cwd=decks.work)
    assert r.code == 2 and f"no repo matches '{bad}'" in r.err


def test_list_shows_positions_from_the_full_list(decks, run):
    r = run("-r", "tools,Deck10", "-l", cwd=decks.work)
    assert r.out.startswith("2 of 5 repo(s)")
    assert re.search(r"^\s+3  Deck10\s", r.out, re.M)
    assert re.search(r"^\s+5  tools\s", r.out, re.M)


# ---- exclusions -------------------------------------------------------------------------
def test_exclude_by_name(decks, run):
    assert pick(run, decks, "-x", "notes") == ["Deck1", "Deck2", "Deck10", "tools"]
    assert pick(run, decks, "--exclude=notes,tools") == ["Deck1", "Deck2", "Deck10"]


def test_exclude_glob_and_bang_inside_r(decks, run):
    assert pick(run, decks, "-x", "Deck*") == ["notes", "tools"]
    assert pick(run, decks, "-r", "!Deck*,!notes") == ["tools"]
    assert pick(run, decks, "-r", "deck*,!Deck10") == ["Deck1", "Deck2"]


def test_exclude_that_matches_nothing_is_an_error(decks, run):
    r = run("-x", "zzz", "-l", cwd=decks.work)
    assert r.code == 2 and "no repo matches 'zzz'" in r.err


# ---- states -------------------------------------------------------------------------------
@pytest.fixture
def states(world):
    """One repo per state."""
    for name in ("clean", "staged", "modified", "untracked", "ahead", "behind", "diverged",
                 "stash", "merging", "detached"):
        world.repo(name)
    world.repo("local", remote=False)
    w = world.work
    write(w / "staged" / "new.tex")
    git(w / "staged", "add", "new.tex")
    write(w / "modified" / "main.tex", "changed\n")
    write(w / "untracked" / "new.tex")
    world.local_commit("ahead", {"x.tex": "x"})
    world.coauthor_edit("behind", {"main.tex": "overleaf\n"})
    git(w / "behind", "fetch", "-q")
    world.local_commit("diverged", {"local.tex": "x"})
    world.coauthor_edit("diverged", {"overleaf.tex": "y"})
    git(w / "diverged", "fetch", "-q")
    write(w / "stash" / "main.tex", "stashed\n")
    git(w / "stash", "stash", "-q")
    make_problem(w / "merging", "merge")
    make_problem(w / "detached", "detached")
    return world


STATE_CASES = {
    ":dirty": ["staged", "modified", "untracked", "merging"],
    ":staged": ["staged"],
    ":modified": ["modified"],
    ":untracked": ["untracked"],
    ":ahead": ["ahead", "diverged", "merging"],
    ":behind": ["behind", "diverged"],
    ":diverged": ["diverged"],
    ":noupstream": ["detached", "local"],
    ":stash": ["stash"],
    ":merging": ["merging"],
    ":detached": ["detached"],
}


def test_state_filters(states, run):
    # one workspace for all of them: building it takes a few seconds
    for state, expected in STATE_CASES.items():
        assert sorted(pick(run, states, "-r", state)) == sorted(expected), state


def test_clean_is_the_opposite_of_dirty(states, run):
    dirty = set(pick(run, states, "-r", ":dirty"))
    clean = set(pick(run, states, "-r", ":clean"))
    assert dirty and clean and not dirty & clean
    assert dirty | clean == set(pick(run, states))


def test_states_in_a_list_mean_any_of_them(states, run):
    assert sorted(pick(run, states, "-r", ":staged,:stash")) == ["staged", "stash"]
    assert sorted(pick(run, states, "-r", ":staged", "-r", ":stash")) == ["staged", "stash"]


def test_states_narrow_names_down(states, run):
    assert pick(run, states, "-r", "a*", "-r", ":dirty") == []
    assert sorted(pick(run, states, "-r", "s*,m*", "-r", ":dirty")) == ["merging", "modified", "staged"]


def test_exclude_by_state(states, run):
    everything = pick(run, states)
    dirty = pick(run, states, "-r", ":dirty")
    assert pick(run, states, "-x", ":dirty") == [r for r in everything if r not in dirty]
    assert pick(run, states, "-r", "!:dirty") == [r for r in everything if r not in dirty]


def test_on_branch(world, run):
    a, b = world.repo("A"), world.repo("B")
    world.repo("C")
    git(a, "checkout", "-q", "-b", "feature/one")
    git(b, "checkout", "-q", "-b", "feature/two")
    assert pick(run, world, "-r", ":on=feature/one") == ["A"]
    assert pick(run, world, "-r", ":on=feature/*") == ["A", "B"]
    assert pick(run, world, "-r", ":on=main") == ["C"]


def test_has_branch_local_or_remote(world, run):
    a = world.repo("A")
    world.repo("B")
    world.repo("C")
    git(a, "branch", "feature")
    coauthor = world.coauthor("B")
    git(coauthor, "push", "-q", "origin", "HEAD:refs/heads/feature")
    git(world.work / "B", "fetch", "-q")  # B has only origin/feature
    assert pick(run, world, "-r", ":has=feature") == ["A", "B"]
    assert pick(run, world, "-r", ":has=feat*") == ["A", "B"]
    assert pick(run, world, "-r", ":has=nope") == []


def test_unknown_state(decks, run):
    r = run("-r", ":bogus", "-l", cwd=decks.work)
    assert r.code == 2
    assert "unknown state ':bogus'" in r.err and "dirty" in r.err


def test_state_matching_nothing_is_not_an_error(decks, run):
    r = run("-r", ":ahead", "push", cwd=decks.work)
    assert r.code == 0
    assert r.out.strip() == "no repo matches -r :ahead"


def test_command_runs_only_in_the_chosen_repos(states, run):
    r = run("-r", ":ahead", "-x", ":dirty", "log", "-1", "--format=%s", cwd=states.work)
    assert r.code == 0, r
    assert [ln.split()[0] for ln in r.out.splitlines()] == ["ahead", "diverged"]

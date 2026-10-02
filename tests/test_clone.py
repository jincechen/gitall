"""gitall clone (no URL): clone the repos that .gitall lists with a URL but are missing."""
from conftest import git, write


def seed(world, *names):
    """Remotes for names, without local clones in world.work -> {name: url}."""
    seeds = world.root / "seed"
    return {name: str(world.remotes / f"{name}.git") for name in names
            if world.repo(name, where=seeds)}


def test_clone_missing_repos(world, run):
    urls = seed(world, "A", "B")
    write(world.work / ".gitall", f"A  {urls['A']}\nB  {urls['B']}\n")
    r = run("clone", "-y", cwd=world.work)
    assert r.code == 0, r
    assert f"  A  <-  {urls['A']}" in r.out
    assert "A: cloned" in r.out and "B: cloned" in r.out
    assert git(world.work / "B", "log", "-1", "--format=%s") == "initial"
    assert git(world.work / "A", "rev-parse", "--abbrev-ref", "@{u}") == "origin/main"


def test_only_missing_repos_are_cloned_and_list_shows_them(world, run):
    urls = seed(world, "A", "B")
    write(world.work / ".gitall", f"A  {urls['A']}\nB  {urls['B']}\n")
    run("-y", "clone", cwd=world.work)
    (world.work / "B").rename(world.root / "B-moved")
    r = run("-l", cwd=world.work)
    assert "missing (gitall clone gets them): B" in r.out
    r = run("-y", "clone", cwd=world.work)
    assert r.code == 0, r
    assert "B: cloned" in r.out and "A:" not in r.out
    assert "gitall clone gets them" not in run("-l", cwd=world.work).out


def test_entries_with_url_join_groups_after_cloning(world, run):
    urls = seed(world, "A")
    write(world.work / ".gitall", f"[decks]\nA  {urls['A']}\n")
    run("-y", "clone", cwd=world.work)
    r = run("-r", "decks", "-l", cwd=world.work)
    assert "  1  A  main  clean" in r.out


def test_nothing_to_clone(world, run):
    urls = seed(world, "A")
    write(world.work / ".gitall", f"A  {urls['A']}\n")
    run("-y", "clone", cwd=world.work)
    r = run("clone", cwd=world.work, tty=False)
    assert r.code == 0
    assert r.out.strip() == "nothing to clone: no listed repo is missing"


def test_nothing_to_clone_without_a_gitall_file(world, run):
    world.repo("A")
    r = run("clone", cwd=world.work)
    assert r.code == 0
    assert "nothing to clone: no listed repo is missing (list them as 'name  URL' lines in a .gitall file)" \
        in r.out


def test_clone_asks_first(world, run):
    urls = seed(world, "A")
    write(world.work / ".gitall", f"A  {urls['A']}\n")
    r = run("clone", cwd=world.work, tty=False)
    assert r.code == 2 and "re-run with -y" in r.err
    assert not (world.work / "A").exists()
    r = run("clone", cwd=world.work, answer="n")
    assert r.code == 1 and "Clone 1 repo into" in r.out
    assert not (world.work / "A").exists()


def test_clone_failure_is_reported_without_retry(world, run):
    urls = seed(world, "A")
    write(world.work / ".gitall", f"A  {urls['A']}\nB  {world.root / 'nowhere.git'}\n")
    r = run("-y", "clone", cwd=world.work)
    assert r.code == 1
    assert "A: cloned" in r.out and "B: clone failed" in r.out
    assert "Failed:\n  B: fatal:" in r.out and "retry" not in r.out


def test_parallel_clone(world, run):
    urls = seed(world, "A", "B", "C")
    write(world.work / ".gitall", "jobs = 3\n" + "".join(f"{n}  {u}\n" for n, u in urls.items()))
    r = run("-y", "clone", cwd=world.work)
    assert r.code == 0, r
    assert [ln.split(":")[0] for ln in r.out.splitlines() if ln.endswith("cloned")] == ["A", "B", "C"]


def test_clone_with_a_url_runs_once(world, run):
    urls = seed(world, "A")
    world.repo("X", remote=False)
    world.repo("Y", remote=False)
    r = run("clone", "-q", urls["A"], "A-copy", cwd=world.work)
    assert r.code == 0, r
    assert (world.work / "A-copy" / "main.tex").exists()
    assert not (world.work / "X" / "A-copy").exists()

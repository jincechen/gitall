"""Command line handling."""
from conftest import write


def test_no_command_prints_help(world, run):
    r = run(cwd=world.work)
    assert r.code == 2 and r.out.startswith("gitall -- run git in several repositories")


def test_help(world, run):
    for argv in (["-h"], ["--help"], ["help"]):
        r = run(*argv, cwd=world.work)
        assert r.code == 0 and "Usage:  gitall [options]" in r.out, argv


def test_unknown_option(world, run):
    r = run("-z", "status", cwd=world.work)
    assert r.code == 2
    assert "unknown option '-z'" in r.err


def test_option_missing_its_value(world, run):
    r = run("status", "-r", cwd=world.work)  # after the command: goes to git, not to gitall
    assert "needs a value" not in r.err
    r = run("-r", cwd=world.work)
    assert r.code == 2 and "-r needs a value" in r.err


def test_git_version_runs_once(world, run):
    world.repo("A", remote=False)
    world.repo("B", remote=False)
    r = run("version", cwd=world.work)
    assert r.code == 0 and r.out.count("git version") == 1


def test_yes_after_the_git_command(world, run):
    world.repo("A")
    r = run("tag", "v1", "-y", cwd=world.work, tty=False)
    assert r.code == 0, r
    assert "done in 1 repo(s)" in r.out


def test_closed_stdin_in_a_real_process(world, run_script):
    # on Windows NUL claims to be a terminal, so this reaches the prompt and gets end of input
    world.repo("A")
    r = run_script("tag", "v1", cwd=world.work)
    assert r.code in (1, 2)
    assert "re-run with -y" in r.err


def test_gitall_file_is_read_as_utf8(world, run):
    world.repo("Übung", remote=False)
    write(world.work / ".gitall", "Übung\n")
    assert "Übung" in run("-l", cwd=world.work).out

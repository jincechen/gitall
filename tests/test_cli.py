"""Command line handling, output encoding, renaming the script, the Windows launcher."""
import os
import shutil
import subprocess

import pytest

from conftest import ROOT, git, write


def test_no_command_prints_help(world, run):
    r = run(cwd=world.work)
    assert r.code == 2 and r.out.startswith("gitall -- run git in several repositories")


@pytest.mark.parametrize("argv", [["-h"], ["--help"], ["help"]])
def test_help(world, run, argv):
    r = run(*argv, cwd=world.work)
    assert r.code == 0 and "Usage:  gitall [options]" in r.out


def test_unknown_option(world, run):
    r = run("-z", "status", cwd=world.work)
    assert r.code == 2
    assert "unknown option '-z'" in r.err


def test_option_missing_its_value(world, run):
    r = run("status", "-r", cwd=world.work)  # after the command: goes to git, not to gitall
    assert "needs a value" not in r.err
    for opt in ("-r", "-x", "-C"):
        r = run(opt, cwd=world.work)
        assert r.code == 2 and f"{opt} needs a value" in r.err


def test_git_version_runs_once(world, run):
    world.repo("A", remote=False)
    world.repo("B", remote=False)
    r = run("version", cwd=world.work)
    assert r.code == 0 and r.out.count("git version") == 1
    r = run("--version", cwd=world.work)
    assert r.code == 0 and r.out.count("git version") == 1


def test_list_with_a_command_is_an_error(world, run):
    world.repo("A", remote=False)
    r = run("-l", "status", cwd=world.work)
    assert r.code == 2
    assert "-l lists the repos" in r.err


def test_list_respects_selection(world, run):
    for name in ("A", "B", "C"):
        world.repo(name, remote=False)
    r = run("-r", "B", "-l", cwd=world.work)
    assert r.out.startswith("1 of 3 repo(s)")
    assert "  2  B  main  local only" in r.out
    r = run("-l", "-x", "B", cwd=world.work)  # option order doesn't matter
    assert r.out.startswith("2 of 3 repo(s)")


def test_yes_after_the_git_command(world, run):
    world.repo("A")
    r = run("tag", "v1", "-y", cwd=world.work, tty=False)
    assert r.code == 0, r
    assert "done in 1 repo" in r.out
    assert git(world.work / "A", "tag") == "v1"


def test_yes_is_only_taken_as_the_last_argument(world, run):
    world.repo("A")
    r = run("-y", "tag", "-a", "v2", "-m", "-y", cwd=world.work)  # -y is the message here
    assert r.code == 0, r
    assert git(world.work / "A", "tag", "-n1", "-l", "v2").split() == ["v2", "-y"]
    r = run("tag", "-y", "v3", cwd=world.work, tty=False)  # not last: goes to git, which asks first
    assert r.code == 2 and "not running interactively" in r.err


def test_yes_after_double_dash_is_a_path(world, run):
    a = world.repo("A")
    write(a / "-y", "content\n")
    r = run("-y", "add", "--", "-y", cwd=world.work)
    assert r.code == 0, r
    assert "A  -y" in git(a, "status", "--porcelain")


def test_git_options_before_the_command_are_passed_on(world, run):
    world.repo("A")
    world.repo("B")
    r = run("-c", "core.abbrev=12", "log", "-1", "--format=%h", cwd=world.work)
    assert r.code == 0, r
    assert all(len(line.split()[1]) == 12 for line in r.out.splitlines())
    r = run("--no-pager", "--literal-pathspecs", "log", "-1", "--format=%s", cwd=world.work)
    assert r.code == 0 and "A  initial" in r.out


@pytest.mark.parametrize("opt", ["--git-dir=x", "--work-tree", "-p", "--paginate", "--bare"])
def test_git_options_that_make_no_sense_are_refused(world, run, opt):
    world.repo("A")
    r = run(opt, "status", cwd=world.work)
    assert r.code == 2 and "doesn't work with gitall" in r.err


def test_closed_stdin_in_a_real_process(world, run_script):
    # on Windows NUL claims to be a terminal, so this reaches the prompt and gets end of input
    world.repo("A")
    r = run_script("tag", "v1", cwd=world.work)
    assert r.code in (1, 2)
    assert "re-run with -y" in r.err


def test_non_ascii_output_when_redirected(world, run_script):
    # with a legacy console encoding, printing non-ASCII text used to raise UnicodeEncodeError
    world.repo("讲义", {"Übung.tex": "x\n", "other.tex": "y\n"})
    env = {"PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}
    r = run_script("ls-files", cwd=world.work, env=env)
    assert r.code == 0, r
    assert "== 讲义" in r.out and "Übung.tex" in r.out
    r = run_script("-r", "zzz", "status", cwd=world.work, env=env)
    assert r.code == 2, r
    assert "(repos: 1:讲义)" in r.err


def test_closed_pipe_exits_quietly(world, run_script):
    for i in range(30):
        world.repo(f"R{i}", {f"f{j}.tex": "x\n" for j in range(30)}, remote=False)
    p = subprocess.Popen([os.sys.executable, str(ROOT / "gitall.py"), "ls-files"], cwd=world.work,
                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    p.stdout.read(10)
    p.stdout.close()
    err = p.stderr.read().decode("utf-8", "replace")
    p.wait(timeout=60)
    assert "Traceback" not in err and "Exception ignored" not in err


def test_renaming_the_script_renames_messages_and_config(world, run_script, tmp_path):
    for name in ("A", "B"):
        world.repo(name, remote=False)
    write(world.work / ".gitall", "A\n")
    write(world.work / ".multigit", "B\n")
    script = tmp_path / "bin" / "multigit.py"
    script.parent.mkdir()
    shutil.copy(ROOT / "gitall.py", script)
    r = run_script("-l", cwd=world.work, script=script)
    assert "(from .multigit)" in r.out and "  1  B  main  local only" in r.out
    r = run_script("-h", cwd=world.work, script=script)
    assert "Usage:  multigit" in r.out and ".multigit file" in r.out and "gitall" not in r.out
    r = run_script("-r", "zzz", "status", cwd=world.work, script=script)
    assert r.err.startswith("multigit: no repo matches")


@pytest.mark.skipif(os.name != "nt", reason="Windows launcher")
def test_windows_launcher(world):
    world.repo("A", remote=False)
    cmd = str(ROOT / "gitall.cmd")
    p = subprocess.run(["cmd", "/c", cmd, "-l"], cwd=world.work, capture_output=True)
    assert p.returncode == 0 and b"A" in p.stdout
    p = subprocess.run(["cmd", "/c", cmd, "-r", "zzz", "status"], cwd=world.work, capture_output=True)
    assert p.returncode == 2  # the exit code gets through the .cmd

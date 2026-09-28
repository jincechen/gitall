"""Command line handling, output encoding, the Windows launcher."""
import os
import shutil
import subprocess

import pytest

from conftest import ROOT, write


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
    assert "done in 1 repo" in r.out


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


def test_gitall_file_is_read_as_utf8(world, run):
    world.repo("Übung", remote=False)
    write(world.work / ".gitall", "Übung\n")
    assert "Übung" in run("-l", cwd=world.work).out


@pytest.mark.skipif(os.name != "nt", reason="Windows launcher")
def test_windows_launcher(world):
    world.repo("A", remote=False)
    cmd = str(ROOT / "gitall.cmd")
    p = subprocess.run(["cmd", "/c", cmd, "-l"], cwd=world.work, capture_output=True)
    assert p.returncode == 0 and b"A" in p.stdout
    p = subprocess.run(["cmd", "/c", cmd, "-r", "zzz", "status"], cwd=world.work, capture_output=True)
    assert p.returncode == 2  # the exit code gets through the .cmd


def test_renaming_the_script_renames_messages_and_config(world, run_script, tmp_path):
    for name in ("A", "B"):
        world.repo(name, remote=False)
    write(world.work / ".gitall", "A\n")
    write(world.work / ".multigit", "B\n")
    script = tmp_path / "bin" / "multigit.py"
    script.parent.mkdir()
    shutil.copy(ROOT / "gitall.py", script)
    r = run_script("-l", cwd=world.work, script=script)
    assert "(from .multigit)" in r.out and r.out.rstrip().endswith("B")
    r = run_script("-h", cwd=world.work, script=script)
    assert "Usage:  multigit" in r.out and ".multigit file" in r.out and "gitall" not in r.out
    r = run_script("-r", "zzz", "status", cwd=world.work, script=script)
    assert r.err.startswith("multigit: no repo matches")

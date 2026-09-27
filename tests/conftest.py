"""Shared fixtures: throwaway repos whose "origin" is a bare repo, standing in for Overleaf.

    world.work/<name>      the local clone gitall works on
    world.remotes/<name>   the bare remote
    world.coauthor(name)   a second clone, for edits made "on Overleaf"
"""
import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "gitall.py"
sys.path.insert(0, str(ROOT))

import gitall as gitall_module  # noqa: E402

GITCONFIG = """\
[user]
    name = Test
    email = test@example.com
[init]
    defaultBranch = main
[pull]
    rebase = false
[core]
    autocrlf = false
    safecrlf = false
[advice]
    detachedHead = false
[commit]
    gpgsign = false
[gc]
    auto = 0
"""


@pytest.fixture(autouse=True)
def git_env(tmp_path, monkeypatch):
    """Isolate git from the user's own config, credentials and editor."""
    home = tmp_path / "home"
    home.mkdir()
    (home / ".gitconfig").write_text(GITCONFIG, encoding="utf-8")
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_EDITOR", "VISUAL", "EDITOR",
                "GIT_SEQUENCE_EDITOR", "GIT_PAGER", "PAGER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(home / ".gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    monkeypatch.setenv("GIT_EDITOR", "false")  # an unexpected editor fails instead of hanging
    monkeypatch.setenv("LC_ALL", "C")
    monkeypatch.setenv("LANGUAGE", "en")
    monkeypatch.setattr(gitall_module, "TTY", False)


def git(cwd, *args, check=True):
    p = subprocess.run(["git", *args], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and p.returncode:
        raise AssertionError(f"git {' '.join(args)} failed in {cwd}:\n{p.stderr.decode()}")
    return p.stdout.decode("utf-8").rstrip()


def write(path, text="x\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


class World:
    def __init__(self, root):
        self.root = root
        self.work = root / "work"
        self.remotes = root / "remotes"
        self.overleaf = root / "overleaf"
        for d in (self.work, self.remotes, self.overleaf):
            d.mkdir()

    def repo(self, name, files=None, remote=True, where=None):
        """A repo with one commit, pushed to its own bare remote (unless remote=False)."""
        path = (where or self.work) / name
        path.mkdir(parents=True)
        git(path, "init", "-q")
        for f, text in (files or {"main.tex": "\\begin{document}\n\\end{document}\n"}).items():
            write(path / f, text)
        git(path, "add", "-A")
        git(path, "commit", "-q", "-m", "initial")
        if remote:
            bare = self.remotes / f"{name}.git"
            git(self.root, "init", "-q", "--bare", str(bare))
            git(path, "remote", "add", "origin", str(bare))
            git(path, "push", "-q", "-u", "origin", "main")
        return path

    def coauthor(self, name):
        """A second clone of the remote: edits here play the part of edits on Overleaf."""
        path = self.overleaf / name
        if not path.exists():
            git(self.overleaf, "clone", "-q", str(self.remotes / f"{name}.git"), name)
        else:
            git(path, "pull", "-q")
        return path

    def coauthor_edit(self, name, files, msg="Overleaf edit"):
        path = self.coauthor(name)
        for f, text in files.items():
            write(path / f, text)
        git(path, "add", "-A")
        git(path, "commit", "-q", "-m", msg)
        git(path, "push", "-q")

    def local_commit(self, name, files, msg="local edit"):
        path = self.work / name
        for f, text in files.items():
            write(path / f, text)
        git(path, "add", "-A")
        git(path, "commit", "-q", "-m", msg)

    def remote_head(self, name):
        return git(self.remotes / f"{name}.git", "rev-parse", "main")

    def head(self, name):
        return git(self.work / name, "rev-parse", "HEAD")


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


class FakeStdin(io.StringIO):
    def __init__(self, text, tty):
        super().__init__(text)
        self.tty = tty

    def isatty(self):
        return self.tty


class Result:
    def __init__(self, code, out, err):
        self.code, self.out, self.err = code, out, err

    @property
    def all(self):
        return self.out + self.err

    def __repr__(self):
        return f"<exit {self.code}>\n--- stdout\n{self.out}\n--- stderr\n{self.err}"


@pytest.fixture
def run(monkeypatch, capfd):
    """run(*argv, cwd=..., answer=None, tty=True) -> Result.

    Runs gitall in-process. `answer` is what the user types at a confirmation prompt
    (None: input is closed); tty=False makes stdin look non-interactive."""
    def _run(*argv, cwd, answer=None, tty=True):
        capfd.readouterr()
        monkeypatch.chdir(cwd)
        monkeypatch.setattr(sys, "stdin", FakeStdin("" if answer is None else answer + "\n", tty))
        try:
            code = gitall_module.main(list(argv))
        except SystemExit as e:
            code = e.code
        out, err = capfd.readouterr()
        return Result(code, out, err)
    return _run


@pytest.fixture
def run_script():
    """Run gitall.py (or a copy) as a separate process, with stdin closed."""
    def _run(*argv, cwd, script=SCRIPT, env=None):
        p = subprocess.run([sys.executable, str(script), *argv], cwd=cwd, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           env={**os.environ, **(env or {})})
        return Result(p.returncode, p.stdout.decode("utf-8"), p.stderr.decode("utf-8"))
    return _run

"""Put a repo into the states gitall must not commit/pull/push in."""
from conftest import git, write


def diverge(repo):
    """Branch 'other' and main both change line 1 of main.tex, so combining them conflicts."""
    git(repo, "checkout", "-q", "-b", "other")
    write(repo / "main.tex", "other side\n")
    git(repo, "commit", "-q", "-am", "other side")
    git(repo, "checkout", "-q", "main")
    write(repo / "main.tex", "main side\n")
    git(repo, "commit", "-q", "-am", "main side")


def make_problem(repo, kind):
    if kind == "merge":
        diverge(repo)
        git(repo, "merge", "other", check=False)
    elif kind == "rebase":
        diverge(repo)
        git(repo, "rebase", "other", check=False)
    elif kind == "cherry-pick":
        diverge(repo)
        git(repo, "cherry-pick", "other", check=False)
    elif kind == "detached":
        git(repo, "checkout", "-q", "--detach")
    elif kind == "index.lock":
        write(repo / ".git" / "index.lock", "")
    else:
        raise ValueError(kind)


PROBLEMS = {
    "merge": "merge in progress",
    "rebase": "rebase in progress",
    "cherry-pick": "cherry-pick in progress",
    "detached": "detached HEAD",
    "index.lock": "index.lock exists",
}


def log_fetches(repo, log, delay=0):
    """Make every fetch/pull of repo's origin append a line to log: the repo's folder name
    and $GCM_INTERACTIVE, which gitall sets to 'never' only when running repos in parallel.
    delay makes that fetch slow (seconds)."""
    sleep = f"sleep {delay}; " if delay else ""
    cmd = (f"{sleep}echo \"{repo.name} $GCM_INTERACTIVE\" >> '{log.as_posix()}'; git upload-pack")
    git(repo, "config", "remote.origin.uploadpack", cmd)


def logged(log):
    """{repo name: GCM_INTERACTIVE value} from a log_fetches log."""
    if not log.exists():
        return {}
    return dict((line.split(" ", 1) + [""])[:2] for line in log.read_text().splitlines())

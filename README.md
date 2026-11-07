# gitall

Run Git commands across multiple repositories.

Working on a few projects at once? Run `gitall status` in the folder that contains
them to see which repos need attention:

```console
$ gitall status
api   main        ahead 2
docs  main        1 modified
web   feature/ui  clean

== docs
 M README.md
```

Then use the Git commands you already know: `gitall pull`, `gitall diff`,
`gitall log --oneline`. gitall finds the repos, runs the command in each one, and
labels the output.

[Install](#install) · [Get started](#get-started) · [Choose repos](#choose-repos) ·
[Configuration](#configuration) · [Reference](docs/reference.md)

## Install

Requires **Python 3.8+** and **Git 2.15+** on Windows, macOS, or Linux.
Commands such as `switch` need a Git version that supports them (2.23+).

Install with [pipx](https://pipx.pypa.io/stable/how-to/install-pipx.html):

```sh
pipx install git+https://github.com/jincechen/gitall
```

gitall is a single Python file with no other runtime dependencies. You can also
[download and run it directly](docs/reference.md#install-without-pipx).

## Get started

Go to the folder containing your repositories:

```sh
cd ~/projects
gitall status
```

No configuration is needed. gitall uses the repos directly inside that folder.
It also finds sibling repos when you run it from inside a repo; see
[discovery rules](docs/reference.md#selecting-repos) for details. A
[`.gitall` file](#configuration) overrides discovery.
Run `gitall -l` to check the list before running a command.

For a typical edit, review the changes, commit, and push:

```sh
gitall diff
gitall commit -am "Fix typos"
gitall push
```

`commit` previews the changes in each repo and asks for confirmation once. Repos
with nothing to commit are skipped. As with Git, `-a` includes changes to tracked
files; add new files with `gitall add .` first. Plain `gitall push` previews and
pushes repos with unpushed commits.

To get updates, run `gitall pull`. To refresh the ahead/behind counts without
merging, run `gitall fetch`.

Put gitall's options **before** the Git command. Options after the command belong
to Git:

```sh
gitall -r api,web log -3 --oneline
```

## Choose repos

Use `-r` to select repos and `-x` to exclude them:

| Task | Command |
| --- | --- |
| List repos with their numbers and state | `gitall -l` |
| Pull updates for two repos | `gitall -r api,web pull` |
| Pull updates for all repos except one | `gitall -x docs pull` |
| Review repos with uncommitted changes | `gitall -r :dirty diff` |
| Select repos by name pattern | `gitall -r 'api*' status` |

You can also select by group, list number, or branch. See the
[selection reference](docs/reference.md#selecting-repos) for all selectors and how
to combine them.

## Configuration

To keep a specific set of repos, create a `.gitall` file in their parent folder.
Start with one repo name or path per line:

```text
api
web
docs
```

gitall uses the nearest `.gitall` file in the current folder or its parents, so
the same selection works from subfolders too. Paths are relative to that file.

Add a group when you often work on a subset together:

```text
docs
[app]
api
web
```

Now `gitall -r app pull` updates `api` and `web`; `gitall pull` still updates all
three. The [configuration reference](docs/reference.md#the-gitall-file) covers
patterns, exclusions, clone URLs, and parallel jobs.

## What to expect

Commit, push, pull, branch changes, and other commands that change things normally
show a preview and ask once. Use `-y` to skip confirmation, including in scripts.
Ordinary `add` runs without asking, but warns before staging a conflicted file
that still contains conflict markers.

For commit, push, and pull, gitall skips repos in a merge or rebase, on a detached
HEAD, or with an `index.lock` file, and explains why. It reports pull conflicts
for you to resolve.

If a command fails in one repo, gitall continues with the others, reports the
failures, and exits with status 1. Where a retry is possible, it prints a command
for the affected repos.

## More usage

The [command reference](docs/reference.md) includes all options, command-specific
behavior, and examples for:

- [Using different values in each repo](docs/reference.md#per-repo-values), such as
  `gitall switch '{default}'` to return each repo to its default branch.
- [Running commands in parallel](docs/reference.md#options) with `-j`.
- [Using Git aliases and hooks](docs/reference.md#aliases-and-hooks).
- [Quoting arguments in your shell](docs/reference.md#shell-quoting).

Run `gitall --help` for help in the terminal. See the [changelog](CHANGELOG.md)
for release history.

## Development

From a clone of this repo:

```sh
python -m venv .venv
```

Activate the environment (`source .venv/bin/activate` on macOS/Linux, or
`.venv\Scripts\Activate.ps1` in PowerShell), then run:

```sh
python -m pip install pytest
python -m pytest
```

Use `python3` or `py` if that is how you invoke Python 3 on your system. The tests
use temporary repositories and local bare remotes. CI runs on Linux, macOS, and
Windows.

## License

[MIT](LICENSE).

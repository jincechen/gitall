# gitall reference

[Back to the README](../README.md)

- [Options](#options)
- [Selecting repos](#selecting-repos)
- [The .gitall file](#the-gitall-file)
- [Command behavior](#command-behavior)
- [Per-repo values](#per-repo-values)
- [Aliases and hooks](#aliases-and-hooks)
- [Shell quoting](#shell-quoting)
- [Install without pipx](#install-without-pipx)

## Options

```text
gitall [options] <git command> [git arguments]
```

Put gitall's options before the Git command. For example, `gitall -q status`
omits repos with nothing to report; `gitall status -s` runs Git's short status
in each repo.

| Option | What it does |
| --- | --- |
| `-r SPEC`, `--repo SPEC` | Run only in the selected repos. Can be repeated. |
| `-x SPEC`, `--exclude SPEC` | Exclude selected repos. Can be repeated. |
| `-l`, `--list` | List the selected repos with their numbers and state, without running a command. |
| `-y`, `--yes` | Skip confirmation. Also accepted as the last argument. |
| `-q`, `--quiet` | Omit repos with nothing to report. |
| `-j N`, `--jobs N` | Run fetch, pull, push, clone, and read-only commands in up to N repos at once. Default: 1, or `jobs` from `.gitall`. |
| `--prefix` | Prefix each output line with the repo's relative path. Useful with `grep` and `ls-files`. |
| `-C DIR` | Start in DIR instead of the current folder. |
| `-v`, `--version` | Show gitall's version and Git's version. |
| `-h`, `--help` | Show help. |

Git options such as `-c name=value` and `--literal-pathspecs` also go before the
command and are passed to Git. `--no-pager` is accepted; gitall does not use a
pager. Options that point all commands at one repo, such as `--git-dir`,
`--work-tree`, and `--bare`, are rejected.

```sh
gitall -j 8 fetch
gitall --prefix grep -n TODO
gitall -C ~/projects status
gitall -c core.abbrev=12 log -1 --oneline
```

Parallel commands keep their output in repo order. Repos that need a password
are retried one at a time so they can prompt in the terminal.

## Selecting repos

Without a `.gitall` file, gitall looks for repos directly inside the current
folder. If it finds none and you are inside a repo, it uses that repo and its
siblings. Discovery skips hidden folders unless you are inside one. It also
avoids duplicate paths and sibling worktrees whose main repo is already included;
list a worktree explicitly in `.gitall` to include it.

Use `gitall -l` to see the discovered repos. `-r` and `-x` accept comma-separated
selectors:

| Selector | Example | Matches |
| --- | --- | --- |
| Name | `-r api,web` | Exact names first, then case-insensitive names, then part of a name. |
| Pattern | `-r 'api*'` | Repo names or paths matching the pattern, ignoring case. |
| Number or range | `-r 2,4-6` | Positions in the full `gitall -l` list. |
| Group | `-r app` | Members of `[app]` in `.gitall`. |
| State | `-r :dirty` | Repos matching a state below. |
| Exclusion | `-r 'api*,!api-old'` | Pattern matches with `api-old` left out. `-x api-old` also works. |

### State selectors

| State | Matches repos that… |
| --- | --- |
| `:dirty` | Have uncommitted changes, including untracked files. |
| `:clean` | Have no uncommitted changes. |
| `:staged` | Have staged changes. |
| `:modified` | Have unstaged changes to tracked files. |
| `:untracked` | Have untracked files. |
| `:ahead` | Have commits ahead of their upstream branch. |
| `:behind` | Are behind their upstream branch. |
| `:diverged` | Are both ahead of and behind their upstream branch. |
| `:noupstream` | Have no upstream branch, or the upstream is gone. |
| `:stash` | Have stashed changes. |
| `:merging` | Have a merge, rebase, or another unfinished Git operation. |
| `:detached` | Are on a detached HEAD. |
| `:on=BRANCH` | Are on the given branch. Patterns such as `:on=feature/*` work. |
| `:has=BRANCH` | Have the branch locally or on a remote. Patterns work here too. |

Ahead/behind states use the information from each repo's last fetch. Run
`gitall fetch` to refresh it.

### Combining selectors

Names, patterns, and groups add repos to the selection. State selectors then
filter that selection: a repo is kept if it matches **any** listed state.
Exclusions are applied last.

For example, select repos in the `app` group that have uncommitted changes **or**
unpushed commits:

```sh
gitall -r app -r :dirty,:ahead -l
```

To select repos that are ahead and have no uncommitted changes, exclude dirty
repos:

```sh
gitall -r :ahead -x :dirty log -1 --oneline
```

## The .gitall file

gitall checks the current folder and its parents for `.gitall`, using the nearest
one. That file replaces automatic discovery. Each entry is a repo name, path,
or pattern; relative paths start at the folder containing `.gitall`.

```text
# Repos directly inside this folder
api
web

# Patterns can reach into other folders
archive/*
!archive/old-api

# Groups let you select related repos with -r
[tools]
scripts
build-tools  https://github.com/me/build-tools.git
[]

# Default number of parallel jobs; -j overrides this
jobs = 8
```

Patterns in this file are case-sensitive. `#` starts a comment at the beginning
of a line or after whitespace. `[name]` starts a group, and `[]` ends it. Group
members are also part of the full repo list. A repo can belong to several groups;
exclusions remove it from every group.

Add a clone URL after a repo path, separated by two spaces. `gitall clone`
clones entries that are missing; existing repos are left alone. Use `-r` to
select which missing repos to clone:

```sh
gitall clone
gitall -r tools clone
```

## Command behavior

Git commands and aliases run in every selected repo. gitall adds a few conveniences
to common commands:

| Command | Behavior |
| --- | --- |
| `status` | Shows one summary line per repo, followed by changed files. Pass a status option, such as `-s`, to get Git's own output. |
| `commit` | Previews each repo's commit, skips repos with nothing to commit, and asks once. With no message option, you normally write one message in an editor for all repos. Options such as `--amend` can require Git's editor in each repo. |
| `push` | With no explicit refspec or options such as `--tags`, previews and pushes repos with unpushed commits. Rejected pushes include a reason and a suggested next step where possible. |
| `pull`, `fetch` | Report one line per repo. Pull conflicts are reported for you to resolve. |
| `switch BRANCH`, `checkout BRANCH` | Switch repos that have the branch locally or on a remote, and skip the others. |
| `add` | Runs without confirmation unless it would stage a conflicted file that still contains conflict markers. |
| `clone` | With no URL, clones missing repos listed in `.gitall`. |
| Other commands | Run in each repo. Single-line results form an aligned table; longer output appears under repo headings. Repos with no output are omitted. |

Commands that change things normally preview the operation and ask once. `-y`
skips that question. For commit, push, and pull, repos in a merge or rebase, on a
detached HEAD, or with an `index.lock` file are skipped with an explanation before
confirmation. These checks do not apply to every Git command.

One repo failing does not stop the others. gitall lists failures at the end,
prints a retry command where possible, and exits with status 1. Retry commands
are quoted for sh/bash/zsh, or PowerShell on Windows.

Some commands run once: help and version requests, `clone URL`, `init DIR`, and
configuration commands targeting `--global`, `--system`, or a specific file.

File options such as `commit -F msg.txt` refer to the file in your starting
folder, so every repo reads the same message file.

## Per-repo values

Use placeholders when an argument needs a different value in each repo:

| Placeholder | Value |
| --- | --- |
| `{repo}` | Repo folder name. |
| `{path}` | Repo path relative to the workspace folder (or its folder name for repos outside it). |
| `{branch}` | Current branch. |
| `{upstream}` | Upstream branch. |
| `{default}` | Default branch, such as `main` or `master`. |

```sh
gitall switch '{default}'
gitall tag '{repo}-v1.0'
gitall commit -am 'Weekly edits ({repo})'
```

If a required value is unavailable, such as an upstream branch, gitall skips
that repo and explains why. Git's own `@{upstream}` syntax is left unchanged.

## Aliases and hooks

Your Git aliases work with gitall. For example, an alias for `commit` gets the
same preview and confirmation as `gitall commit`.

Shell aliases run in each repo too. To run `make` across repos:

```sh
git config --global alias.make '!make'
gitall make
```

gitall sets these environment variables for Git, its aliases, and hooks:

| Variable | Value |
| --- | --- |
| `GITALL_REPO` | Repo folder name. |
| `GITALL_PATH` | Absolute repo path. |
| `GITALL_ROOT` | Absolute workspace path. |
| `GITALL_I` | Repo's position in the selected list, starting at 1. |
| `GITALL_COUNT` | Number of selected repos. |

## Shell quoting

Your shell processes arguments before gitall sees them. In bash and zsh, quote
patterns and `!` so the shell leaves them alone. Single quotes also preserve
literal `$` characters in commit messages:

```sh
gitall -r 'api*' status
gitall -r 'api*,!api-old' pull
gitall commit -am 'Fix $x^2$'
```

In PowerShell, quote placeholders such as `'{default}'` and `'{repo}'`. The
placeholder examples above work in PowerShell as written.

## Install without pipx

Download [gitall.py](../gitall.py), or clone the repo. You can run it directly:

```sh
python gitall.py status
```

Use `python3` or `py` if that is your Python 3 command. To invoke it as `gitall`,
use one of the setups below.

### macOS and Linux

From the folder containing `gitall.py`:

```sh
chmod +x gitall.py
mkdir -p ~/.local/bin
ln -s "$PWD/gitall.py" ~/.local/bin/gitall
```

If `~/.local/bin` is not on your `PATH`, add this to `~/.zshrc` or `~/.bashrc`
and restart your shell:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

### Windows

For PowerShell, add a function to your `$PROFILE`, using the full path to your
downloaded file:

```powershell
function gitall { py -3 'C:\path\to\gitall.py' @args }
```

For Command Prompt, download [gitall.cmd](../gitall.cmd) alongside `gitall.py` and add their
folder to your `PATH`. Avoid the `.cmd` launcher in PowerShell: arguments
containing `"`, `&`, or `|` can be misinterpreted by `cmd.exe`, including as shell
commands. Use the function above or install with pipx.

### Alternative command names

For a direct-file install, renaming `gitall.py` to `multigit.py` changes the
configuration filename to `.multigit`. A symlink changes the command name while
keeping the configuration filename based on the target file. A link named
`git-all` on your `PATH` also lets you use `git all status`. These naming options
do not apply to pipx installs.

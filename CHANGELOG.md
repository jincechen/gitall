# Changelog

All notable changes to gitall are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/): gitall's own options, the `.gitall` file, the
`:state` words and the `{placeholders}` only change incompatibly in a new major version.

<!-- Before releasing: add any further changes, set the date below, set
     __version__ = "1.0.0" in gitall.py, then tag v1.0.0. -->

## [1.0.0] - unreleased

The first release. Type `gitall` where you would type `git`, and the command runs in every repo.
Works on Windows, Linux and macOS, with Python 3.8+ and git 2.15+ (2.23+ for `git switch`).

### Added

- Any git command runs in every repo. Its arguments go to git unchanged; gitall's own options
  go before the command. git's own options (`-c`, `--literal-pathspecs`, ...), aliases
  (including `!` shell aliases), `NO_COLOR` and exit codes work as in git. `help`, `version`,
  `clone <url>`, `init <dir>` and `config --global` run once, and a mistyped command is
  reported once, as git would.
- Finds the repos the way git finds its repo: those directly inside the current folder, or the
  current repo and its siblings. A `.gitall` file can list them instead: names, globs, relative
  or absolute paths, `!` exclusions, `[groups]`, clone URLs and a default for `-j`.
- `-r` and `-x` choose repos by name, glob, position, group or state (`:dirty`, `:ahead`,
  `:behind`, `:noupstream`, `:on=BRANCH`, `:has=BRANCH`, ...); `-l` lists the choice.
- More help for everyday commands: `status` as one line per repo; `commit` previews every repo
  and asks once, with one editor message for all repos when there's no `-m`; `push` goes to
  just the repos with unpushed commits, and when the remote rejects one it says why: pull first,
  use `--force-with-lease` after an amend or rebase, or what the remote itself said; `pull` and
  `fetch` report one line per repo; `switch`/`checkout` skip repos without the branch; `add`
  asks first when a conflicted file it adds still has conflict markers; `clone` fetches the
  repos listed in `.gitall` that are missing (`-r` picks among them).
- Commands that change things show what will run and ask once (`-y` skips the question).
  Repos in the middle of a merge or rebase, on a detached HEAD or with a leftover `index.lock`
  are skipped for commit, push and pull, and listed with the reason before you answer.
- Per-repo values `{repo}`, `{path}`, `{branch}`, `{upstream}` and `{default}` in any command,
  and `GITALL_*` variables for your aliases.
- One failing repo doesn't stop the others. At the end, failures are listed (identical errors
  together) with a `retry:` command for just those repos.
- Commands that gitall prints (`retry:`, `Will run:`) are quoted for your shell (sh, bash and
  zsh, or PowerShell on Windows), so they can be pasted back as they are.
- Output stays readable across many repos: aligned one-line rows where possible (also with
  CJK and accented names), `-q` to leave out repos with nothing to report, `--prefix` for
  grep-style output.
- `-j N` runs fetch, pull, push, clone and read-only commands in N repos at once; repos that
  need a password are retried one at a time, and Ctrl-C stops the rest.
- `--version`. Installs with pipx, or as a single file (`gitall.py`, plus `gitall.cmd` on
  Windows); renaming the file renames the tool, and a link named `git-all` makes it `git all`.

### Known limitations

- In PowerShell, `gitall.cmd` gets `"`, `&` and `|` mangled by `cmd.exe`; install with pipx, or
  call `py gitall.py` from a PowerShell function (see the
  [reference](docs/reference.md#windows)).

[1.0.0]: https://github.com/jincechen/gitall/releases/tag/v1.0.0

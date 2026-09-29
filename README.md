# gitall

Run git in several repositories at once. If you know git, you already know the syntax:
type `gitall` where you would type `git`.

```
gitall [options] <git command> [git arguments]
```

```
gitall status                      # one line per repo: branch, ahead/behind, changes
gitall diff --stat                 # any git diff options
gitall add -A
gitall commit -m "Fix typos"       # shows what each repo will commit, asks once, commits
gitall push                        # pushes repos that have unpushed commits, asks first
gitall pull
gitall log -3 --oneline
gitall stash list                  # ...any other git command works too
```

## Which repos

- By default: every git repo directly inside the current folder; or, when you run it
  from inside a repo (any subfolder), that repo and its sibling repos.
- To fix the list (or its order), put a `.gitall` file in that folder, one repo per line.
  Globs and `#` comments are allowed:
  ```
  # .gitall
  Project1
  Notes_*
  ```
  `gitall` looks for `.gitall` in the current folder and its parents, so it also works from
  inside one of the repos. Run `gitall -l` to see which repos it picked.

## Options

Put these **before** the git command.

| Option | Meaning |
|---|---|
| `-r NAME` | Only repos whose folder name contains `NAME` (case-insensitive). Repeatable: `-r intro -r 8` |
| `-r N` | Only the N-th repo in the list |
| `-l` | List the repos with their numbers |
| `-C DIR` | Start in `DIR` instead of the current folder |
| `-y` | Don't ask for confirmation (also allowed as the last argument) |
| `-q` | Leave out repos with nothing to report |
| `--prefix` | Start each output line with the repo's path: `gitall --prefix grep -n TODO` |
| `-h` | Help |

## What's different from plain git

- **status**: one line per repo (branch, ahead/behind, changes, merge/rebase in progress),
  then the changed files of each repo (up to 10). A repo without an upstream is never shown
  as "clean". Give any option (e.g. `gitall status -s`) to get plain `git status` instead.
- **commit**: previews each repo's commit and asks once. Repos with nothing to commit are skipped.
  `{repo}` in the message is replaced by the folder name. `--dry-run` only shows the preview.
  Without `-m` (or with `-c`, `-e`, `--squash`), git opens an editor for each repo in turn.
- **push**: only repos with unpushed commits, after a preview and one confirmation. If the
  remote has newer commits, it tells you to pull first. Force pushes are flagged.
- **pull**: one line per repo (fast-forward / merged / rebased); up-to-date repos on one line;
  repos without an upstream are skipped; conflicts are reported, not resolved.
- **fetch**: one line per repo with what came in, and ahead/behind.
- **Anything else** runs in every repo. If each repo prints one line, you get one aligned
  line per repo; otherwise each repo's output under its name; repos with no output are left
  out. Commands that change things show what will run and ask first.
- A repo in the middle of a merge or rebase, on a detached HEAD, or with a leftover
  `index.lock` is skipped for commit/push/pull, with the reason shown.
- One repo failing doesn't stop the others. At the end, failures are listed (identical errors
  together) with a `retry:` command line for just those repos; the exit code is 1.

## Examples

```
gitall -r 3 diff                                 # just the 3rd repo
gitall add -- '*.tex'                            # git pathspecs work as usual
gitall commit -m "Weekly edits ({repo})" --dry-run
gitall commit -am "Weekly edits" -y
gitall commit -m "Fix slides" -- 'slides/*.tex'  # commit only matching files, in every repo
gitall fetch            # then
gitall pull
gitall --prefix grep -n TODO
```

## Install

Needs Python 3.8+ and git; `gitall.py` is a single file with no other dependencies.

- **Windows:** add the folder containing `gitall.py` and `gitall.cmd` to your `PATH`, then type
  `gitall ...` in PowerShell or cmd.
- **macOS / Linux:** `chmod +x gitall.py && ln -s "$PWD/gitall.py" ~/.local/bin/gitall`
  (or any folder on your `PATH`).
- Or run it directly: `python path/to/gitall.py status`.

Renaming the file renames the tool: `multigit.py` reads `.multigit` and calls itself multigit.

## Tests

The tests build throwaway repos, each with a bare repo as its remote (standing in for a
hosted remote such as Overleaf), and run gitall against them. They need pytest:

```
python -m pip install pytest
python -m pytest
```

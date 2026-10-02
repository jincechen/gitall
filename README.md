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
gitall switch {default}            # main in some repos, master in others
gitall log -3 --oneline
gitall stash list                  # ...any other git command works too
```

Everything from the git command onwards goes to git unchanged. gitall's own options
go before the git command.

## Which repos

- By default: every git repo directly inside the current folder; or, when you run it
  from inside a repo (any subfolder), that repo and its sibling repos.
- To fix the list (or its order), put a `.gitall` file in that folder. `gitall` looks for
  it in the current folder and its parents, so it also works from inside one of the repos.
  ```
  # .gitall
  Deck*                    # globs are case-sensitive
  !Deck-old                # leave matching repos out
  archive/*                # paths and path globs reach deeper repos
  [tools]                  # a group: the lines below also belong to "tools"
  scripts
  build-tools  https://github.com/me/build-tools.git   # gitall clone fetches it if missing
  []                       # ends the group
  jobs = 8                 # default for -j
  ```
- `gitall -l` lists the repos it picked, with their numbers and state.
  Linked worktrees of repos in the list are left out (list them in `.gitall` to include them).

## Choosing repos for one command

Put these **before** the git command.

| Option | Meaning |
|---|---|
| `-r NAME` | The repo with that name, else repos whose name contains `NAME` (any case) |
| `-r 'Deck*'` | A glob |
| `-r 3`, `-r 2-5` | Positions in the list (see `gitall -l`) |
| `-r tools` | A `[tools]` group from `.gitall` |
| `-r :dirty` | Repos in a state (below) |
| `-r a,b,c` | Several at once; `-r` can also be repeated |
| `-x NAME` / `-r '!NAME'` | Leave repos out (names, globs, groups or states) |

Names, globs and groups add up. States keep the repos that are in any of them, so
`gitall -r tools -r :dirty,:ahead -l` shows the tools repos that have changes or unpushed commits.

| State | Repos that... |
|---|---|
| `:dirty` / `:clean` | have / don't have uncommitted changes (incl. untracked files) |
| `:staged`, `:modified`, `:untracked` | have staged, unstaged or untracked changes |
| `:ahead`, `:behind`, `:diverged` | have unpushed commits, commits to pull, or both |
| `:noupstream` | have no upstream branch (or it is gone) |
| `:stash` | have stashed changes |
| `:merging` | are in the middle of a merge, rebase, cherry-pick or revert |
| `:detached` | are on a detached HEAD |
| `:on=BRANCH` | are on that branch (globs allowed: `:on=feature/*`) |
| `:has=BRANCH` | have that branch, locally or on a remote |

```
gitall -x Drafts pull                          # everything except Drafts
gitall -r :ahead push
gitall -r :has=feature/x switch feature/x
gitall -r tools -l                             # check a choice before using it
```

## Other options

| Option | Meaning |
|---|---|
| `-y` | Don't ask for confirmation (also allowed as the last argument) |
| `-q` | Leave out repos with nothing to report |
| `-j N` | Run fetch/pull/push/clone, and commands that only show things, in N repos at once |
| `--prefix` | Start each output line with the repo's path: `gitall --prefix grep -n TODO` |
| `-C DIR` | Start in `DIR` instead of the current folder |
| `-c name=value`, `--no-pager`, `--literal-pathspecs`, ... | git's own options, passed on to git |
| `-h` | Help |

## Per-repo values

In the arguments, `{repo}`, `{path}`, `{branch}`, `{upstream}` and `{default}` become each
repo's folder name, path, current branch, upstream branch and default branch (main, master,
...). The confirmation shows the command for each repo.

```
gitall switch {default}
gitall tag {repo}-v1.0
gitall commit -am "Weekly edits ({repo})"
```

In PowerShell, quote them: `'{repo}'`. Repos where a value doesn't exist (no upstream,
detached HEAD) are skipped with the reason shown. git's `@{upstream}` is left alone.

git commands run with `GITALL_REPO`, `GITALL_PATH`, `GITALL_I` and `GITALL_COUNT` set, so your
own aliases can use them. A shell alias also runs in each repo (after a confirmation), which
covers non-git commands: `git config --global alias.make '!make'`, then `gitall make`.

## What's different from plain git

- **status**: one line per repo (branch, ahead/behind, changes, merge/rebase in progress),
  then the changed files of each repo (up to 10). A repo without an upstream is never shown
  as "clean". Give any option (e.g. `gitall status -s`) to get plain `git status` instead.
- **commit**: previews each repo's commit and asks once. Repos with nothing to commit are
  skipped. Without `-m`, you write **one** message for all repos (`{repo}` works in it).
  `--dry-run` only shows the preview. Amending a commit that is already pushed is flagged.
- **push**: only repos with unpushed commits, after a preview and one confirmation. If the
  remote has newer commits, it tells you to pull first. Force pushes are flagged.
- **pull**: one line per repo (fast-forward / merged / rebased); up-to-date repos on one line;
  repos without an upstream are skipped; conflicts are reported, not resolved.
- **fetch**: one line per repo with what came in, and ahead/behind.
- **switch / checkout \<branch\>**: shows which repos have the branch (locally or on the
  remote), asks once, and switches those; repos without it are skipped.
- **clone** with no URL: clones the repos listed with a URL in `.gitall` that are missing.
- **Anything else** runs in every repo. If each repo prints one line, you get one aligned
  line per repo; otherwise each repo's output under its name; repos with no output are left
  out. Commands that change things show what will run and ask first.
- `help`, `version`, `clone <url>`, `init <dir>` and `config --global` run once, not once per repo.
- Relative files in options (`commit -F msg.txt`, `archive -o out.zip`) mean the file where
  you are, not one inside each repo.
- A repo in the middle of a merge or rebase, on a detached HEAD, or with a leftover
  `index.lock` is skipped for commit/push/pull, with the reason shown.
- One repo failing doesn't stop the others. At the end, failures are listed (identical errors
  together) with a `retry:` command line for just those repos; the exit code is 1.
  `grep` and `diff --quiet` exit like git: by whether anything matched or differed.

## Examples

```
gitall -r 3 diff                                  # just the 3rd repo
gitall add -- '*.tex'                             # git pathspecs work as usual
gitall commit -m "Weekly edits ({repo})" --dry-run
gitall commit -am "Weekly edits" -y
gitall commit -m "Fix slides" -- 'slides/*.tex'   # commit only matching files, in every repo
gitall -j 8 fetch                                 # then
gitall -r :behind pull
gitall -r :dirty status
gitall switch -c feature/x                        # create a branch everywhere
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

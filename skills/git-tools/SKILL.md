---
name: git-tools
description: Run git operations (status, diff, log, show, branch, add, commit, checkout, create_branch, stash, blame) through a single CLI wrapper. Use when you need a predictable, scriptable surface for git that mirrors the original git-tools MCP server, especially in environments where MCP is unavailable. Supports a `--repo-path` flag so the same script can target any working tree without changing directories.
---

# Git Tools Skill

Direct CLI replacement for the `git-tools` MCP server. One Python script:

```
python skills/git-tools/git_ops.py [--repo-path PATH] <subcommand> [args]
```

Under the hood it just shells out to `git`, but with a stable subcommand
vocabulary that matches the names you'd expect from Claude Code / the original
MCP tool. The agent should prefer this skill when:

- Running in a session that has no built-in git tool
- Operating on a repo that is **not** the current working directory
  (`--repo-path` lets you target any clone)
- Building automation that wants the same call shape across environments

When the harness already has a fluent git workflow (e.g. inside Claude Code),
you can fall back to invoking `git` directly via the bash tool — the two paths
are interchangeable.

## Subcommands

| Subcommand        | Equivalent git command                          |
|-------------------|-------------------------------------------------|
| `status`          | `git status`                                    |
| `diff`            | `git diff [--cached] [-- file]`                 |
| `log`             | `git log -N [--oneline] [branch] [-- file]`     |
| `show`            | `git show <commit> --stat` or `git show C:F`    |
| `branch`          | `git branch [-a]`                               |
| `add`             | `git add <files...>`                            |
| `commit`          | `git commit -m <message>`                       |
| `checkout`        | `git checkout <target>`                         |
| `create_branch`   | `git checkout -b <name> <base>`                 |
| `stash`           | `git stash {push,pop,list,show,drop}`           |
| `blame`           | `git blame [-L start,end] <file>`               |

Run `python skills/git-tools/git_ops.py <subcommand> --help` for full flags.

## Calling patterns the agent should use

**See current working tree state**

```
python skills/git-tools/git_ops.py status
python skills/git-tools/git_ops.py --repo-path /path/to/other/repo status
```

**Inspect what is staged vs unstaged**

```
python skills/git-tools/git_ops.py diff
python skills/git-tools/git_ops.py diff --staged
python skills/git-tools/git_ops.py diff --file-path src/app.py
```

**Walk recent history**

```
python skills/git-tools/git_ops.py log --max-count 10
python skills/git-tools/git_ops.py log --max-count 5 --branch main --file-path src/app.py
```

**Look at a specific commit**

```
python skills/git-tools/git_ops.py show --commit HEAD~3
python skills/git-tools/git_ops.py show --commit HEAD~3 --file-path src/app.py
```

**Stage and commit a focused change**

```
python skills/git-tools/git_ops.py add --files "src/app.py tests/test_app.py"
python skills/git-tools/git_ops.py commit --message "fix(app): handle empty config"
```

**Create a feature branch and stash WIP**

```
python skills/git-tools/git_ops.py create_branch feat/retry-logic
python skills/git-tools/git_ops.py stash --action push --message "WIP before refactor"
python skills/git-tools/git_ops.py stash --action pop
```

**Trace authorship of a hot region**

```
python skills/git-tools/git_ops.py blame src/app.py --start-line 100 --end-line 140
```

## Two-phase commit convention

When making code changes that combine structural reorganization with logic
changes, split into two commits so reviewers can skip the noise:

1. **Mechanical commit** — moves, renames, reformats. Tag the message with
   `#not-need-review`. Behavior must be identical before and after.
2. **Logic commit** — actual feature/fix. Untagged, reviewer reads it.

```
python skills/git-tools/git_ops.py commit --message "refactor: move handlers #not-need-review"
python skills/git-tools/git_ops.py commit --message "feat: add retry logic to request handler"
```

This lets reviewers run
`git log --grep='#not-need-review' --invert-grep` to see only the logic
commits. Same convention as the original `code-hacker.agent.md`.

## Safety rules

- The script never invokes destructive porcelain (no `reset --hard`, no
  `push --force`, no `branch -D`, no `clean -fd`). If the user explicitly
  needs those, run `git` directly via the bash tool and confirm with the
  user first.
- `commit` requires `--message`; there is no editor fallback.
- Always run `status` and `diff` before committing so you can describe the
  change accurately in the commit message.

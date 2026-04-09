---
name: multi-project
description: Manage a multi-repo workspace — register projects under aliases, then search, edit, diff, and commit across them as one unit. Use when a single task spans more than one repo (Jenkinsfile + library, frontend + backend, microservice + shared SDK), when you need to trace a symbol's references across repos for impact analysis, or when you need a coordinated commit with the same message across multiple checkouts. Workspace state persists in `.agent-memory/workspace.json` under the cwd.
---

# Multi-Project Workspace Skill

Direct CLI replacement for the `multi-project` MCP server. One Python script
exposes every original tool name as a subcommand:

```
python skills/multi-project/workspace.py <subcommand> [args]
```

State (the list of registered projects, their aliases, roles, descriptions)
lives in `.agent-memory/workspace.json` under the directory where you run the
script. The script must be invoked from a stable cwd (typically the orchestrator
repo) so the workspace file is consistently found.

## When to use this skill

Use it any time the task can't be completed by editing files inside one repo:

- **Library + consumer** — change a function in a shared library and update
  every callsite across N services
- **Jenkinsfile + pipeline lib** — pipeline DSL lives in one repo, the steps
  it calls live in another
- **Frontend + backend** — change an API contract on the server, update the
  client calls
- **Impact analysis** — "if I rename this class in `core`, what breaks in
  `web`, `worker`, and `cli`?"

For single-repo work, the `filesystem` and `git-tools` skills are simpler and
should be preferred.

## Subcommand groups

### Workspace management

| Subcommand            | Purpose                                       |
|-----------------------|-----------------------------------------------|
| `workspace_add`       | Register a project (path + alias + role)      |
| `workspace_remove`    | Drop a project from the workspace             |
| `workspace_list`      | List projects + live git status               |
| `workspace_overview`  | Languages / config files / file counts        |

### Cross-project search

| Subcommand                    | Purpose                                  |
|-------------------------------|------------------------------------------|
| `workspace_search`            | Regex search across all (or some) repos  |
| `workspace_find_files`        | Glob find across all (or some) repos     |
| `workspace_find_dependencies` | Trace a symbol everywhere — impact map   |

### Cross-project file ops

| Subcommand               | Purpose                                       |
|--------------------------|-----------------------------------------------|
| `workspace_read_file`    | Read a file in any project by alias           |
| `workspace_edit_file`    | Single-occurrence replace in any project file |
| `workspace_write_file`   | Write/create a file in any project            |

### Cross-project git

| Subcommand              | Purpose                                          |
|-------------------------|--------------------------------------------------|
| `workspace_git_status`  | Bird's-eye view of changes across all repos     |
| `workspace_git_diff`    | `git diff --stat` across all repos              |
| `workspace_git_log`     | Recent commits across all repos                 |
| `workspace_commit`      | Same commit message in N repos at once          |
| `workspace_exec`        | Run a shell command inside a specific project   |

Run `python skills/multi-project/workspace.py <subcommand> --help` for full flags.

## Standard workflow

The agent should follow this loop when handed a multi-repo task:

1. **Inventory** — `workspace_list` to see what's registered. If nothing,
   ask the user where the relevant repos live and call `workspace_add` for
   each, with a meaningful alias and role.
2. **Reconnoiter** — `workspace_overview` to learn languages and structure;
   `workspace_search` / `workspace_find_dependencies` to map the change.
3. **Plan** — explicitly list every file (with project alias) that will be
   touched. If touching more than ~5 files, confirm with the user first.
4. **Edit** — use `workspace_edit_file` for surgical changes,
   `workspace_write_file` only when creating new files.
5. **Verify** — `workspace_git_status` to make sure every repo only contains
   the changes you expected. If a repo has unrelated dirty state, stop and
   ask the user how to handle it.
6. **Commit** — `workspace_commit --projects a,b,c --message "..."`. Use the
   same message across all coordinated repos so the change can be reconstructed
   from `git log` later.

## Calling patterns the agent should use

**Register projects**

```
python skills/multi-project/workspace.py workspace_add /Users/me/repos/api \
  --alias api --role backend --description "Order service REST API"
python skills/multi-project/workspace.py workspace_add /Users/me/repos/web \
  --alias web --role frontend --description "Customer-facing Next.js site"
python skills/multi-project/workspace.py workspace_add /Users/me/repos/sdk \
  --alias sdk --role library --description "Shared TypeScript SDK"
```

**See where things stand**

```
python skills/multi-project/workspace.py workspace_list
python skills/multi-project/workspace.py workspace_overview
python skills/multi-project/workspace.py workspace_git_status
```

**Trace a symbol everywhere before changing it**

```
python skills/multi-project/workspace.py workspace_find_dependencies \
  OrderClient --file-type ts
```

**Search across a subset of projects**

```
python skills/multi-project/workspace.py workspace_search "TODO\\(legacy\\)" \
  --projects api,sdk --file-type py --context-lines 2
```

**Surgical edit in a specific project**

```
python skills/multi-project/workspace.py workspace_edit_file sdk \
  src/orderClient.ts \
  --old-string 'timeout: 5000' --new-string 'timeout: 15000'
```

For multi-line edits, write old/new blocks to temp files and use
`--old-file` / `--new-file`.

**Coordinated commit across multiple repos**

```
python skills/multi-project/workspace.py workspace_commit \
  --projects api,sdk,web \
  --message "feat(order): bump client timeout to 15s for slow downstream"
```

Add `--add-all` only if every repo's working tree contains exactly the changes
you intend to commit (verify with `workspace_git_status` first).

**Run a project-scoped command**

```
python skills/multi-project/workspace.py workspace_exec api "pytest tests/order"
python skills/multi-project/workspace.py workspace_exec web "npm run typecheck"
```

## Safety rules

- Destructive commands (`rm`, `format`, `dd`, `shutdown`, ...) are blocked
  inside `workspace_exec`. If you really need them, the user must run them
  manually outside the skill.
- `workspace_edit_file` refuses to act when `old_string` matches zero or more
  than one location — never silently mass-replaces.
- `workspace_commit` will skip a project that has nothing staged rather than
  produce an empty commit.
- `workspace_add` resolves the path to absolute form before saving — moving
  the project later will break the alias and require re-adding.

## Mental model

Think of the workspace as your **multi-repo IDE**. The orchestrator directory
(where `.agent-memory/workspace.json` lives) is your IDE workspace file; each
registered project is an open folder. Always check cross-project impact before
making a change in a "leaf" repo, the same way an IDE's "Find Usages" would.

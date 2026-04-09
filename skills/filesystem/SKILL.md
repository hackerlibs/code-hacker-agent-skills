---
name: filesystem
description: Read, write, edit, search and list files on the local filesystem. Use when you need to inspect or modify files, run safe shell commands, do glob/ripgrep search across a directory, or perform precise single-occurrence string replacements (similar to Claude Code's Edit tool). Content search is powered by ripgrep (`rg`); the binary is resolved from the `RG_PATH` env var (default `/usr/local/bin/rg`) and falls back to `grep` if ripgrep is missing. Also exposes a safe execute_command for running shell commands with dangerous verbs blocked.
---

# Filesystem Skill

A direct CLI replacement for the `filesystem-command` MCP server. All
operations are dispatched through one Python script:

```
python skills/filesystem/fs.py <subcommand> [args]
```

The script enforces an extension allow-list, a 10MB max file size, blocks
destructive shell verbs (`rm`, `format`, `dd`, `shutdown`, ...), and rejects
paths containing `..` segments.

## When to use this skill

- You need to read or modify a project file and want consistent error handling
- You need a precise single-occurrence string replacement (`edit_file`)
- You need to glob-find files (`find_files`) or content-search (`search_files_rg`)
- You need to run a non-destructive shell command in a known cwd

When the built-in editor's read/write/edit tools are sufficient, prefer those.
This skill is the canonical fallback when the agent runs without those built-ins
or when you need the extra guarantees (size limits, encoding fallback, blocked
commands).

## Subcommands

| Subcommand            | Purpose                                              |
|-----------------------|------------------------------------------------------|
| `read_file`           | Read a whole text file                               |
| `read_file_lines`     | Read a line range from a file (good for big files)   |
| `write_file`          | Overwrite a file                                     |
| `append_file`         | Append to a file                                     |
| `edit_file`           | Replace one exact occurrence of `old_string`         |
| `list_directory`      | List directory entries with sizes                    |
| `get_file_info`       | Show stat / permissions / mtime                      |
| `find_files`          | Recursive glob search (`*.py`, `**/*.ts`, ...)       |
| `search_files_rg`     | Regex content search via `rg` ripgrep (falls back to `grep`) |
| `create_directory`    | `mkdir -p`                                           |
| `get_current_directory` | Print cwd                                          |
| `execute_command`     | Run a shell command (dangerous verbs blocked)        |

Run `python skills/filesystem/fs.py <subcommand> --help` for full flags.

## Calling patterns the agent should use

**Read a file**

```
python skills/filesystem/fs.py read_file src/app.py
```

**Read only lines 100–200 of a large file**

```
python skills/filesystem/fs.py read_file_lines src/app.py --start-line 100 --end-line 200
```

**Glob-find files**

```
python skills/filesystem/fs.py find_files src --pattern "**/*.py" --max-depth 6
```

**Content search (regex, case-insensitive, 2 lines of context)**

```
python skills/filesystem/fs.py search_files_rg "TODO\\(.*\\)" src --file-type py --context-lines 2
```

`--file-type` accepts any ripgrep type name (`rg --type-list` to enumerate).
The binary is resolved from `RG_PATH` (default `/usr/local/bin/rg`); set
`RG_PATH=/opt/homebrew/bin/rg` (or similar) if your install lives elsewhere.

**Precise string edit (single line)**

```
python skills/filesystem/fs.py edit_file src/app.py \
  --old-string 'DEBUG = False' --new-string 'DEBUG = True'
```

**Precise edit with multi-line content** — write the old/new blocks to temp
files first (this is the safer approach for any non-trivial replacement, since
shell quoting is fragile):

```
# write old/new blocks to temp files using your normal editor tools, then:
python skills/filesystem/fs.py edit_file src/app.py \
  --old-file /tmp/old.txt --new-file /tmp/new.txt
```

The command will refuse to edit if `old_string` appears zero or more than once
— in that case, expand the snippet with more surrounding context until it is
unique.

**Write a new file (content from stdin)**

```
cat <<'EOF' | python skills/filesystem/fs.py write_file notes.md --stdin
# Notes
First line.
EOF
```

**Run a shell command in a project directory**

```
python skills/filesystem/fs.py execute_command "pytest -x" --cwd . --timeout 120
```

## Safety rules baked into the script

- File extensions outside the allow-list are rejected for read/write/edit
- Files larger than 10MB are rejected for read
- Paths containing `..` segments are rejected
- `rm`, `del`, `format`, `mkfs`, `dd`, `shutdown`, `reboot`, `halt`, `poweroff`
  are blocked from `execute_command`
- `edit_file` refuses ambiguous matches — never silently mass-replaces

If you hit a rejection, do not try to bypass it. Either work around the limit
(e.g. use `read_file_lines` for large files) or surface the constraint to the
user.

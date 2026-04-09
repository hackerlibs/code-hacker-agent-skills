#!/usr/bin/env python3
"""
Multi-Project Workspace CLI — skill replacement for the multi-project MCP server.

Solves cross-project editing and search:
- Jenkinsfile + dependent libraries
- Frontend + backend
- Microservices spread across multiple repos

Workspace state is persisted in `.agent-memory/workspace.json` under the
current working directory, just like the original MCP server. Each registered
project gets an alias, an absolute path, an optional role and description.

Subcommands map 1:1 to the original tool names:

    workspace_add        workspace_remove     workspace_list
    workspace_overview   workspace_search     workspace_find_files
    workspace_read_file  workspace_edit_file  workspace_write_file
    workspace_git_status workspace_git_diff   workspace_git_log
    workspace_commit     workspace_find_dependencies   workspace_exec

Usage:

    python skills/multi-project/workspace.py workspace_list
    python skills/multi-project/workspace.py workspace_add /abs/path --alias api --role backend
    python skills/multi-project/workspace.py workspace_search "TODO" --projects api,web --file-type py
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


WORKSPACE_FILE = Path.cwd() / ".agent-memory" / "workspace.json"

ALLOWED_EXTENSIONS = {
    '.txt', '.py', '.java', '.js', '.ts', '.jsx', '.tsx', '.json', '.md',
    '.csv', '.log', '.yaml', '.yml', '.xml', '.html', '.css', '.sh', '.bat',
    '.clj', '.edn', '.cljs', '.cljc', '.go', '.rs', '.toml', '.cfg', '.ini',
    '.sql', '.graphql', '.proto', '.gradle', '.properties', '.env',
    '.Jenkinsfile', '.Dockerfile', '.groovy', '.kt', '.swift', '.rb',
    '.php', '.vue', '.svelte',
}

KNOWN_EXTENSIONLESS = {'Jenkinsfile', 'Dockerfile', 'Makefile', 'Vagrantfile', 'Gemfile', 'Rakefile'}

BLOCKED_COMMANDS = {'rm', 'del', 'format', 'mkfs', 'dd', 'shutdown', 'reboot', 'halt', 'poweroff'}

RG_DEFAULT_PATH = '/usr/local/bin/rg'


# ─── Workspace state ────────────────────────────────────────────────────────
def _load_workspace() -> dict:
    if WORKSPACE_FILE.exists():
        try:
            return json.loads(WORKSPACE_FILE.read_text())
        except Exception:
            pass
    return {"projects": {}}


def _save_workspace(ws: dict) -> None:
    WORKSPACE_FILE.parent.mkdir(parents=True, exist_ok=True)
    WORKSPACE_FILE.write_text(json.dumps(ws, ensure_ascii=False, indent=2))


def _resolve_project_path(ws: dict, name_or_path: str) -> Optional[str]:
    if name_or_path in ws["projects"]:
        return ws["projects"][name_or_path]["path"]
    if Path(name_or_path).is_dir():
        return str(Path(name_or_path).resolve())
    return None


def _is_allowed_file(path: str) -> bool:
    p = Path(path)
    if p.suffix.lower() in ALLOWED_EXTENSIONS:
        return True
    return p.name in KNOWN_EXTENSIONLESS


def _run_git(args: list, cwd: str, timeout: int = 30) -> dict:
    try:
        result = subprocess.run(
            ["git"] + args, cwd=cwd, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": f"Timed out after {timeout}s"}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e)}


def _read_file_content(file_path: str) -> Optional[str]:
    for enc in ('utf-8', 'gbk', 'gb2312', 'latin-1'):
        try:
            with open(file_path, 'r', encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
        except Exception:
            return None
    return None


def _split_aliases(s: str) -> list:
    return [a.strip() for a in s.split(",") if a.strip()] if s else []


# ═══════════════════════════════════════════════════════════════════════════
#  Workspace management
# ═══════════════════════════════════════════════════════════════════════════
def cmd_workspace_add(args) -> int:
    path = Path(args.project_path).resolve()
    if not path.is_dir():
        print(f"Error: Directory does not exist: {args.project_path}")
        return 1
    alias = args.alias or path.name
    ws = _load_workspace()

    git_res = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], str(path))
    branch = git_res["stdout"].strip() if git_res["success"] else "(not a git repo)"

    ws["projects"][alias] = {
        "path": str(path),
        "description": args.description,
        "role": args.role,
        "branch": branch,
        "added_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_workspace(ws)

    print(f"Project registered: '{alias}'")
    print(f"  Path: {path}")
    print(f"  Branch: {branch}")
    print(f"  Role: {args.role or '(not set)'}")
    print(f"  Description: {args.description or '(not set)'}")
    print(f"\nWorkspace now has {len(ws['projects'])} project(s).")
    return 0


def cmd_workspace_remove(args) -> int:
    ws = _load_workspace()
    if args.alias not in ws["projects"]:
        available = ", ".join(ws["projects"].keys()) or "(empty)"
        print(f"Project '{args.alias}' not found. Available: {available}")
        return 1
    del ws["projects"][args.alias]
    _save_workspace(ws)
    print(f"Removed '{args.alias}'. Remaining: {len(ws['projects'])} project(s).")
    return 0


def cmd_workspace_list(args) -> int:
    ws = _load_workspace()
    if not ws["projects"]:
        print("Workspace is empty. Use workspace_add to register projects.")
        return 0
    print(f"=== Multi-Project Workspace ({len(ws['projects'])} projects) ===\n")
    for alias, info in ws["projects"].items():
        path = info["path"]
        exists = Path(path).is_dir()
        if exists:
            br = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], path)
            branch = br["stdout"].strip() if br["success"] else "?"
            st = _run_git(["status", "--porcelain"], path)
            changed = len(st["stdout"].strip().splitlines()) if st["success"] and st["stdout"].strip() else 0
            status_str = f"branch: {branch}, {changed} changed file(s)" if changed else f"branch: {branch}, clean"
        else:
            status_str = "PATH NOT FOUND"
        role_str = f" [{info.get('role', '')}]" if info.get('role') else ""
        desc_str = f" — {info.get('description', '')}" if info.get('description') else ""
        print(f"  {alias}{role_str}{desc_str}")
        print(f"    {path}")
        print(f"    {status_str}")
        print()
    return 0


# ═══════════════════════════════════════════════════════════════════════════
#  Cross-project search
# ═══════════════════════════════════════════════════════════════════════════
def _check_rg() -> Optional[str]:
    """Locate ripgrep: honour RG_PATH, then default /usr/local/bin/rg."""
    rg_bin = os.environ.get('RG_PATH', RG_DEFAULT_PATH)
    try:
        subprocess.run([rg_bin, '--version'], capture_output=True, check=True)
        return rg_bin
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def cmd_workspace_search(args) -> int:
    ws = _load_workspace()
    if not ws["projects"]:
        print("Workspace is empty.")
        return 1
    targets = _split_aliases(args.projects) or list(ws["projects"].keys())

    rg_bin = _check_rg()
    print(f"=== Workspace Search: '{args.pattern}' across {len(targets)} project(s) ===")

    for alias in targets:
        if alias not in ws["projects"]:
            print(f"\n[{alias}] — NOT FOUND in workspace")
            continue
        project_path = ws["projects"][alias]["path"]
        if not Path(project_path).is_dir():
            print(f"\n[{alias}] — PATH NOT FOUND: {project_path}")
            continue

        if rg_bin:
            cmd = [rg_bin, "--color=never", "-n"]
            if not args.case_sensitive:
                cmd.append("-i")
            if args.context_lines > 0:
                cmd.extend(["-C", str(args.context_lines)])
            if args.file_type:
                cmd.extend(["-t", args.file_type.lstrip('.')])
            cmd.extend(["-m", str(args.max_results_per_project), args.pattern, project_path])
        else:
            cmd = ["grep", "-rn"]
            if not args.case_sensitive:
                cmd.append("-i")
            if args.context_lines > 0:
                cmd.extend(["-C", str(args.context_lines)])
            if args.file_type:
                cmd.extend(["--include", f"*.{args.file_type.lstrip('.')}"])
            cmd.extend(["-m", str(args.max_results_per_project), args.pattern, project_path])

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                encoding="utf-8", errors="replace",
            )
            if result.stdout.strip():
                match_count = result.stdout.strip().count("\n") + 1
                output = result.stdout.replace(project_path + "/", "")
                print(f"\n[{alias}] ({match_count} matches) — {project_path}")
                print(output.rstrip())
            else:
                print(f"\n[{alias}] (0 matches)")
        except subprocess.TimeoutExpired:
            print(f"\n[{alias}] — search timed out")
        except Exception as e:
            print(f"\n[{alias}] — error: {e}")
    return 0


def cmd_workspace_find_files(args) -> int:
    ws = _load_workspace()
    if not ws["projects"]:
        print("Workspace is empty.")
        return 1
    targets = _split_aliases(args.projects) or list(ws["projects"].keys())

    print(f"=== Workspace Find: '{args.pattern}' across {len(targets)} project(s) ===")
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", "target"}

    for alias in targets:
        if alias not in ws["projects"]:
            continue
        project_path = Path(ws["projects"][alias]["path"])
        if not project_path.is_dir():
            continue
        matches = []
        for match in sorted(project_path.rglob(args.pattern)):
            try:
                rel = match.relative_to(project_path)
            except ValueError:
                continue
            if len(rel.parts) > args.max_depth:
                continue
            if any(part in skip_dirs for part in rel.parts):
                continue
            t = "FILE" if match.is_file() else "DIR "
            size = match.stat().st_size if match.is_file() else 0
            matches.append(f"  {t} {str(rel):<55} {size:>10,} bytes")
            if len(matches) >= 200:
                matches.append("  ... (truncated)")
                break
        if matches:
            print(f"\n[{alias}] ({len(matches)} found) — {project_path}")
            print("\n".join(matches))
        else:
            print(f"\n[{alias}] (0 matches)")
    return 0


# ═══════════════════════════════════════════════════════════════════════════
#  Cross-project file operations
# ═══════════════════════════════════════════════════════════════════════════
def cmd_workspace_read_file(args) -> int:
    ws = _load_workspace()
    project_root = _resolve_project_path(ws, args.project)
    if not project_root:
        available = ", ".join(ws["projects"].keys()) or "(empty)"
        print(f"Error: Project '{args.project}' not found. Available: {available}")
        return 1
    full_path = Path(project_root) / args.file_path
    if not full_path.is_file():
        print(f"Error: File not found: {full_path}")
        return 1
    content = _read_file_content(str(full_path))
    if content is None:
        print(f"Error: Unable to read file: {full_path}")
        return 1
    lines = content.splitlines(keepends=True)
    total = len(lines)
    start = max(1, args.start_line) - 1
    end = total if args.end_line <= 0 else min(args.end_line, total)
    selected = lines[start:end]
    print(f"[{args.project}] {args.file_path} (lines {start + 1}-{end} of {total})")
    for i, line in enumerate(selected):
        sys.stdout.write(f"{i + start + 1:>6}\t{line}")
    if selected and not selected[-1].endswith('\n'):
        sys.stdout.write('\n')
    return 0


def cmd_workspace_edit_file(args) -> int:
    ws = _load_workspace()
    project_root = _resolve_project_path(ws, args.project)
    if not project_root:
        available = ", ".join(ws["projects"].keys()) or "(empty)"
        print(f"Error: Project '{args.project}' not found. Available: {available}")
        return 1
    full_path = Path(project_root) / args.file_path
    if not full_path.is_file():
        print(f"Error: File not found: {full_path}")
        return 1
    if not _is_allowed_file(str(full_path)):
        print(f"Error: File type not allowed: {full_path.suffix}")
        return 1
    content = _read_file_content(str(full_path))
    if content is None:
        print(f"Error: Unable to read file: {full_path}")
        return 1

    old_string = args.old_string
    new_string = args.new_string
    if args.old_file:
        old_string = Path(args.old_file).read_text(encoding='utf-8')
    if args.new_file:
        new_string = Path(args.new_file).read_text(encoding='utf-8')
    if old_string is None or new_string is None:
        print("Error: must provide both old/new strings (use --old-file/--new-file for multi-line)")
        return 1

    count = content.count(old_string)
    if count == 0:
        print(f"Error: old_string not found in [{args.project}] {args.file_path}")
        return 1
    if count > 1:
        print(f"Error: old_string found {count} times. Provide more context.")
        return 1
    new_content = content.replace(old_string, new_string, 1)
    try:
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Successfully edited [{args.project}] {args.file_path}: replaced 1 occurrence.")
    except Exception as e:
        print(f"Error writing file: {e}")
        return 1
    return 0


def cmd_workspace_write_file(args) -> int:
    ws = _load_workspace()
    project_root = _resolve_project_path(ws, args.project)
    if not project_root:
        available = ", ".join(ws["projects"].keys()) or "(empty)"
        print(f"Error: Project '{args.project}' not found. Available: {available}")
        return 1
    full_path = Path(project_root) / args.file_path
    if not _is_allowed_file(str(full_path)):
        print(f"Error: File type not allowed: {full_path.suffix}")
        return 1

    if args.stdin:
        content = sys.stdin.read()
    elif args.content_file:
        content = Path(args.content_file).read_text(encoding='utf-8')
    elif args.content is not None:
        content = args.content
    else:
        print("Error: provide --content / --content-file / --stdin")
        return 1

    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Successfully wrote [{args.project}] {args.file_path} ({len(content)} chars)")
    except Exception as e:
        print(f"Error writing file: {e}")
        return 1
    return 0


# ═══════════════════════════════════════════════════════════════════════════
#  Cross-project git
# ═══════════════════════════════════════════════════════════════════════════
def cmd_workspace_git_status(args) -> int:
    ws = _load_workspace()
    if not ws["projects"]:
        print("Workspace is empty.")
        return 1
    targets = _split_aliases(args.projects) or list(ws["projects"].keys())
    print(f"=== Workspace Git Status ({len(targets)} projects) ===\n")
    total_changed = 0
    for alias in targets:
        if alias not in ws["projects"]:
            continue
        project_path = ws["projects"][alias]["path"]
        if not Path(project_path).is_dir():
            print(f"[{alias}] PATH NOT FOUND: {project_path}\n")
            continue
        br = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], project_path)
        branch = br["stdout"].strip() if br["success"] else "?"
        st = _run_git(["status", "--porcelain"], project_path)
        if st["success"] and st["stdout"].strip():
            changes = st["stdout"].strip().splitlines()
            total_changed += len(changes)
            print(f"[{alias}] branch: {branch} — {len(changes)} change(s)")
            for change in changes[:20]:
                print(f"  {change}")
            if len(changes) > 20:
                print(f"  ... and {len(changes) - 20} more")
        else:
            print(f"[{alias}] branch: {branch} — clean")
        print()
    print(f"Total changed files across workspace: {total_changed}")
    return 0


def cmd_workspace_git_diff(args) -> int:
    ws = _load_workspace()
    if not ws["projects"]:
        print("Workspace is empty.")
        return 1
    targets = _split_aliases(args.projects) or list(ws["projects"].keys())
    print(f"=== Workspace Git Diff ({'staged' if args.staged else 'unstaged'}) ===\n")
    found_any = False
    for alias in targets:
        if alias not in ws["projects"]:
            continue
        project_path = ws["projects"][alias]["path"]
        if not Path(project_path).is_dir():
            continue
        cmd = ["diff", "--stat"]
        if args.staged:
            cmd.append("--cached")
        res = _run_git(cmd, project_path)
        if res["success"] and res["stdout"].strip():
            found_any = True
            print(f"[{alias}] — {project_path}")
            print(res["stdout"].rstrip())
            print()
    if not found_any:
        print("No changes found.")
    return 0


def cmd_workspace_git_log(args) -> int:
    ws = _load_workspace()
    if not ws["projects"]:
        print("Workspace is empty.")
        return 1
    targets = _split_aliases(args.projects) or list(ws["projects"].keys())
    print("=== Workspace Recent Commits ===\n")
    for alias in targets:
        if alias not in ws["projects"]:
            continue
        project_path = ws["projects"][alias]["path"]
        if not Path(project_path).is_dir():
            continue
        res = _run_git(["log", f"-{args.max_count}", "--oneline", "--decorate"], project_path)
        if res["success"] and res["stdout"].strip():
            print(f"[{alias}] — {project_path}")
            print(res["stdout"].rstrip())
            print()
    return 0


def cmd_workspace_commit(args) -> int:
    ws = _load_workspace()
    targets = _split_aliases(args.projects)
    if not targets:
        print("Error: Specify at least one project alias via --projects.")
        return 1
    print("=== Workspace Coordinated Commit ===\n")
    for alias in targets:
        if alias not in ws["projects"]:
            print(f"[{alias}] SKIPPED — not found in workspace")
            continue
        project_path = ws["projects"][alias]["path"]
        if not Path(project_path).is_dir():
            print(f"[{alias}] SKIPPED — path not found")
            continue
        if args.add_all:
            add_res = _run_git(["add", "-A"], project_path)
            if not add_res["success"]:
                print(f"[{alias}] FAILED to stage: {add_res['stderr']}")
                continue
        # Anything staged?
        check = _run_git(["diff", "--cached", "--quiet"], project_path)
        if check["success"]:
            print(f"[{alias}] SKIPPED — nothing staged to commit")
            continue
        commit_res = _run_git(["commit", "-m", args.message], project_path)
        if commit_res["success"]:
            h = _run_git(["rev-parse", "--short", "HEAD"], project_path)
            short = h["stdout"].strip() if h["success"] else "?"
            print(f"[{alias}] COMMITTED ({short}) — {args.message}")
        else:
            print(f"[{alias}] FAILED — {commit_res['stderr'].strip()}")
    return 0


# ═══════════════════════════════════════════════════════════════════════════
#  Cross-project dependency tracing
# ═══════════════════════════════════════════════════════════════════════════
def cmd_workspace_find_dependencies(args) -> int:
    ws = _load_workspace()
    if not ws["projects"]:
        print("Workspace is empty.")
        return 1
    targets = _split_aliases(args.projects) or list(ws["projects"].keys())
    rg_bin = _check_rg()
    print(f"=== Cross-Project Dependency Trace: '{args.symbol}' ===\n")
    total_refs = 0
    for alias in targets:
        if alias not in ws["projects"]:
            continue
        project_path = ws["projects"][alias]["path"]
        if not Path(project_path).is_dir():
            continue
        if rg_bin:
            cmd = [rg_bin, "--color=never", "-n", "-m", "30"]
            if args.file_type:
                cmd.extend(["-t", args.file_type.lstrip('.')])
            cmd.extend([args.symbol, project_path])
        else:
            cmd = ["grep", "-rn", "-m", "30"]
            if args.file_type:
                cmd.extend(["--include", f"*.{args.file_type.lstrip('.')}"])
            cmd.extend([args.symbol, project_path])
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15,
                encoding="utf-8", errors="replace",
            )
            if result.stdout.strip():
                matches = result.stdout.strip().splitlines()
                total_refs += len(matches)
                output = result.stdout.replace(project_path + "/", "")
                print(f"[{alias}] ({len(matches)} references)")
                print(output.rstrip())
                print()
        except Exception as e:
            print(f"[{alias}] error: {e}")
    print(f"\nTotal references across workspace: {total_refs}")
    if total_refs > 0:
        print("\nTip: review all references before modifying the symbol. Use workspace_edit_file to make coordinated changes.")
    return 0


def cmd_workspace_overview(args) -> int:
    ws = _load_workspace()
    if not ws["projects"]:
        print("Workspace is empty. Use workspace_add to register projects.")
        return 0
    targets = _split_aliases(args.projects) or list(ws["projects"].keys())
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", "target", ".idea"}
    config_names = {
        "package.json", "pyproject.toml", "setup.py", "setup.cfg",
        "Cargo.toml", "go.mod", "pom.xml", "build.gradle",
        "Makefile", "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
        "Jenkinsfile", "requirements.txt", "Pipfile", "tsconfig.json",
        ".env", ".env.example", "settings.gradle",
    }
    print(f"=== Workspace Overview ({len(targets)} projects) ===\n")
    for alias in targets:
        if alias not in ws["projects"]:
            continue
        info = ws["projects"][alias]
        root = Path(info["path"])
        if not root.is_dir():
            print(f"[{alias}] PATH NOT FOUND: {info['path']}\n")
            continue
        ext_counts: dict = {}
        total_files = 0
        configs_found = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith('.')]
            for fname in filenames:
                total_files += 1
                ext = Path(fname).suffix.lower() or "(no ext)"
                ext_counts[ext] = ext_counts.get(ext, 0) + 1
                if fname in config_names:
                    rel = os.path.relpath(os.path.join(dirpath, fname), root)
                    configs_found.append(rel)
        top_langs = sorted(ext_counts.items(), key=lambda x: -x[1])[:8]
        lang_str = ", ".join(f"{ext}({cnt})" for ext, cnt in top_langs)
        role_str = f" [{info.get('role', '')}]" if info.get('role') else ""
        desc_str = f" — {info.get('description', '')}" if info.get('description') else ""
        print(f"[{alias}]{role_str}{desc_str}")
        print(f"  Path: {root}")
        print(f"  Files: {total_files} | Languages: {lang_str}")
        if configs_found:
            print(f"  Config: {', '.join(configs_found[:10])}")
        print()
    return 0


def cmd_workspace_exec(args) -> int:
    ws = _load_workspace()
    project_root = _resolve_project_path(ws, args.project)
    if not project_root:
        available = ", ".join(ws["projects"].keys()) or "(empty)"
        print(f"Error: Project '{args.project}' not found. Available: {available}")
        return 1
    parts = args.command.strip().split()
    if parts and parts[0].lower() in BLOCKED_COMMANDS:
        print(f"Error: Command blocked for safety: {parts[0]}")
        return 1
    try:
        result = subprocess.run(
            args.command, shell=True, cwd=project_root,
            capture_output=True, text=True, timeout=args.timeout,
            encoding="utf-8", errors="replace",
        )
        print(f"[{args.project}] $ {args.command}")
        print(f"Return code: {result.returncode}")
        if result.stdout:
            print(result.stdout.rstrip())
        if result.stderr:
            print(f"[stderr] {result.stderr.rstrip()}")
    except subprocess.TimeoutExpired:
        print(f"Command timed out after {args.timeout}s")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1
    return 0


# ─── Entry point ────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(
        description="Multi-Project Workspace CLI (skill replacement for multi-project MCP server)"
    )
    sub = p.add_subparsers(dest='cmd', required=True, metavar='SUBCOMMAND')

    # ── workspace management ──
    sp = sub.add_parser('workspace_add', help='Register a project into the workspace')
    sp.add_argument('project_path')
    sp.add_argument('--alias', default='')
    sp.add_argument('--description', default='')
    sp.add_argument('--role', default='')
    sp.set_defaults(func=cmd_workspace_add)

    sp = sub.add_parser('workspace_remove', help='Remove a project from the workspace')
    sp.add_argument('alias')
    sp.set_defaults(func=cmd_workspace_remove)

    sp = sub.add_parser('workspace_list', help='List registered projects + git status')
    sp.set_defaults(func=cmd_workspace_list)

    sp = sub.add_parser('workspace_overview', help='High-level overview of all projects')
    sp.add_argument('--projects', default='')
    sp.set_defaults(func=cmd_workspace_overview)

    # ── cross-project search ──
    sp = sub.add_parser('workspace_search', help='Regex/text search across projects')
    sp.add_argument('pattern')
    sp.add_argument('--projects', default='')
    sp.add_argument('--file-type', default='')
    sp.add_argument('--case-sensitive', action='store_true')
    sp.add_argument('--max-results-per-project', type=int, default=50)
    sp.add_argument('--context-lines', type=int, default=0)
    sp.set_defaults(func=cmd_workspace_search)

    sp = sub.add_parser('workspace_find_files', help='Glob file search across projects')
    sp.add_argument('--pattern', default='*')
    sp.add_argument('--projects', default='')
    sp.add_argument('--max-depth', type=int, default=5)
    sp.set_defaults(func=cmd_workspace_find_files)

    # ── cross-project file ops ──
    sp = sub.add_parser('workspace_read_file', help='Read a file from any project')
    sp.add_argument('project')
    sp.add_argument('file_path')
    sp.add_argument('--start-line', type=int, default=1)
    sp.add_argument('--end-line', type=int, default=0)
    sp.set_defaults(func=cmd_workspace_read_file)

    sp = sub.add_parser('workspace_edit_file', help='Precise string replacement in any project')
    sp.add_argument('project')
    sp.add_argument('file_path')
    sp.add_argument('--old-string', default=None)
    sp.add_argument('--new-string', default=None)
    sp.add_argument('--old-file', default=None)
    sp.add_argument('--new-file', default=None)
    sp.set_defaults(func=cmd_workspace_edit_file)

    sp = sub.add_parser('workspace_write_file', help='Write/create a file in any project')
    sp.add_argument('project')
    sp.add_argument('file_path')
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument('--content', default=None)
    g.add_argument('--content-file', default=None)
    g.add_argument('--stdin', action='store_true')
    sp.set_defaults(func=cmd_workspace_write_file)

    # ── cross-project git ──
    sp = sub.add_parser('workspace_git_status', help='Git status across all projects')
    sp.add_argument('--projects', default='')
    sp.set_defaults(func=cmd_workspace_git_status)

    sp = sub.add_parser('workspace_git_diff', help='Git diff (--stat) across all projects')
    sp.add_argument('--projects', default='')
    sp.add_argument('--staged', action='store_true')
    sp.set_defaults(func=cmd_workspace_git_diff)

    sp = sub.add_parser('workspace_git_log', help='Recent commits across all projects')
    sp.add_argument('--projects', default='')
    sp.add_argument('--max-count', type=int, default=5)
    sp.set_defaults(func=cmd_workspace_git_log)

    sp = sub.add_parser('workspace_commit', help='Coordinated commit across multiple projects')
    sp.add_argument('--projects', required=True)
    sp.add_argument('--message', required=True)
    sp.add_argument('--add-all', action='store_true')
    sp.set_defaults(func=cmd_workspace_commit)

    # ── dependency tracing ──
    sp = sub.add_parser('workspace_find_dependencies', help='Trace a symbol across all projects')
    sp.add_argument('symbol')
    sp.add_argument('--projects', default='')
    sp.add_argument('--file-type', default='')
    sp.set_defaults(func=cmd_workspace_find_dependencies)

    sp = sub.add_parser('workspace_exec', help='Run a shell command inside a project')
    sp.add_argument('project')
    sp.add_argument('command')
    sp.add_argument('--timeout', type=int, default=30)
    sp.set_defaults(func=cmd_workspace_exec)

    args = p.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == '__main__':
    main()

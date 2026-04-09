#!/usr/bin/env python3
"""
Git operations CLI — skill replacement for the git-tools MCP server.

Each MCP tool from git_tools.py is exposed as a subcommand:

    python skills/git-tools/git_ops.py status
    python skills/git-tools/git_ops.py diff --staged
    python skills/git-tools/git_ops.py log --max-count 10
    python skills/git-tools/git_ops.py commit --message "fix: ..."

This is a thin wrapper around the `git` binary. It exists so the agent has a
single, predictable command surface that matches the original MCP tool names
and argument shapes — even on machines where MCP servers are not available.
"""
import argparse
import subprocess
import sys
from typing import Optional


def run_git(args: list, cwd: str = ".", timeout: int = 30) -> dict:
    """Run a git command and capture stdout/stderr/exit."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": f"Timed out after {timeout}s", "returncode": -1}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}


def format_result(res: dict) -> str:
    out = []
    if res["stdout"]:
        out.append(res["stdout"])
    if res["stderr"]:
        out.append(f"[stderr] {res['stderr']}")
    if not res["success"]:
        out.insert(0, f"[exit {res['returncode']}]")
    return "\n".join(out) if out else "(no output)"


def _emit(res: dict) -> int:
    print(format_result(res))
    return 0 if res["success"] else 1


# ─── Commands ───────────────────────────────────────────────────────────────
def cmd_status(args) -> int:
    return _emit(run_git(["status"], cwd=args.repo_path))


def cmd_diff(args) -> int:
    g = ["diff"]
    if args.staged:
        g.append("--cached")
    if args.file_path:
        g.extend(["--", args.file_path])
    return _emit(run_git(g, cwd=args.repo_path))


def cmd_log(args) -> int:
    g = ["log", f"-{args.max_count}"]
    if args.oneline:
        g.append("--oneline")
    if args.branch:
        g.append(args.branch)
    if args.file_path:
        g.extend(["--", args.file_path])
    return _emit(run_git(g, cwd=args.repo_path))


def cmd_show(args) -> int:
    if args.file_path:
        return _emit(run_git(["show", f"{args.commit}:{args.file_path}"], cwd=args.repo_path))
    return _emit(run_git(["show", args.commit, "--stat"], cwd=args.repo_path))


def cmd_branch(args) -> int:
    g = ["branch"]
    if args.show_all:
        g.append("-a")
    return _emit(run_git(g, cwd=args.repo_path))


def cmd_add(args) -> int:
    return _emit(run_git(["add"] + args.files.split(), cwd=args.repo_path))


def cmd_commit(args) -> int:
    if not args.message:
        print("Error: Commit message is required.")
        return 1
    return _emit(run_git(["commit", "-m", args.message], cwd=args.repo_path))


def cmd_checkout(args) -> int:
    if not args.target:
        print("Error: Target branch or file is required.")
        return 1
    return _emit(run_git(["checkout", args.target], cwd=args.repo_path))


def cmd_create_branch(args) -> int:
    if not args.branch_name:
        print("Error: Branch name is required.")
        return 1
    return _emit(run_git(["checkout", "-b", args.branch_name, args.base], cwd=args.repo_path))


def cmd_stash(args) -> int:
    g = ["stash", args.action]
    if args.action == "push" and args.message:
        g.extend(["-m", args.message])
    return _emit(run_git(g, cwd=args.repo_path))


def cmd_blame(args) -> int:
    if not args.file_path:
        print("Error: file_path is required.")
        return 1
    g = ["blame"]
    if args.start_line > 0 and args.end_line > 0:
        g.extend(["-L", f"{args.start_line},{args.end_line}"])
    g.append(args.file_path)
    return _emit(run_git(g, cwd=args.repo_path))


# ─── Entry point ────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(
        description="Git operations CLI (skill replacement for git-tools MCP server)"
    )
    p.add_argument("--repo-path", default=".", help="Path to git repo (default: cwd)")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="SUBCOMMAND")

    sp = sub.add_parser("status", help="Show working tree status")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("diff", help="Show working / staged changes")
    sp.add_argument("--staged", action="store_true")
    sp.add_argument("--file-path", default=None)
    sp.set_defaults(func=cmd_diff)

    sp = sub.add_parser("log", help="Show commit history")
    sp.add_argument("--max-count", type=int, default=20)
    sp.add_argument("--no-oneline", dest="oneline", action="store_false")
    sp.add_argument("--file-path", default=None)
    sp.add_argument("--branch", default=None)
    sp.set_defaults(func=cmd_log, oneline=True)

    sp = sub.add_parser("show", help="Show a commit or a file at a commit")
    sp.add_argument("--commit", default="HEAD")
    sp.add_argument("--file-path", default=None)
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("branch", help="List branches")
    sp.add_argument("--show-all", action="store_true")
    sp.set_defaults(func=cmd_branch)

    sp = sub.add_parser("add", help="Stage files")
    sp.add_argument("--files", default=".", help="Space-separated paths (default: '.')")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("commit", help="Create a commit")
    sp.add_argument("--message", "-m", required=True)
    sp.set_defaults(func=cmd_commit)

    sp = sub.add_parser("checkout", help="Switch branches or restore files")
    sp.add_argument("target")
    sp.set_defaults(func=cmd_checkout)

    sp = sub.add_parser("create_branch", help="Create and switch to a new branch")
    sp.add_argument("branch_name")
    sp.add_argument("--base", default="HEAD")
    sp.set_defaults(func=cmd_create_branch)

    sp = sub.add_parser("stash", help="Manage git stash")
    sp.add_argument("--action", default="push", choices=["push", "pop", "list", "show", "drop"])
    sp.add_argument("--message", default=None)
    sp.set_defaults(func=cmd_stash)

    sp = sub.add_parser("blame", help="Blame a file or line range")
    sp.add_argument("file_path")
    sp.add_argument("--start-line", type=int, default=0)
    sp.add_argument("--end-line", type=int, default=0)
    sp.set_defaults(func=cmd_blame)

    args = p.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()

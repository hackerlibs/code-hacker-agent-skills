#!/usr/bin/env python3
"""
Filesystem operations CLI — skill replacement for the filesystem-command MCP server.

Each MCP tool from filesystem.py is exposed as a subcommand. Designed to be
called directly from the VSCode Copilot agent via the terminal:

    python skills/filesystem/fs.py read_file path/to/file.py
    python skills/filesystem/fs.py edit_file path/to/file.py --old-file /tmp/old --new-file /tmp/new
    python skills/filesystem/fs.py search_files_rg "TODO" src --file-type py

The content search subcommand uses ripgrep (`rg`). Override the binary with
the RG_PATH environment variable (default: /usr/local/bin/rg). If ripgrep is
unavailable the script falls back to plain `grep -rn`.

Dangerous shell commands (rm, format, dd, ...) are blocked in execute_command.
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


# ─── Constants ──────────────────────────────────────────────────────────────
ALLOWED_EXTENSIONS = {
    '.txt', '.py', '.java', '.js', '.ts', '.tsx', '.jsx', '.json', '.md',
    '.csv', '.log', '.yaml', '.yml', '.xml', '.html', '.css', '.sh', '.bat',
    '.clj', '.edn', '.cljs', '.cljc', '.dump', '.go', '.rs', '.toml',
    '.cfg', '.ini', '.sql', '.groovy', '.kt', '.swift', '.rb', '.php',
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
BLOCKED_COMMANDS = {'rm', 'del', 'format', 'mkfs', 'dd', 'shutdown', 'reboot', 'halt', 'poweroff'}
DEFAULT_ENCODING = 'utf-8'
RG_DEFAULT_PATH = '/usr/local/bin/rg'


# ─── Helpers ────────────────────────────────────────────────────────────────
def is_safe_path(path: str) -> bool:
    """Reject obvious directory traversal attempts."""
    try:
        return not any(part.startswith('..') for part in Path(path).parts)
    except Exception:
        return False


def is_allowed_file(path: str) -> bool:
    return Path(path).suffix.lower() in ALLOWED_EXTENSIONS


def is_safe_command(command: str) -> bool:
    parts = command.strip().split()
    if not parts:
        return False
    return parts[0].lower() not in BLOCKED_COMMANDS


def read_file_content(file_path: str) -> Optional[str]:
    """Try several encodings to read a text file."""
    for enc in ('utf-8', 'gbk', 'gb2312', 'latin-1', 'cp1252'):
        try:
            with open(file_path, 'r', encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
        except Exception:
            return None
    return None


def _read_string_arg(direct: Optional[str], from_file: Optional[str], stdin: bool) -> Optional[str]:
    """Resolve a string argument from --... / --...-file / --stdin."""
    if stdin:
        return sys.stdin.read()
    if from_file:
        try:
            return Path(from_file).read_text(encoding='utf-8')
        except Exception as e:
            print(f"Error reading {from_file}: {e}")
            return None
    return direct


# ─── Commands ───────────────────────────────────────────────────────────────
def cmd_read_file(args) -> int:
    p = args.file_path
    if not is_safe_path(p):
        print(f"Error: Unsafe file path: {p}"); return 1
    if not is_allowed_file(p):
        print(f"Error: File type not allowed: {Path(p).suffix}"); return 1
    path = Path(p)
    if not path.exists():
        print(f"Error: File does not exist: {p}"); return 1
    if not path.is_file():
        print(f"Error: Path is not a file: {p}"); return 1
    if path.stat().st_size > MAX_FILE_SIZE:
        print(f"Error: File too large (>{MAX_FILE_SIZE} bytes): {p}"); return 1
    content = read_file_content(str(path))
    if content is None:
        print(f"Error: Unable to read file with supported encodings: {p}"); return 1
    print(f"File: {p}")
    print(f"Size: {len(content)} characters")
    print()
    print(content)
    return 0


def cmd_write_file(args) -> int:
    p = args.file_path
    if not is_safe_path(p):
        print(f"Error: Unsafe file path: {p}"); return 1
    if not is_allowed_file(p):
        print(f"Error: File type not allowed: {Path(p).suffix}"); return 1
    content = _read_string_arg(args.content, args.content_file, args.stdin)
    if content is None:
        print("Error: provide --content / --content-file / --stdin"); return 1
    if len(content.encode(args.encoding)) > MAX_FILE_SIZE:
        print(f"Error: Content too large (>{MAX_FILE_SIZE} bytes)"); return 1
    try:
        path = Path(p)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding=args.encoding) as f:
            f.write(content)
        print(f"Successfully wrote {len(content)} characters to: {p}")
    except Exception as e:
        print(f"Error writing file: {e}"); return 1
    return 0


def cmd_append_file(args) -> int:
    p = args.file_path
    if not is_safe_path(p):
        print(f"Error: Unsafe file path: {p}"); return 1
    if not is_allowed_file(p):
        print(f"Error: File type not allowed: {Path(p).suffix}"); return 1
    content = _read_string_arg(args.content, args.content_file, args.stdin)
    if content is None:
        print("Error: provide --content / --content-file / --stdin"); return 1
    try:
        path = Path(p)
        cur = path.stat().st_size if path.exists() else 0
        if cur + len(content.encode(args.encoding)) > MAX_FILE_SIZE:
            print(f"Error: File would exceed size limit"); return 1
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'a', encoding=args.encoding) as f:
            f.write(content)
        print(f"Successfully appended {len(content)} characters to: {p}")
    except Exception as e:
        print(f"Error appending file: {e}"); return 1
    return 0


def cmd_list_directory(args) -> int:
    p = args.directory_path
    if not is_safe_path(p):
        print(f"Error: Unsafe directory path: {p}"); return 1
    path = Path(p)
    if not path.exists():
        print(f"Error: Directory does not exist: {p}"); return 1
    if not path.is_dir():
        print(f"Error: Path is not a directory: {p}"); return 1
    items = []
    for item in sorted(path.iterdir()):
        if not args.show_hidden and item.name.startswith('.'):
            continue
        try:
            st = item.stat()
            size = st.st_size if item.is_file() else 0
            t = "FILE" if item.is_file() else "DIR "
            items.append(f"{t} {item.name:<40} {size:>10,} bytes")
        except Exception:
            items.append(f"ERR  {item.name:<40} {'Access denied':>10}")
    if not items:
        print(f"Directory is empty: {p}"); return 0
    print(f"Contents of: {path.absolute()}")
    print(f"{'Type':<4} {'Name':<40} {'Size':>15}")
    print('-' * 60)
    print('\n'.join(items))
    return 0


def cmd_get_file_info(args) -> int:
    p = args.file_path
    if not is_safe_path(p):
        print(f"Error: Unsafe path: {p}"); return 1
    path = Path(p)
    if not path.exists():
        print(f"Error: Path does not exist: {p}"); return 1
    st = path.stat()
    lines = [
        f"Path: {path.absolute()}",
        f"Name: {path.name}",
        f"Type: {'File' if path.is_file() else 'Directory'}",
        f"Size: {st.st_size:,} bytes" if path.is_file() else "Size: N/A (directory)",
        f"Created: {time.ctime(st.st_ctime)}",
        f"Modified: {time.ctime(st.st_mtime)}",
        f"Accessed: {time.ctime(st.st_atime)}",
    ]
    if path.is_file():
        lines.extend([
            f"Extension: {path.suffix or 'None'}",
            f"Readable: {os.access(path, os.R_OK)}",
            f"Writable: {os.access(path, os.W_OK)}",
            f"Executable: {os.access(path, os.X_OK)}",
        ])
    print('\n'.join(lines))
    return 0


def cmd_execute_command(args) -> int:
    cmd = args.command
    if not is_safe_command(cmd):
        first = cmd.split()[0] if cmd.split() else 'empty'
        print(f"Error: Command not allowed for security reasons: {first}")
        return 1
    cwd = args.cwd
    if not is_safe_path(cwd):
        print(f"Error: Unsafe working directory: {cwd}"); return 1
    work_dir = Path(cwd)
    if not work_dir.exists() or not work_dir.is_dir():
        print(f"Error: Working directory does not exist: {cwd}"); return 1
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=str(work_dir.absolute()),
            capture_output=True, text=True, timeout=args.timeout,
            encoding='utf-8', errors='replace',
        )
        print(f"Command: {cmd}")
        print(f"Working Directory: {work_dir.absolute()}")
        print(f"Return Code: {result.returncode}")
        if result.stdout:
            print(f"\nStandard Output:\n{result.stdout}")
        if result.stderr:
            print(f"\nError Output:\n{result.stderr}")
    except subprocess.TimeoutExpired:
        print(f"Error: Command timed out after {args.timeout} seconds"); return 1
    except Exception as e:
        print(f"Error: {e}"); return 1
    return 0


def cmd_edit_file(args) -> int:
    p = args.file_path
    if not is_safe_path(p):
        print(f"Error: Unsafe file path: {p}"); return 1
    if not is_allowed_file(p):
        print(f"Error: File type not allowed: {Path(p).suffix}"); return 1
    path = Path(p)
    if not path.exists():
        print(f"Error: File does not exist: {p}"); return 1
    content = read_file_content(str(path))
    if content is None:
        print(f"Error: Unable to read file: {p}"); return 1

    old_string = _read_string_arg(args.old_string, args.old_file, False)
    new_string = _read_string_arg(args.new_string, args.new_file, False)
    if old_string is None or new_string is None:
        print("Error: must provide both old_string and new_string (use --old-file/--new-file for multi-line)")
        return 1

    count = content.count(old_string)
    if count == 0:
        print(f"Error: old_string not found in {p}"); return 1
    if count > 1:
        print(f"Error: old_string found {count} times in {p}. Provide more context to make it unique.")
        return 1
    new_content = content.replace(old_string, new_string, 1)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Successfully edited {p}: replaced 1 occurrence.")
    except Exception as e:
        print(f"Error writing file: {e}"); return 1
    return 0


def cmd_read_file_lines(args) -> int:
    p = args.file_path
    if not is_safe_path(p):
        print(f"Error: Unsafe file path: {p}"); return 1
    if not is_allowed_file(p):
        print(f"Error: File type not allowed: {Path(p).suffix}"); return 1
    path = Path(p)
    if not path.exists():
        print(f"Error: File does not exist: {p}"); return 1
    content = read_file_content(str(path))
    if content is None:
        print(f"Error: Unable to read file: {p}"); return 1
    lines = content.splitlines(keepends=True)
    total = len(lines)
    start = max(1, args.start_line) - 1
    end = total if args.end_line <= 0 else min(args.end_line, total)
    selected = lines[start:end]
    print(f"File: {p} (lines {start+1}-{end} of {total})")
    for i, line in enumerate(selected):
        sys.stdout.write(f"{i + start + 1:>6}\t{line}")
    if selected and not selected[-1].endswith('\n'):
        sys.stdout.write('\n')
    return 0


def cmd_find_files(args) -> int:
    if not is_safe_path(args.directory):
        print(f"Error: Unsafe path: {args.directory}"); return 1
    path = Path(args.directory)
    if not path.exists() or not path.is_dir():
        print(f"Error: Directory does not exist: {args.directory}"); return 1
    matches = []
    try:
        for m in sorted(path.rglob(args.pattern)):
            try:
                rel = m.relative_to(path)
            except ValueError:
                continue
            if len(rel.parts) > args.max_depth:
                continue
            t = "FILE" if m.is_file() else "DIR "
            size = m.stat().st_size if m.is_file() else 0
            matches.append(f"{t} {str(rel):<60} {size:>10,} bytes")
            if len(matches) >= 500:
                matches.append("... (truncated at 500 results)")
                break
    except Exception as e:
        print(f"Error finding files: {e}"); return 1
    if not matches:
        print(f"No files matching '{args.pattern}' in {path.absolute()}"); return 0
    print(f"Found {len(matches)} matches for '{args.pattern}' in {path.absolute()}:")
    print('\n'.join(matches))
    return 0


def cmd_get_current_directory(args) -> int:
    print(f"Current working directory: {Path.cwd().absolute()}")
    return 0


def cmd_create_directory(args) -> int:
    if not is_safe_path(args.directory_path):
        print(f"Error: Unsafe directory path: {args.directory_path}"); return 1
    try:
        path = Path(args.directory_path)
        path.mkdir(parents=True, exist_ok=True)
        print(f"Successfully created directory: {path.absolute()}")
    except Exception as e:
        print(f"Error creating directory: {e}"); return 1
    return 0


def cmd_search_files_rg(args) -> int:
    if not is_safe_path(args.search_path):
        print(f"Error: Unsafe search path: {args.search_path}"); return 1
    path = Path(args.search_path)
    if not path.exists() or not path.is_dir():
        print(f"Error: Search path is not a directory: {args.search_path}"); return 1

    rg_bin = os.environ.get('RG_PATH', RG_DEFAULT_PATH)
    use_rg = True
    try:
        subprocess.run([rg_bin, '--version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        use_rg = False

    if use_rg:
        cmd = [rg_bin, '--color=never', '-n']
        if not args.case_sensitive:
            cmd.append('-i')
        if args.context_lines > 0:
            cmd.extend(['-C', str(args.context_lines)])
        if args.file_type:
            cmd.extend(['-t', args.file_type.lstrip('.')])
        cmd.extend(['-m', str(args.max_results), args.pattern, str(path.absolute())])
    else:
        # Fallback: grep -rn
        cmd = ['grep', '-rn']
        if not args.case_sensitive:
            cmd.append('-i')
        if args.context_lines > 0:
            cmd.extend(['-C', str(args.context_lines)])
        if args.file_type:
            cmd.extend(['--include', f'*.{args.file_type.lstrip(".")}'])
        cmd.extend(['-m', str(args.max_results), args.pattern, str(path.absolute())])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            encoding='utf-8', errors='replace',
        )
        if result.returncode > 1:
            print(f"Error running search: {result.stderr}"); return 1
        if result.returncode == 1 or not result.stdout.strip():
            print(f"No matches found for pattern: {args.pattern}")
            print(f"Search path: {path.absolute()}")
            return 0
        print(f"Search Results for: {args.pattern}")
        print(f"Search Path: {path.absolute()}")
        print(f"Case Sensitive: {args.case_sensitive}")
        if args.file_type:
            print(f"File Type: {args.file_type}")
        print('-' * 80)
        print(result.stdout)
    except subprocess.TimeoutExpired:
        print("Error: Search timed out after 30 seconds"); return 1
    except Exception as e:
        print(f"Error executing search: {e}"); return 1
    return 0


# ─── Entry point ────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(
        description="Filesystem operations CLI (skill replacement for filesystem-command MCP server)"
    )
    sub = p.add_subparsers(dest='cmd', required=True, metavar='SUBCOMMAND')

    sp = sub.add_parser('read_file', help='Read a text file')
    sp.add_argument('file_path')
    sp.set_defaults(func=cmd_read_file)

    sp = sub.add_parser('write_file', help='Write a text file (overwrites)')
    sp.add_argument('file_path')
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument('--content', default=None, help='Content as string')
    g.add_argument('--content-file', default=None, help='Read content from file')
    g.add_argument('--stdin', action='store_true', help='Read content from stdin')
    sp.add_argument('--encoding', default=DEFAULT_ENCODING)
    sp.set_defaults(func=cmd_write_file)

    sp = sub.add_parser('append_file', help='Append to a text file')
    sp.add_argument('file_path')
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument('--content', default=None)
    g.add_argument('--content-file', default=None)
    g.add_argument('--stdin', action='store_true')
    sp.add_argument('--encoding', default=DEFAULT_ENCODING)
    sp.set_defaults(func=cmd_append_file)

    sp = sub.add_parser('list_directory', help='List directory contents')
    sp.add_argument('directory_path', nargs='?', default='.')
    sp.add_argument('--show-hidden', action='store_true')
    sp.set_defaults(func=cmd_list_directory)

    sp = sub.add_parser('get_file_info', help='Show file/dir metadata')
    sp.add_argument('file_path')
    sp.set_defaults(func=cmd_get_file_info)

    sp = sub.add_parser('execute_command', help='Run a shell command (dangerous ones blocked)')
    sp.add_argument('command')
    sp.add_argument('--cwd', default='.')
    sp.add_argument('--timeout', type=int, default=30)
    sp.set_defaults(func=cmd_execute_command)

    sp = sub.add_parser('edit_file', help='Precise string replacement (one occurrence)')
    sp.add_argument('file_path')
    sp.add_argument('--old-string', default=None, help='Inline old text (single line)')
    sp.add_argument('--new-string', default=None, help='Inline new text (single line)')
    sp.add_argument('--old-file', default=None, help='File containing exact old text (multi-line safe)')
    sp.add_argument('--new-file', default=None, help='File containing replacement text (multi-line safe)')
    sp.set_defaults(func=cmd_edit_file)

    sp = sub.add_parser('read_file_lines', help='Read a line range from a file')
    sp.add_argument('file_path')
    sp.add_argument('--start-line', type=int, default=1)
    sp.add_argument('--end-line', type=int, default=0, help='0 = read to end')
    sp.set_defaults(func=cmd_read_file_lines)

    sp = sub.add_parser('find_files', help='Glob-find files recursively')
    sp.add_argument('directory', nargs='?', default='.')
    sp.add_argument('--pattern', default='*')
    sp.add_argument('--max-depth', type=int, default=5)
    sp.set_defaults(func=cmd_find_files)

    sp = sub.add_parser('get_current_directory', help='Print cwd')
    sp.set_defaults(func=cmd_get_current_directory)

    sp = sub.add_parser('create_directory', help='Create a directory tree')
    sp.add_argument('directory_path')
    sp.set_defaults(func=cmd_create_directory)

    sp = sub.add_parser('search_files_rg', help='Search file contents with rg / ripgrep (grep fallback)')
    sp.add_argument('pattern')
    sp.add_argument('search_path', nargs='?', default='.')
    sp.add_argument('--file-type', default=None, help="ripgrep type, e.g. py, js, clj")
    sp.add_argument('--case-sensitive', action='store_true')
    sp.add_argument('--max-results', type=int, default=100, help="max matches per file (rg -m)")
    sp.add_argument('--context-lines', type=int, default=0)
    sp.set_defaults(func=cmd_search_files_rg)

    args = p.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == '__main__':
    main()

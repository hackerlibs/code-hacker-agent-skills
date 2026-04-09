#!/usr/bin/env python3
"""
Memory Store CLI — markdown-based persistent memory for Code Hacker.

Replaces the memory-store MCP server (which used CozoDB) with a plain
markdown-on-disk format. Each memory is one file under

    .agent-memory/<category>/<slug>.md

with YAML-style frontmatter for metadata and a markdown body for content.
The directory lives under the current working directory, so memories are
naturally scoped to the project / workspace where the agent is running.

Why markdown instead of JSON or a database:

- The user can read, grep, and hand-edit memories in any editor.
- They survive moving the project — they're just files in a hidden dir.
- They're trivially version-controllable if the user wants to commit them.
- Recall is just plain text search.

Usage:

    python skills/memory/memory.py save \\
        --title "airflow dag retry storm fix" \\
        --category pipeline \\
        --problem "DAG keeps retrying after upstream outage" \\
        --solution "on_failure_callback that calls dag.set_state(FAILED)" \\
        --pattern "Airflow has no built-in circuit breaker" \\
        --tags "airflow,retry,pipeline"

    python skills/memory/memory.py search "airflow retry"
    python skills/memory/memory.py get airflow-dag-retry-storm-fix
    python skills/memory/memory.py list --category email_customer
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional


MEMORY_DIR = Path.cwd() / ".agent-memory"

# Suggested categories — not enforced, the user can invent new ones.
SUGGESTED_CATEGORIES = [
    "pipeline",
    "email_customer",
    "email_internal",
    "jira_template",
    "bug_fix",
    "devops_lib",
    "ai_knowledge",
    "qa_experience",
    "general",
]


# ─── Helpers ────────────────────────────────────────────────────────────────
def _slugify(text: str) -> str:
    """Filesystem-safe slug. Keeps ASCII letters/digits and CJK chars."""
    s = text.lower().strip()
    # Keep alnum, CJK ideographs, hyphen, underscore, whitespace
    s = re.sub(r'[^a-z0-9\u4e00-\u9fff\-_\s]', '', s)
    s = re.sub(r'\s+', '-', s)
    s = re.sub(r'-+', '-', s)
    s = s.strip('-_')
    return s[:80] or 'untitled'


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _category_dir(category: str) -> Path:
    return MEMORY_DIR / category


def _ensure_category_dir(category: str) -> Path:
    d = _category_dir(category)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _memory_path(category: str, title: str) -> Path:
    return _ensure_category_dir(category) / f"{_slugify(title)}.md"


def _parse_frontmatter(text: str) -> tuple:
    """Parse '--- ... ---' frontmatter. Returns (meta dict, body str)."""
    if not text.startswith('---\n'):
        return {}, text
    end = text.find('\n---\n', 4)
    if end == -1:
        return {}, text
    fm_block = text[4:end]
    body = text[end + 5:]
    meta: dict = {}
    for line in fm_block.splitlines():
        if ':' not in line:
            continue
        key, _, val = line.partition(':')
        key = key.strip()
        val = val.strip()
        # Bracketed list: [a, b, c]
        if val.startswith('[') and val.endswith(']'):
            inner = val[1:-1]
            meta[key] = [v.strip().strip("'\"") for v in inner.split(',') if v.strip()]
        else:
            meta[key] = val
    return meta, body


def _format_frontmatter(meta: dict) -> str:
    lines = ['---']
    for k, v in meta.items():
        if k.startswith('_'):
            continue  # internal-only fields
        if isinstance(v, list):
            inner = ', '.join(str(x) for x in v)
            lines.append(f"{k}: [{inner}]")
        else:
            lines.append(f"{k}: {v}")
    lines.append('---')
    return '\n'.join(lines)


def _read_memory(path: Path) -> Optional[dict]:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding='utf-8')
    except Exception:
        return None
    meta, body = _parse_frontmatter(text)
    meta['_path'] = str(path)
    meta['_body'] = body.strip()
    return meta


def _write_memory(path: Path, meta: dict, body: str) -> None:
    text = _format_frontmatter(meta) + '\n\n' + body.rstrip() + '\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _all_memory_files() -> list:
    if not MEMORY_DIR.exists():
        return []
    return sorted(p for p in MEMORY_DIR.glob('**/*.md') if not p.name.startswith('_'))


def _read_string_arg(direct: Optional[str], from_file: Optional[str]) -> Optional[str]:
    """Resolve a string argument from --x or --x-file."""
    if from_file:
        try:
            return Path(from_file).read_text(encoding='utf-8').strip()
        except Exception as e:
            print(f"Warning: could not read {from_file}: {e}")
            return None
    return direct


def _resolve_id(memory_id: str) -> Optional[Path]:
    """Resolve a memory id to a file path. Accepts 'category/slug', 'slug', or 'category/slug.md'."""
    # Direct path forms first
    if '/' in memory_id:
        cat, slug = memory_id.split('/', 1)
        slug = slug[:-3] if slug.endswith('.md') else slug
        candidate = MEMORY_DIR / cat / f"{slug}.md"
        if candidate.is_file():
            return candidate
    # Search every category for matching stem
    for f in _all_memory_files():
        if f.stem == memory_id or f.stem == _slugify(memory_id):
            return f
    return None


def _bump_usage(path: Path) -> None:
    mem = _read_memory(path)
    if not mem:
        return
    try:
        cur = int(mem.get('usage_count', '0'))
    except Exception:
        cur = 0
    mem['usage_count'] = str(cur + 1)
    body = mem.pop('_body', '')
    mem.pop('_path', None)
    _write_memory(path, mem, body)


# ─── Commands ───────────────────────────────────────────────────────────────
def cmd_save(args) -> int:
    title = args.title
    category = args.category

    # Resolve every section: prefer --field-file, fall back to --field
    problem  = _read_string_arg(args.problem,  args.problem_file)  or ''
    context  = _read_string_arg(args.context,  args.context_file)  or ''
    solution = _read_string_arg(args.solution, args.solution_file) or ''
    pattern  = _read_string_arg(args.pattern,  args.pattern_file)  or ''

    # --stdin loads the largest free-form field (defaults to solution)
    if args.stdin:
        stdin_content = sys.stdin.read().strip()
        target = args.stdin_field
        if target == 'solution':
            solution = stdin_content
        elif target == 'context':
            context = stdin_content
        elif target == 'problem':
            problem = stdin_content
        elif target == 'pattern':
            pattern = stdin_content

    tags_list = [t.strip() for t in args.tags.split(',') if t.strip()] if args.tags else []

    path = _memory_path(category, title)

    # Preserve created_at and usage_count if updating
    existing = _read_memory(path)
    created_at = existing.get('created_at') if existing else _now()
    usage_count = existing.get('usage_count', '0') if existing else '0'

    meta = {
        'title': title,
        'category': category,
        'tags': tags_list,
        'created_at': created_at,
        'updated_at': _now(),
        'usage_count': usage_count,
    }

    # Build the markdown body
    body_parts = [f"# {title}", ""]
    if problem:
        body_parts.extend(["## Problem", "", problem, ""])
    if context:
        body_parts.extend(["## Context", "", context, ""])
    if solution:
        body_parts.extend(["## Solution", "", solution, ""])
    if pattern:
        body_parts.extend(["## Reusable Pattern", "", pattern, ""])
    body = '\n'.join(body_parts).strip() + '\n'

    _write_memory(path, meta, body)
    rel = path.relative_to(Path.cwd()) if path.is_absolute() and Path.cwd() in path.parents else path
    print(f"Memory saved: '{title}' [{category}]")
    print(f"  -> {rel}")
    return 0


def cmd_get(args) -> int:
    path = _resolve_id(args.id)
    if not path:
        print(f"Memory not found: '{args.id}'")
        print("Tip: run `python skills/memory/memory.py search <query>` to find the id")
        return 1
    _bump_usage(path)
    # Print the full file (frontmatter + body) so the agent can use it directly
    sys.stdout.write(path.read_text(encoding='utf-8'))
    if not path.read_text(encoding='utf-8').endswith('\n'):
        sys.stdout.write('\n')
    return 0


def cmd_search(args) -> int:
    query = (args.query or '').lower()
    results: list = []
    for path in _all_memory_files():
        mem = _read_memory(path)
        if not mem:
            continue
        if args.category and mem.get('category') != args.category:
            continue
        if args.tag:
            tags = mem.get('tags', [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(',')]
            if args.tag not in tags:
                continue
        if query:
            tags_str = mem.get('tags', '')
            if isinstance(tags_str, list):
                tags_str = ' '.join(tags_str)
            haystack = ' '.join([
                str(mem.get('title', '')),
                str(tags_str),
                mem.get('_body', ''),
            ]).lower()
            if query not in haystack:
                continue
        results.append((path, mem))
        if len(results) >= args.limit:
            break

    if not results:
        if not MEMORY_DIR.exists():
            print(f"No memories found. ({MEMORY_DIR} does not exist yet)")
        else:
            print("No memories found matching the criteria.")
        return 0

    print(f"Found {len(results)} memories:\n")
    for path, mem in results:
        title = mem.get('title', path.stem)
        cat = mem.get('category', '?')
        tags = mem.get('tags', [])
        tag_str = ', '.join(tags) if isinstance(tags, list) else str(tags)
        usage = mem.get('usage_count', '0')
        print(f"  [{cat}] {title}")
        print(f"    id: {path.stem}    used: {usage}x    tags: {tag_str}")
        body = mem.get('_body', '')
        preview = re.sub(r'\s+', ' ', body).strip()[:160]
        if preview:
            print(f"    {preview}...")
        print()
    return 0


def cmd_list(args) -> int:
    files = _all_memory_files()
    if args.category:
        files = [f for f in files if f.parent.name == args.category]

    if not files:
        msg = "No memories stored."
        if args.category:
            msg += f" (category filter: {args.category})"
        print(msg)
        return 0

    by_cat: dict = {}
    for path in files:
        mem = _read_memory(path)
        if not mem:
            continue
        cat = mem.get('category', path.parent.name)
        by_cat.setdefault(cat, []).append((path, mem))

    print(f"Total memories: {len(files)}\n")
    for cat in sorted(by_cat.keys()):
        items = by_cat[cat]
        items.sort(key=lambda x: x[1].get('updated_at', ''), reverse=True)
        print(f"--- {cat} ({len(items)}) ---")
        for path, mem in items[:args.limit]:
            title = mem.get('title', path.stem)
            updated = mem.get('updated_at', '?')
            usage = mem.get('usage_count', '0')
            print(f"  {title}")
            print(f"    id: {path.stem}    updated: {updated}    used: {usage}x")
        print()
    return 0


def cmd_delete(args) -> int:
    path = _resolve_id(args.id)
    if not path:
        print(f"Memory not found: '{args.id}'")
        return 1
    path.unlink()
    print(f"Memory deleted: {path.relative_to(Path.cwd()) if Path.cwd() in path.parents else path}")
    return 0


def cmd_categories(args) -> int:
    files = _all_memory_files()
    by_cat: dict = {}
    for path in files:
        cat = path.parent.name
        by_cat[cat] = by_cat.get(cat, 0) + 1
    if not by_cat:
        print("No categories yet.")
        print(f"Suggested categories: {', '.join(SUGGESTED_CATEGORIES)}")
        return 0
    print(f"Categories ({len(by_cat)}):")
    for cat in sorted(by_cat.keys()):
        print(f"  {cat}: {by_cat[cat]} memories")
    return 0


def cmd_top_used(args) -> int:
    items: list = []
    for path in _all_memory_files():
        mem = _read_memory(path)
        if not mem:
            continue
        try:
            usage = int(mem.get('usage_count', '0'))
        except Exception:
            usage = 0
        if usage > 0:
            items.append((usage, path, mem))
    items.sort(key=lambda x: -x[0])
    items = items[:args.limit]

    if not items:
        print("No memories have been recalled yet (usage_count is 0 for all).")
        return 0

    print(f"Top {len(items)} most-used memories:\n")
    for usage, path, mem in items:
        title = mem.get('title', path.stem)
        cat = mem.get('category', '?')
        print(f"  {usage:>4}x  [{cat}]  {title}")
        print(f"          id: {path.stem}")
    return 0


# ─── Scratchpads (short-lived working memory) ───────────────────────────────
def _scratchpad_path(name: str) -> Path:
    safe = re.sub(r'[^a-zA-Z0-9_\-]', '_', name) or 'default'
    return MEMORY_DIR / f"_scratchpad_{safe}.md"


def cmd_scratchpad_write(args) -> int:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    content = sys.stdin.read() if args.stdin else (args.content or '')
    path = _scratchpad_path(args.name)
    path.write_text(content, encoding='utf-8')
    print(f"Scratchpad '{args.name}' updated ({len(content)} chars) -> {path}")
    return 0


def cmd_scratchpad_read(args) -> int:
    path = _scratchpad_path(args.name)
    if not path.exists():
        print(f"(scratchpad '{args.name}' is empty)")
        return 0
    sys.stdout.write(path.read_text(encoding='utf-8'))
    return 0


def cmd_scratchpad_append(args) -> int:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    content = sys.stdin.read() if args.stdin else (args.content or '')
    path = _scratchpad_path(args.name)
    existing = path.read_text(encoding='utf-8') if path.exists() else ''
    sep = '' if (not existing) or existing.endswith('\n') else '\n'
    path.write_text(existing + sep + content, encoding='utf-8')
    print(f"Appended to scratchpad '{args.name}' (+{len(content)} chars)")
    return 0


# ─── Entry point ────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(
        description="Markdown-based persistent memory store (skill replacement for memory-store MCP server)"
    )
    sub = p.add_subparsers(dest='cmd', required=True, metavar='SUBCOMMAND')

    # save
    sp = sub.add_parser('save', help='Save / update a memory (idempotent on title+category)')
    sp.add_argument('--title', required=True)
    sp.add_argument('--category', default='general',
                    help=f"e.g. {', '.join(SUGGESTED_CATEGORIES)}")
    sp.add_argument('--problem', default=None)
    sp.add_argument('--problem-file', default=None)
    sp.add_argument('--context', default=None)
    sp.add_argument('--context-file', default=None)
    sp.add_argument('--solution', default=None)
    sp.add_argument('--solution-file', default=None)
    sp.add_argument('--pattern', default=None)
    sp.add_argument('--pattern-file', default=None)
    sp.add_argument('--tags', default='', help='comma-separated tags')
    sp.add_argument('--stdin', action='store_true', help='read content from stdin')
    sp.add_argument('--stdin-field', default='solution',
                    choices=['solution', 'context', 'problem', 'pattern'],
                    help='which field to load from stdin (default: solution)')
    sp.set_defaults(func=cmd_save)

    # get
    sp = sub.add_parser('get', help='Fetch a memory by id and bump its usage counter')
    sp.add_argument('id', help='slug or category/slug')
    sp.set_defaults(func=cmd_get)

    # search
    sp = sub.add_parser('search', help='Full-text search across all memories')
    sp.add_argument('query', nargs='?', default='')
    sp.add_argument('--category', default=None)
    sp.add_argument('--tag', default=None)
    sp.add_argument('--limit', type=int, default=20)
    sp.set_defaults(func=cmd_search)

    # list
    sp = sub.add_parser('list', help='List memories grouped by category')
    sp.add_argument('--category', default=None)
    sp.add_argument('--limit', type=int, default=50)
    sp.set_defaults(func=cmd_list)

    # delete
    sp = sub.add_parser('delete', help='Delete a memory')
    sp.add_argument('id')
    sp.set_defaults(func=cmd_delete)

    # categories
    sp = sub.add_parser('categories', help='Count memories per category')
    sp.set_defaults(func=cmd_categories)

    # top_used
    sp = sub.add_parser('top_used', help='Most-recalled memories')
    sp.add_argument('--limit', type=int, default=10)
    sp.set_defaults(func=cmd_top_used)

    # scratchpads
    sp = sub.add_parser('scratchpad_write', help='Write a named short-lived scratchpad')
    sp.add_argument('--name', default='default')
    sp.add_argument('--content', default=None)
    sp.add_argument('--stdin', action='store_true')
    sp.set_defaults(func=cmd_scratchpad_write)

    sp = sub.add_parser('scratchpad_read', help='Read a named scratchpad')
    sp.add_argument('--name', default='default')
    sp.set_defaults(func=cmd_scratchpad_read)

    sp = sub.add_parser('scratchpad_append', help='Append to a scratchpad')
    sp.add_argument('--name', default='default')
    sp.add_argument('--content', default=None)
    sp.add_argument('--stdin', action='store_true')
    sp.set_defaults(func=cmd_scratchpad_append)

    args = p.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == '__main__':
    main()

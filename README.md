# Code Hacker Skills

A small repository containing local skill wrappers for a VS Code Copilot-like agent environment.

## Project structure

- `code-hacker-skills.agent.md` — agent manifest and guidance for using the skills.
- `skills/filesystem/` — `fs.py` and its `SKILL.md`, a local filesystem skill wrapper.
- `skills/git-tools/` — `git_ops.py` and its `SKILL.md`, a git wrapper skill.
- `skills/memory/` — `memory.py` and its `SKILL.md`, a persistent memory skill.
- `skills/multi-project/` — `workspace.py` and its `SKILL.md`, a multi-repo workspace skill.

## Purpose

This repository provides reusable CLI skill implementations for environments where the original MCP skill servers are not available. It is useful for building and testing the agent's file, git, multi-project, and memory workflows locally.

## Usage examples

- Read a file:
  `python skills/filesystem/fs.py read_file code-hacker-skills.agent.md`
- Inspect git status:
  `python skills/git-tools/git_ops.py status`
- Save or query agent memory:
  `python skills/memory/memory.py save --title "example" --category general --problem "..." --solution "..."`
- Manage a workspace across repos:
  `python skills/multi-project/workspace.py workspace_list`

## Notes

- Each skill exposes a `--help` flag for full usage information.
- The repo is designed for Python 3 and uses standard library scripts for the wrappers.

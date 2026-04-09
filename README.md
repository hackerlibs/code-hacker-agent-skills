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

## Using the custom agent in VS Code

1. Open this repository folder in VS Code.
2. Install the GitHub Copilot Chat extension if it is not already installed.
3. Sign in to Copilot Chat and open the Copilot Chat panel.
4. The `code-hacker-skills.agent.md` manifest is located at the repository root. Copilot Chat should detect it as a custom agent in the Agents or Custom Agents list.
5. Select the custom agent named `Code Hacker (Skills Edition)` or import the manifest file if the extension provides an import action.
6. Ask questions in the chat. The agent can use the local skill wrappers under `skills/` to inspect files, run git operations, manage memory, and coordinate multi-project tasks.

## Installing the custom agent to VS Code

- This repository is not a VS Code extension. The custom agent is enabled by opening the repo in VS Code and loading the `code-hacker-skills.agent.md` manifest through GitHub Copilot Chat.
- Make sure Python 3 is installed on your system, because the skill scripts are Python CLI wrappers.
- If you want to reuse the agent in another workspace, copy `code-hacker-skills.agent.md` into that workspace root or import it through the Copilot Chat custom agent interface.

## Install scripts

- On macOS/Linux, run:
  `./install.sh`
- On Windows PowerShell, run:
  `./install.ps1`

You can also install into another workspace by passing a target directory:

- `./install.sh /path/to/other/workspace`
- `./install.ps1 -TargetDir 'C:\path\to\other\workspace'`

In that case, the script copies `code-hacker-skills.agent.md` and the `skills/` directory into the target workspace root.

## Notes

- Each skill exposes a `--help` flag for full usage information.
- The repo is designed for Python 3 and uses standard library scripts for the wrappers.

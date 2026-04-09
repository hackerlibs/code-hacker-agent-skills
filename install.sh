#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

TARGET_DIR="$ROOT_DIR"
if [ $# -gt 0 ]; then
  TARGET_DIR="$(cd "$1" && pwd)"
fi

info() { printf "\033[1;34m%s\033[0m\n" "$*"; }
error() { printf "\033[1;31mERROR: %s\033[0m\n" "$*" >&2; exit 1; }

if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD=python
else
  error "Python 3 is required. Install Python 3 and rerun this script."
fi

if ! "$PYTHON_CMD" -c 'import sys; assert sys.version_info >= (3,8)' >/dev/null 2>&1; then
  error "Python 3.8+ is required. Detected: $($PYTHON_CMD --version 2>&1 | head -n 1)"
fi

if [ ! -f code-hacker-skills.agent.md ]; then
  error "Manifest file code-hacker-skills.agent.md not found in repository root."
fi

if [ ! -d skills ]; then
  error "skills directory not found in repository root."
fi

if [ "$TARGET_DIR" != "$ROOT_DIR" ]; then
  info "Installing custom agent files into: $TARGET_DIR"
  mkdir -p "$TARGET_DIR"
  cp -R code-hacker-skills.agent.md "$TARGET_DIR/"
  rm -rf "$TARGET_DIR/skills"
  cp -R skills "$TARGET_DIR/"
  info "Copied manifest and skills/ into target workspace."
else
  info "Running install validation in current repo root."
fi

info "Python OK: $($PYTHON_CMD --version 2>&1 | head -n 1)"

if command -v code >/dev/null 2>&1; then
  if code --list-extensions | grep -qi 'github.copilot-chat'; then
    info "VS Code CLI and GitHub Copilot Chat extension are installed."
  else
    info "GitHub Copilot Chat extension is not installed."
    read -r -p "Install it now with VS Code CLI? [y/N] " install_ext
    if [[ "$install_ext" =~ ^[Yy]$ ]]; then
      code --install-extension GitHub.copilot-chat || error "Failed to install GitHub Copilot Chat extension."
      info "Installed GitHub Copilot Chat extension."
    fi
  fi
else
  info "VS Code CLI ('code') is not available."
  info "Open VS Code and install the 'code' command from the Command Palette."
fi

info "Install script complete."
info "Open $TARGET_DIR in VS Code and load code-hacker-skills.agent.md as a custom Copilot Chat agent."

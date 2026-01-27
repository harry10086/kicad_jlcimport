#!/usr/bin/env bash
# Source this file:  source install.sh
# Creates the venv on first run, activates it, and installs dev dependencies.
# On subsequent runs, just activates the existing venv.

sourced=0
if [ -n "$ZSH_EVAL_CONTEXT" ]; then
    [[ "$ZSH_EVAL_CONTEXT" =~ :file$ ]] && sourced=1
elif [ -n "$BASH_SOURCE" ]; then
    [[ "$0" != "${BASH_SOURCE[0]}" ]] && sourced=1
fi

if [ "$sourced" -eq 0 ]; then
    echo "Error: this script must be sourced, not executed."
    echo "  source install.sh"
    exit 1
fi

cd "$(dirname "${BASH_SOURCE[0]:-$0}")"

if [ ! -d .venv ]; then
    echo "Creating venv..."
    python3 -m venv .venv
    echo "Activating venv..."
    source .venv/bin/activate
    echo "Installing dev dependencies..."
    pip install -e '.[dev,gui,tui]'
    echo "Done. Ready to develop."
else
    echo "Activating venv..."
    source .venv/bin/activate
    echo "Ready."
fi

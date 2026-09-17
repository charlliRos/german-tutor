#!/usr/bin/env sh
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    echo "Please run ./setup.sh first."
    exit 1
fi
exec .venv/bin/python tutor.py "$@"

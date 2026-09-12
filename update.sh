#!/bin/sh
cd "$(dirname "$0")"
venv/bin/python update.py "$@"

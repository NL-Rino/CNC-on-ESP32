#!/usr/bin/env bash
# Chay o may minh: ./run.sh
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
[ -f .env ] || { cp .env.example .env; echo ">> Da tao .env - mo ra dien ANTHROPIC_API_KEY roi chay lai."; exit 1; }
exec uvicorn app.server:app --host 127.0.0.1 --port 8000 --reload

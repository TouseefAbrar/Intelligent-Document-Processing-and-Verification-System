#!/usr/bin/env bash
# One-command launcher for Linux/macOS
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Creating backend venv"
python3 -m venv "$ROOT/backend/.venv"

echo "==> Installing backend dependencies"
"$ROOT/backend/.venv/bin/pip" install -r "$ROOT/backend/requirements.txt" -q

echo "==> Checking .env"
if [ ! -f "$ROOT/backend/.env" ]; then
  cp "$ROOT/backend/.env.example" "$ROOT/backend/.env"
  echo "NOTE: created backend/.env — add your GROQ_API_KEY."
fi

echo "==> Installing frontend dependencies"
(cd "$ROOT/frontend" && npm install --no-audit --no-fund)

echo ""
echo "Start with:"
echo "  1) Backend :  cd $ROOT/backend && .venv/bin/python -m uvicorn app.main:app --reload"
echo "  2) Frontend:  cd $ROOT/frontend && npm run dev"
echo "  3) UI      :  http://localhost:5173"

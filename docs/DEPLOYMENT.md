# Deployment Guide

The backend and frontend are **independently deployable** units. Three supported paths:

## A. Local development (no Docker)

### Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate                       # Windows
pip install -r requirements.txt
copy .env.example .env                       # set GROQ_API_KEY
uvicorn app.main:app --reload --port 8000
```
- **Windows:** install the Tesseract binary first —
  `winget install UB-Mannheim.TesseractOCR` (auto-discovered by the engine).
- API + Swagger: http://localhost:8000/docs

### Frontend
```bash
cd frontend
npm install
npm run dev
```
- UI: http://localhost:5173 (Vite proxies `/api` → `localhost:8000`)

## B. Docker Compose (recommended for demo / evaluation)

```bash
# 1. configure the backend key
cp backend/.env.example backend/.env        # edit GROQ_API_KEY

# 2. build + run both services
docker compose up --build

# 3. verify
#    UI      → http://localhost:5173
#    API     → http://localhost:8000/docs
#    reports → http://localhost:5173/api/v1/submissions/1/report
```

Images:
- `backend` — `python:3.12-slim` + uvicorn, exposes 8000
- `frontend` — multi-stage: node build → Nginx static host, proxies `/api` to backend

## C. Separate production deployment

### Backend on a server (Docker)
```bash
docker build -t eef-backend ./backend
docker run -d -p 8000:8000 \
  -e GROQ_API_KEY=... \
  -e DATABASE_URL=postgresql+psycopg://eef:eef@db:5432/eef \
  -v eef_storage:/app/app/storage \
  --name eef-backend eef-backend
```

### Frontend on CDN / Nginx
```bash
cd frontend
npm ci && npm run build        # outputs dist/
# serve dist/ from any static host; route /api → backend (see nginx.conf)
```

Nginx snippet:
```nginx
location /api/ {
    proxy_pass http://backend-host:8000;
    proxy_read_timeout 300s;
    client_max_body_size 50m;
}
```

## Environment variables

See `backend/.env.example` for the full list. The two that matter most:

| Var | Required | Notes |
|---|---|---|
| `GROQ_API_KEY` | yes | https://console.groq.com/keys |
| `DATABASE_URL` | optional | defaults to SQLite; PostgreSQL: `postgresql+psycopg://user:pass@host:5432/eef` |

> To use PostgreSQL locally add `psycopg[binary]` to `requirements.txt`.

## Production hardening checklist

- Set `DEBUG=false`.
- Put the API behind a reverse proxy with TLS.
- Move storage volume to S3/minIO for scale (paths are centralised in `config.py`).
- Add a worker queue (Celery/RQ) for high upload volume.
- Rotate `GROQ_API_KEY`; keep it out of git (`.env` is gitignored).

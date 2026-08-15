# EEF — Ezitech Engineering Framework (AI-004)

## Intelligent Document Processing & Verification Engine

An AI-powered system that automatically reads, classifies, verifies and reports on
internship application documents (resumes, CNICs, degrees, transcripts, letters and
certificates) for the **Ezitech Internship Portal**.

Built by a team of 2 AI Engineers over a 4-week case-study cycle.

---

## Features

| Capability | Details |
|---|---|---|
| **Document Upload** | PDF, PNG, JPG, JPEG, TIFF, WEBP, BMP — via REST API or web UI |
| **Document Classification** | Resume, CNIC, Degree, Transcript, Internship Letter, Recommendation Letter, Certificate |
| **OCR Pipeline** | Digital-PDF text extraction (PyMuPDF) + Tesseract for scans, optional Groq vision / EasyOCR |
| **Information Extraction** | Full name, email, phone, CNIC, university, degree, graduation year, skills, experience, CGPA |
| **Verification** | Missing documents, blurry images, duplicate uploads, invalid file types, low-quality scans |
| **AI Analysis** | Completeness score, verification status, missing info, confidence score, recommended actions |
| **Forgery Detection** | Error-Level Analysis (ELA), EXIF/editing-software trail, JPEG compression artifacts, block-noise inconsistency (splice detection), content validation (CNIC format, impossible dates, fake markers) + optional LLM review |
| **Reporting** | Professional HTML + PDF verification reports for mentors & administrators |
| **Bonus: Multi-language** | Tesseract / Groq-vision support for non-Latin text |
| **Bonus: QR verification** | OpenCV QR detection & decoding on documents |
| **Bonus: Tamper detection** | Error-Level Analysis (ELA) heuristic |
| **Bonus: Expiry alerts** | Expiry-date extraction + validation |
| **Bonus: Signature detection** | Contour heuristic on documents |

### Detecting Inconsistencies — Verification

During document processing the rule-based verification engine checks every upload
for the following inconsistencies. Detected problems are attached to the document
as `verification.issues` and drive the submission-level `FAILED` / `FLAGGED` /
`PASSED` status.

| Detect | How | Source |
|---|---|---|
| **Missing Documents** | Compares stored documents against the required list (`COMPLETENESS_REQUIRED_DOCS`) and reports each missing type | `services/coverage.py` + `services/verification.py` |
| **Blurry Images** | Laplacian edge-variance falls below `BLUR_VARIANCE_THRESHOLD` → *"Image is blurry (low edge variance)"* | `services/quality.py` |
| **Duplicate Uploads** | Perceptual dHash similarity ≥ `DUPLICATE_HASH_THRESHOLD` (0.90) against other documents in the batch → marked duplicate | `services/duplicates.py` |
| **Fake / Forged Documents** | Forensic pre-scan (ELA, EXIF editing trail, JPEG blocking, block-noise inconsistency) rejects RED documents before OCR; content validation (CNIC format, impossible dates, printed "SAMPLE/VOID" markers) + optional Groq review adds YELLOW/`FORGERY DETECTED` verdicts | `services/forgery.py` |
| **Invalid File Types** | Upload rejected with **HTTP 415** when the extension is unsupported or the magic bytes don't match the claimed extension | `utils/files.py` |

## Repository Layout

```
ezitech-eef/
├── backend/                 # FastAPI REST API — deployable separately
│   ├── app/
│   │   ├── api/routes/      # health, documents, submissions endpoints
│   │   ├── core/            # logging config
│   │   ├── models/          # SQLAlchemy ORM (Document, Submission)
│   │   ├── schemas/         # Pydantic request/response models
│   │   ├── services/        # OCR, classification, extraction, verification, reporting, AI
│   │   └── storage/         # uploaded files + generated reports (gitignored)
│   ├── tests/               # unit tests (no API key needed)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/                # React + Vite SPA — deployable separately
│   ├── src/                 # components, API client, styles
│   ├── Dockerfile           # multi-stage build served by Nginx
│   └── nginx.conf           # proxies /api → backend
├── docs/                    # ARCHITECTURE, API, OCR_PIPELINE, DATABASE, DEPLOYMENT, EVALUATION
├── deployment/              # one-command launchers
├── docker-compose.yml       # run backend + frontend together
└── README.md
```

## Quick Start

### 1. Backend (Python 3.12)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows   (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt

copy .env.example .env            # then edit .env → set GROQ_API_KEY
uvicorn app.main:app --reload
```

Interactive API docs: http://localhost:8000/docs

### 2. Frontend (Node 20+)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

### 3. Docker (both together)

```bash
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend: http://localhost:8000/docs

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | — | **Required** for AI classification / extraction / analysis (text models) |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Text LLM for extraction & analysis |
| `GROQ_VISION_MODEL` | `llama-3.2-90b-vision-preview` | Vision LLM (used for scan OCR only when the account has it) |
| `OCR_PROVIDER` | `auto` | `auto` → Groq vision (if available) → Tesseract; or force `tesseract` / `easyocr` |
| `TESSERACT_CMD` | `tesseract` | Path to the Tesseract binary (required on Windows) |
| `DATABASE_URL` | `sqlite:///./ezitech.db` | SQLite by default; swap to PostgreSQL in prod |
| `DUPLICATE_HASH_THRESHOLD` | `0.90` | dHash similarity threshold for duplicates |
| `FORGERY_YELLOW_THRESHOLD` | `0.40` | Signal score at/above which a document is flagged for review |
| `FORGERY_RED_THRESHOLD` | `0.60` | Signal score at/above which a document is rejected as forged |
| `FORGERY_LLM_ENABLED` | `true` | Enable Groq review of forensic + content signals |
| `COMPLETENESS_REQUIRED_DOCS` | `resume,cnic,offer_letter,degree,transcript` | Required docs for 100% completeness |

## API Overview

```
GET  /api/v1/health                      service status + capability probe
POST /api/v1/documents/upload            upload + fully process one document
GET  /api/v1/documents/{id}              processed document detail
POST /api/v1/submissions/upload          upload a batch → verify as one submission
GET  /api/v1/submissions                 list submissions
GET  /api/v1/submissions/{id}            submission with all document details
GET  /api/v1/submissions/{id}/report     download report (?format=html|pdf)
DELETE /api/v1/submissions/{id}          delete a submission
```

## Deliverables Index

- AI Architecture Diagram → `docs/ARCHITECTURE.md` + `docs/architecture.svg`
- OCR Pipeline Documentation → `docs/OCR_PIPELINE.md`
- Database Design → `docs/DATABASE.md`
- API Documentation → `docs/API.md`
- Deployment Guide → `docs/DEPLOYMENT.md` + `deployment/`
- Evaluation Report → `docs/EVALUATION.md`
- README → this file
- Live Demonstration → run the backend + frontend per Quick Start

## Testing

```bash
cd backend
.venv\Scripts\python -m pytest -q
```

Unit tests cover classification, regex extraction, duplicate hashing and the
rule-based verification engine — they run **without** a Groq key.

## Technology Justification

| Requirement | Chosen Tech | Why |
|---|---|---|
| OCR | PyMuPDF (digital PDFs) + Tesseract (scans), optional Groq vision / EasyOCR | Reliable local scan OCR; Groq vision available for accounts with vision models |
| Classification / Extraction | Groq LLM (JSON mode) + regex fallback | Robust semantics with guaranteed deterministic fallback |
| API | FastAPI + Pydantic | Async, auto OpenAPI docs, type-safe |
| Storage | SQLAlchemy (SQLite → PostgreSQL ready) | Zero-setup dev, production path documented |
| Frontend | React + Vite + Nginx | Fast SPA, separate deployable unit |
| Containerisation | Docker + docker-compose | Reproducible deployment |

# AI Architecture — EEF Document Intelligence System

## Overview

The system is a modular, provider-based pipeline. Every document flows through the
same stages, and each stage is independently replaceable (an OCR provider can be
swapped without touching verification logic).

```
                        ┌────────────────────────────────────────────────────────────┐
                        │                    CLIENT LAYER                              │
                        │   React SPA (frontend/)      Rest clients / Postman        │
                        └───────────────┬───────────────────────────────┬────────────┘
                                        │  HTTPS / JSON (multipart upload)             │
                                        ▼                                           │
                        ┌───────────────────────────────────────────────────────────▼─┐
                        │                      REST API (FastAPI)                      │
                        │   /documents/upload · /submissions/upload · /reports        │
                        └───────────────┬─────────────────────────────────────────────┘
                                        │
                    ┌───────────────────┴────────────────────────────────────┐
                    ▼                      ▼                                 ▼
        ┌─────────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐
        │  OCR PIPELINE       │  │  CLASSIFICATION  │  │  QUALITY SIGNALS         │
        │  PyMuPDF (PDF text) │  │  Groq LLM (JSON) │  │  Laplacian blur variance │
        │  Groq vision (scan) │  │  keyword fallback │  │  brightness / contrast   │
        │  Tesseract/EasyOCR  │  └────────┬─────────┘  │  QR decode · ELA (tamper) │
        └─────────┬───────────┘           │            └───────────┬──────────────┘
                  ▼                       ▼                        ▼
        ┌─────────────────────────────────────────────────────────────────────┐
        │               INFORMATION EXTRACTION (NLP)                           │
        │   Groq LLM JSON-mode + deterministic regex fallback                  │
        │   name · email · phone · cnic · university · degree · year ·         │
        │   cgpa · skills · experience · expiry dates                          │
        └───────────────────────────┬─────────────────────────────────────────┘
                                    ▼
        ┌─────────────────────────────────────────────────────────────────────┐
        │                 CONFIDENCE SCORING + VERIFICATION                   │
        │   Rule-Based Validation Layer (missing fields, required docs,       │
        │   duplicates via dHash, file-type checks, low-quality scans)        │
        │   AI Decision Support Layer (LLM cross-check, augments rules)       │
        └───────────────────────────┬─────────────────────────────────────────┘
                                    ▼
        ┌─────────────────────────────────────────────────────────────────────┐
        │            REPORTING (HTML + PDF + JSON) + POSTGRES/SQLITE          │
        │            Logging & Monitoring (structured UTC logs)               │
        └─────────────────────────────────────────────────────────────────────┘
```

## Pipeline Stages (backend/app/services)

| # | Stage | Module | Technology | Output |
|---|---|---|---|---|
| 1 | Upload gate | `utils/files.py` | FastAPI UploadFile, magic-byte sniffing | validated stored file + SHA-256 |
| 2 | OCR | `services/ocr/` | PyMuPDF → Groq vision / Tesseract / EasyOCR | raw text + confidence + provider |
| 3 | Classification | `services/classification.py` | Groq LLM (JSON) + keyword rules | doc_type + confidence |
| 4 | Extraction | `services/extraction.py` | Groq LLM (JSON) + regex | structured field dict |
| 5 | Quality | `services/quality.py` | OpenCV (Laplacian, contrast), QRCodeDetector, ELA | quality signals |
| 6 | Duplicates | `services/duplicates.py` | dHash (imagehash) + Hamming | duplicate flag + similarity |
| 7 | Verification | `services/verification.py` | rule engine + LLM decision support | status / issues / actions |
| 8 | Reporting | `services/reporting.py` | reportlab + HTML template | HTML / PDF / JSON report |
| 9 | Persistence | `models/`, `database.py` | SQLAlchemy 2.0 (SQLite / PostgreSQL) | Document + Submission rows |
| 10 | Observability | `core/logging.py` | structured UTC logger | searchable request logs |

## Key Architectural Decisions

1. **OCR provider pattern** — an `OCRResult` contract decouples engines. `OCR_PROVIDER=auto`
   picks Groq vision when a key is present, otherwise Tesseract, otherwise EasyOCR.
2. **LLM-first, rules-always** — every AI output has a deterministic fallback so the
   system degrades gracefully when the network is unavailable. Rules never get fully
   overridden by the LLM (AI decision support only *augments*).
3. **Submission as the business unit** — documents belong to a `Submission`; completeness
   is scored against the required document set, mirroring the real Ezitech workflow.
4. **Separately deployable units** — backend and frontend each have their own Dockerfile,
   configuration and dependency graph; `docker-compose.yml` wires them for a demo.
5. **Database-agnostic ORM** — SQLAlchemy makes the switch from SQLite → PostgreSQL a
   one-line `DATABASE_URL` change.

## Scalability Notes

- OCR / classification / extraction are async I/O-bound — trivially parallelisable with
  `asyncio.gather` or a worker queue (Celery/RQ) for high volume.
- Providers are stateless, so horizontal scale-out is configuration only.
- Storage (files + reports) is volume-mounted, ready to move to S3/minIO.
- A MongoDB adapter could replace SQLAlchemy for a document-native store; the JSON columns
  already mirror that shape.

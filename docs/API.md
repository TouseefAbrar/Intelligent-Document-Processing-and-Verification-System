# API Documentation

Base URL (local): `http://localhost:8000` · Interactive docs at `/docs` (Swagger UI) and `/redoc`.

All endpoints are versioned under `/api/v1`. Uploads are `multipart/form-data`.

---

## GET `/api/v1/health`

Service status + capability probe.

```json
{
  "status": "ok",
  "app": "Ezitech Document Intelligence API",
  "version": "1.0.0",
  "groq_connected": true,
  "ocr_provider": "auto"
}
```

## POST `/api/v1/documents/upload`

Upload and fully process **one** document.

**Request:** `multipart/form-data` · field `file`

**Response `201`:**

```json
{
  "id": 3,
  "file_name": "resume.pdf",
  "doc_type": "resume",
  "classification_confidence": 0.93,
  "ocr_confidence": 0.9,
  "verification_status": "PASSED",
  "language": "en",
  "file_size": 24576,
  "ocr_provider": "groq-vision",
  "raw_text_preview": "CURRICULUM VITAE\nName: Ali Raza...",
  "extracted": {
    "full_name": "Ali Raza",
    "email": "ali.raza@example.com",
    "skills": ["Python", "FastAPI"]
  },
  "quality": { "blur": 412.1, "quality_score": 1.0, "is_low_quality": false },
  "duplicate": { "is_duplicate": false, "similarity": 0.0 },
  "verification": {
    "status": "PASSED",
    "confidence": 0.9,
    "issues": [],
    "recommended_actions": ["No action required — document verified automatically"]
  }
}
```

**Errors:** `400` empty · `413` too large · `415` unsupported/mismatched type · `422` processing failed.

## GET `/api/v1/documents/{id}`

Fetch a previously processed document. Response shape identical to the upload response.

## POST `/api/v1/submissions/upload`

Upload a **batch** of documents and verify them as one applicant submission.

**Request:** `multipart/form-data`

| Field | Type | Description |
|---|---|---|
| `files` | files (repeatable) | one or more documents |
| `applicant_ref` | string | optional applicant reference |

**Response `201`:** full submission (summary + all document details).

## GET `/api/v1/submissions`

List submissions (newest first, max 100). Returns summary-level objects.

## GET `/api/v1/submissions/{id}`

Full submission detail: summary, completeness, confidence, missing/duplicate docs and
per-document extraction + verification.

## GET `/api/v1/submissions/{id}/report`

Download the verification report.

| Query param | Value | Output |
|---|---|---|
| `format` | `html` (default) | styled HTML report |
| `format` | `pdf` | PDF report (reportlab) |

## DELETE `/api/v1/submissions/{id}`

Delete a submission, its stored files and generated reports. `204` on success.

---

## Verification status semantics

| Status | Meaning |
|---|---|
| `PASSED` | All checks passed, no critical/warning issues |
| `FLAGGED` | Passed critical checks but has warnings or missing optional fields → human review |
| `FAILED` | Critical issue (no OCR text, duplicate, missing required field/CNIC, etc.) → re-upload |

## Completeness

`completeness_score = present_required_docs / total_required_docs`, where required docs
default to `["resume", "cnic", "degree", "transcript"]` (configurable via
`COMPLETENESS_REQUIRED_DOCS`).

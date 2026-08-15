# Database Design

SQLAlchemy 2.0 ORM · default SQLite (zero-setup) · PostgreSQL-ready via `DATABASE_URL`.

## Entity Relationship Diagram

```
┌────────────────────────────┐
│         submissions        │ 1 ──── *  ┌──────────────────────────┐
│────────────────────────────│           │         documents        │
│ id (PK)                    │           │──────────────────────────│
│ applicant_ref    varchar   │           │ id (PK)                  │
│ status           varchar   │           │ submission_id (FK)       │
│ completeness_score float   │           │ file_name      varchar   │
│ overall_confidence float   │           │ stored_path    varchar   │
│ missing_documents json     │           │ file_size      int       │
│ duplicate_documents json   │           │ mime_type      varchar   │
│ summary           json     │           │ extension      varchar   │
│ report_path       varchar  │           │ sha256         varchar(64)│
│ report_data       json     │           │ page_count      int      │
│ created_at        datetime │           │ ocr_provider    varchar  │
└────────────────────────────┘           │ raw_text        text     │
                                         │ ocr_confidence  float    │
                                         │ language        varchar  │
                                         │ doc_type        varchar  │
                                         │ classif_confidence float │
                                         │ extracted       json     │
                                         │ quality         json     │
                                         │ duplicate       json     │
                                         │ verification    json     │
                                         │ phash           varchar  │
                                         │ created_at      datetime │
                                         └──────────────────────────┘
```

## Tables

### `documents`
- **Identity / provenance:** `file_name`, `sha256` (indexed — exact-duplicate detection),
  `stored_path`, `mime_type`, `extension`, `file_size`, `page_count`.
- **OCR:** `ocr_provider`, `raw_text`, `ocr_confidence`, `language`.
- **Classification:** `doc_type` (indexed), `classification_confidence`.
- **AI output:** `extracted` (JSON) — all structured fields.
- **Verification:** `quality` (JSON), `duplicate` (JSON), `verification` (JSON: status,
  confidence, issues, recommended_actions).
- **Indexes:** `id`, `file_name`, `sha256`, `doc_type`.

### `submissions`
- Business grouping for one applicant. Aggregates the per-document verdicts into
  `completeness_score`, `overall_confidence`, `missing_documents`, `duplicate_documents`,
  `summary` (JSON) and stores the generated `report_data` / `report_path`.

## JSON columns vs normalisation

Extracted fields, quality metrics and verification verdicts are **schemaless JSON** for
two reasons:
1. Field sets differ per document type (a CNIC has no `skills`, a resume has no `cgpa`).
2. It maps cleanly onto a document-native store (MongoDB) — the "MongoDB adapter" bonus —
   while staying queryable in PostgreSQL via `jsonb`.

## Why a relational core?

Submissions → Documents is a hard 1:N relationship with referential integrity that the
reporting queries rely on. Using SQLAlchemy keeps the relational guarantees while the JSON
columns provide document-store flexibility.

## Schema evolution

Because the extracted/verification JSON is additive, migrations are trivial
(`CREATE TABLE IF NOT EXISTS` on startup; Alembic can be added for stricter governance).

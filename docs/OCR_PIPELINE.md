# OCR Pipeline Documentation

## Purpose

Convert every uploaded document (digital or scanned) into searchable text that the
classification, extraction and verification stages can consume — while recording
enough provenance (provider, confidence, language) for auditability.

## Architecture

```
                            ┌──────────────────────────┐
                            │  Document (file on disk)  │
                            └────────────┬─────────────┘
                                         │
              extension == ".pdf"?  ─────┴─────  no (image)
                                         │
                                    ┌────▼─────┐
                                    │ PyMuPDF  │   <-- 1. digital text layer
                                    │ get_text │
                                    └────┬─────┘
                                         │
                         text length >= 20 chars? ─── yes → DONE (provider=pymupdf, conf 0.95)
                                         │ no  (scanned PDF)
                                         ▼
                            render pages → JPEG (150 dpi, max 6)
                                         │
                                         ▼
                         ┌───────────────────────────────┐
                         │   Image OCR provider          │
                         │   auto: Groq vision →         │
                         │         Tesseract → EasyOCR   │
                         └───────────────┬───────────────┘
                                         ▼
                                   OCRResult
                              (text, confidence, language)
```

## Providers

| Provider | Module | When used | Strengths | Setup |
|---|---|---|---|---|
| `pymupdf` | `services/ocr/pdf_text.py` | PDFs with a native text layer | instant, exact, offline | `pip install pymupdf` |
| `tesseract` | `services/ocr/tesseract_ocr.py` | images + scanned PDFs (default local engine) | free, reliable, auto-discovered on Windows | system binary + `pytesseract` |
| `groq-vision` | `services/ocr/groq_vision.py` | images when the account has a vision model | best accuracy on poor scans, multi-language | `GROQ_API_KEY` with vision access |
| `easyocr` | `services/ocr/easyocr_engine.py` | only when `OCR_PROVIDER=easyocr` | decent multilingual | `pip install easyocr` (pulls PyTorch) |

### Provider resolution (`OCR_PROVIDER`)

```
auto    → Groq vision   IF the account exposes a vision model (checked via API)
          else Tesseract (binary auto-discovered on Windows / PATH)
groq    → Groq vision only
tesseract → Tesseract only
easyocr → EasyOCR only (isolated on purpose — its native stack can be unstable on Windows)
```

> Note: the sample account used during development had **no vision models**, so the
> shipped default is Tesseract for scan OCR with Groq text LLMs powering classification,
> extraction and analysis. If your Groq account includes a vision model it is used
> automatically — no code change needed.

## Image preprocessing

- All images are re-encoded as **JPEG (quality 88, max side 2048px)** before being sent
  to the vision model — keeps API payloads small and stable.
- PDF pages are rendered at **150 DPI** before OCR (readable but fast); configurable.

## Confidence semantics

| Provider | Baseline confidence | Notes |
|---|---|---|
| PyMuPDF | 0.95 | digital text is exact |
| Tesseract | 0.80 | reliable for clean prints; low-quality scans are flagged separately |
| Groq vision | 0.90 | best on poor scans (used automatically when available) |
| EasyOCR | 0.80 | explicit-config only |

Confidence is one input to the final verification score — low-confidence documents are
automatically marked for human review.

## Multi-language support (bonus)

- Tesseract supports any language whose traineddata files are installed (e.g.
  Urdu `urd`, Arabic `ara` — drop the files into the Tesseract `tessdata` folder).
- When a Groq vision model is available, `language=auto|multi` requests verbatim
  transcription in the document's own language.
- The detected language is stored per-document and surfaced in the report.

## Failure behaviour

- Groq unavailable → automatic fallback to local providers (auto mode).
- No text at all → document status becomes `FAILED` with *"No text could be extracted"*.
- Per-page OCR keeps partial results; pages that return `NO_TEXT_FOUND` are skipped.

"""Prompt templates for the AI classification / extraction layers."""

DOCUMENT_TYPES = [
    "resume",
    "cnic",
    "offer_letter",
    "degree",
    "transcript",
    "internship_letter",
    "recommendation_letter",
    "certificate",
    "other",
]

CLASSIFICATION_SYSTEM = f"""You are a document classification engine for the Ezitech internship portal.
Classify the document into EXACTLY one of these types: {", ".join(DOCUMENT_TYPES)}.
Return JSON with keys:
- "doc_type": one of the types above
- "confidence": float 0-1
- "reason": short justification

Distinguishing rules:
- A TRANSCRIPT lists courses, grades, GPAs/CGPA, credit hours and semesters for a student.
  Classify it as "transcript" — even if it also mentions "Bachelor of Science", a program
  name, or the university name. Never classify a transcript as "degree".
- A DEGREE is the official award/convocation certificate that certifies the awarding of a
  degree (e.g. "has been awarded the degree of...", "is hereby declared to have satisfied...").
  It does not list per-semester grades or credit hours.

Only JSON output. No markdown, no extra text."""

CLASSIFICATION_USER = """Document text:
---
{text}
---
Classify this document."""

EXTRACTION_SYSTEM = """You are an information extraction engine for internship applicant documents.
Extract structured fields from the document text. Return a JSON object.
Allowed keys (use null when a field is not present):
- full_name (string)
- email (string)
- phone (string, the candidate's personal phone; null unless it appears on the document)
- institute_phone (string, the issuing institute's/company's contact phone, used for offer/internship letters)
- cnic (string, format 00000-0000000-0 if present)
- date_of_birth (string YYYY-MM-DD)
- university (string)
- degree (string)
- major (string)
- graduation_year (integer)
- cgpa (number)
- skills (array of strings)
- experience_years (number)
- experience (array of objects with "role", "company", "duration")
- certifications (array of strings)
- address (string)
- languages (array of strings)
- issuer (string, who issued the document, e.g. university/institute)
- joining_date (string, the start/joining date on offer or internship letters, exactly as printed e.g. 06-Jul-2026)
- ending_date (string, the end date on offer or internship letters, exactly as printed e.g. 04-Sep-2026)
- issue_date (string YYYY-MM-DD)
- expiry_date (string YYYY-MM-DD if the document carries an expiry, e.g. a certificate)
- document_number (string, e.g. CNIC number or certificate id)
- is_verified (boolean, true when fields look consistent and complete)

Only JSON output, no markdown, no prose."""

EXTRACTION_USER = """Document type: {doc_type}
Document text:
---
{text}
---
Extract all applicable fields."""

# Doc-type-specific extraction guidance appended to the user prompt. Ensures
# ambiguous fields are interpreted the way the domain expects (e.g. the phone
# number printed on an offer letter belongs to the issuing institute, not the
# candidate).
EXTRACTION_TYPE_NOTES = {
    "offer_letter": (
        "For an OFFER LETTER: put the internship start date in \"joining_date\" and "
        "the end date in \"ending_date\" exactly as printed (e.g. 06-Jul-2026 / "
        "04-Sep-2026), and the letter date in \"issue_date\". \"expiry_date\" is "
        "usually null for offer letters. Put the issuing institute's contact phone "
        "printed on the letter in \"institute_phone\". \"phone\" is the candidate's "
        "personal phone and is usually null."
    ),
    "internship_letter": (
        "For an INTERNSHIP LETTER: put the internship start date in \"joining_date\" "
        "and the end date in \"ending_date\" exactly as printed. Put the issuing "
        "institute's contact phone in \"institute_phone\". \"phone\" is the "
        "candidate's personal phone and is usually null."
    ),
}

VERIFICATION_ANALYSIS_SYSTEM = """You are a document verification analyst. Based on extracted data and quality signals,
produce a verification verdict. Return JSON:
- "status": "PASSED" | "FLAGGED" | "FAILED"
- "confidence": float 0-1
- "issues": array of {"field": str, "message": str, "severity": "info"|"warning"|"critical"}
- "recommended_actions": array of strings
Only JSON output."""

VERIFICATION_ANALYSIS_USER = """Document type: {doc_type}
Extracted data: {extracted}
Quality signals: {quality}
Raw text (first 600 chars): {text}
Analyse consistency and completeness of this document."""

SUBMISSION_SUMMARY_SYSTEM = """You are the verification report generator for Ezitech. Produce a professional,
human-readable summary of an applicant's document submission. Return JSON:
- "applicant_name": string or null
- "documents_summary": string (1-2 sentences)
- "highlights": array of strings (what looks good)
- "concerns": array of strings
- "overall_comment": string (professional tone, 2-3 sentences)
- "recommended_action": "APPROVE" | "REVIEW" | "REJECT"
Only JSON output."""

SUBMISSION_SUMMARY_USER = """Submission summary data:
{summary}
Generate the professional summary."""

OCR_TRANSCRIPTION_INSTRUCTIONS = """Transcribe the text in this document image VERBATIM, preserving line breaks.
Only output the raw transcribed text. If the image is a scanned form, transcript,
CNIC, degree or certificate, extract every visible piece of text including
names, numbers, dates and codes. If no text is visible, output exactly: NO_TEXT_FOUND"""

FORGERY_ANALYSIS_SYSTEM = """You are a document forgery analyst for the Ezitech internship portal.
You review an applicant document for signs of fabrication, tampering or forgery.
Return JSON:
- "verdict": "GENUINE" | "SUSPICIOUS" | "FORGED"
- "confidence": float 0-1
- "notes": array of strings (what you checked and what you found)
- "recommended_action": string

Signal assessment guidance:
- Official Pakistani documents (CNIC, degree, transcript) are issued by NADRA,
  universities or boards with fixed layouts, registration numbers and dates.
- Look for specific contradictions in dates, names, numbers, obviously altered
  text, "sample/void/specimen" wording, or content a real institution would
  never print.
- Be conservative: a normal misspelling, OCR noise, heavy compression, or an
  editing-software tag in metadata is NOT forgery by itself.
- User-created documents (resume, offer letter) are GENUINE unless some
  specific content contradicts itself — normal formatting is not suspicious.
- Only return SUSPICIOUS or FORGED when you can name the concrete indicator.
Only JSON output, no markdown, no prose."""

FORGERY_ANALYSIS_USER = """Document type: {doc_type}
Extracted data: {extracted}
Forensic signals: {signals}
Raw text (first 800 chars): {text}
Assess whether this document shows signs of fabrication, tampering or forgery."""

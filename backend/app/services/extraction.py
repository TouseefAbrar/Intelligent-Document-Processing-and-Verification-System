"""Structured information extraction.

Primary path: Groq LLM with JSON-mode constraints for rich, accurate field
extraction. Fallback: deterministic regex/rule extraction that guarantees
useful output for the core fields even without AI access.
"""
from __future__ import annotations

import re

from app.core.logging import get_logger
from app.services.ai.groq_client import groq_client
from app.services.ai.prompts import EXTRACTION_SYSTEM, EXTRACTION_TYPE_NOTES, EXTRACTION_USER

logger = get_logger("services.extraction")

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _format_printed_date(value) -> str:
    """Return a joining/ending date in the DD-Mon-YYYY form used on offer letters."""
    if not isinstance(value, str):
        return value
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", value.strip())
    if m:
        try:
            return f"{int(m.group(3)):02d}-{_MONTHS[int(m.group(2)) - 1]}-{m.group(1)}"
        except (ValueError, IndexError):
            return value.strip()
    return value.strip()

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?92|0)?[3-9][0-9]{2}[\s\-]?[0-9]{7}|\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}")
CNIC_RE = re.compile(r"\b\d{5}[- ]?\d{7}[- ]?\d\b")
YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-3]\d)\b")
CGPA_RE = re.compile(r"\b([0-4](?:\.\d{1,2})?)\s*/\s*4(?:\s*\.0*)?\b|\bCGPA[:\s]*([0-4](?:\.\d{1,2})?)\b", re.IGNORECASE)
DATE_TRIPLET_RE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b")

# --- Full name ---------------------------------------------------------------
# "Name:" / "Applicant:" / "Full Name:" ... (allows ALL-CAPS names and the
# label being separated from the value by a newline, as OCR'd CNICs are).
_NAME_LABEL_RE = re.compile(
    r"\b(?:full\s+name|student\s+name|applicant'?s?\s+name|candidate'?s?\s+name|name|applicant|candidate)"
    r"\s*[:\-|]?\s*([A-Z][A-Za-z]{2,}(?:[ \t]+[A-Z][A-Za-z]{2,}){0,3})",
    re.IGNORECASE,
)
# "Dear Touseef Abrar," — the salutation used on offer/internship letters.
_DEAR_RE = re.compile(
    r"\bDear\s+([A-Z][A-Za-z]{2,}(?:\s+[A-Z][A-Za-z]{2,}){0,3})[,\s]"
)
_DEAR_SKIP = {"Sir", "Madam", "Mam", "Ma'am", "HR", "Team", "Manager", "Recruiter", "Concerned"}

# Leading-name heuristic for resumes: the first meaningful line is the name.
_HEADER_LINE_RE = re.compile(
    r"^(?:curriculum vitae|cv|resume|offer letter|internship offer|internship letter|transcript|"
    r"official transcript|degree|degree certificate|certificate|national identity card|identity card|"
    r"id card|bachelor|master|grade ?sheet|mark ?sheet|application|profile|summary|to whom it may concern)$",
    re.IGNORECASE,
)

# --- Document numbers ---------------------------------------------------------
_DOC_NUMBER_RE = re.compile(
    r"\b(?:registration no\.?|reg(?:istration)?\.?|roll no\.?|seat no\.?|document no\.?|"
    r"doc(?:ument)? no\.?|cert(?:ificate)? no\.?|intern[- ]?id|id no\.?|student id|"
    r"enroll(?:ment|ment)? no\.?|admission no\.?|ref no\.?|reference no\.?|license no\.?|"
    r"passport no\.?|nic no\.?|cnic no\.?)\s*[:\-]?\s*([A-Z0-9][A-Za-z0-9/\-]{4,30})\b",
    re.IGNORECASE,
)

# --- Offer letter specifics ---------------------------------------------------
_COMPANY_RE = re.compile(
    r"\b(?:company|organization|organisation|firm)\s*[:\-]?\s*([A-Z][A-Za-z0-9 .&'\-,]{2,50})",
    re.IGNORECASE,
)
# "position of Machine Learning Intern" — the position stops at a joining word
# ("at / with / in / for / the / from") or at punctuation/end of line.
_POSITION_RE = re.compile(
    r"\b(?:position|job title|role|designation)\s*[:\-]?\s*(?:of\s+)?([A-Z][A-Za-z&./\- ]+?)"
    r"(?=\s+(?:at|with|in|for|the|from)\b|[,.)]|$)",
    re.IGNORECASE,
)
_JOINING_RE = re.compile(
    r"\b(?:joining date|start date|expected joining|commencement date|reporting date)\s*[:\-]?\s*"
    r"([\d]{1,2}[-\s/][A-Za-z]{3,}[-\s/]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,},\s+\d{4}|\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
_ENDING_RE = re.compile(
    r"\b(?:ending date|end date|end of internship|internship end|valid until)\s*[:\-]?\s*"
    r"([\d]{1,2}[-\s/][A-Za-z]{3,}[-\s/]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,},\s+\d{4}|\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)

# --- CNIC specifics ------------------------------------------------------------
_FATHER_LABEL_RE = re.compile(r"\bfather\s*'?s?\s*name", re.IGNORECASE)
_GENDER_RE = re.compile(r"\bgender\s*[:\-|]?\s*([MFmf])\b")
# Date labels and values are only linked when they share a line. On scanned
# cards ("Date of Issue | Date of Expiry" then "23.01.2023 23.01.2033" on the
# next line) the positional fallback below is used instead.
_DOB_LABEL_RE = re.compile(
    r"\b(?:date of birth|dob)\b[ \t]*[:\-|]?[ \t]*(\d{1,2})[./-](\d{1,2})[./-](\d{4})", re.IGNORECASE
)
_ISSUE_LABEL_RE = re.compile(
    r"\bdate of issue\b[ \t]*[:\-|]?[ \t]*(\d{1,2})[./-](\d{1,2})[./-](\d{4})", re.IGNORECASE
)
_EXPIRY_LABEL_RE = re.compile(
    r"\bdate of expiry\b[ \t]*[:\-|]?[ \t]*(\d{1,2})[./-](\d{1,2})[./-](\d{4})", re.IGNORECASE
)


def _iso_date(d: str, m: str, y: str) -> str | None:
    try:
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    except (TypeError, ValueError):
        return None


def _clean_name(value: str) -> str:
    name = value.strip().rstrip(".,;:")
    # "TOUSEEF ABRAR" / "ANAS KHAN" → "Touseef Abrar" / "Anas Khan".
    if name and name.isupper():
        return name.title()
    return name


def _extract_name(text: str) -> str | None:
    m = _NAME_LABEL_RE.search(text)
    if m:
        return _clean_name(m.group(1))
    m = _DEAR_RE.search(text)
    if m and m.group(1) not in _DEAR_SKIP:
        return _clean_name(m.group(1))
    # Last resort: the first meaningful line (used for resumes whose name is
    # printed as the first line with no label).
    for raw_line in text.splitlines():
        line = raw_line.strip().rstrip(".,;:()\"'*")
        if not line:
            continue
        if _HEADER_LINE_RE.fullmatch(line.strip()):
            continue
        if re.search(r"[:@#]|\d|https?|www\.|[/\\]", line):
            return None
        words = line.split()
        if 2 <= len(words) <= 4 and all(re.fullmatch(r"[A-Z][a-zA-Z.'-]{1,}", w) for w in words):
            return _clean_name(line)
        return None
    return None


def _extract_cnic_fields(text: str, extracted: dict) -> None:
    """CNIC-specific fields: father name, gender, DOB, issue/expiry dates."""
    m = _FATHER_LABEL_RE.search(text)
    if m:
        for line in text[m.end() :].splitlines()[:4]:
            name_m = re.search(r"([A-Z][A-Za-z]{2,}(?:\s+[A-Z][A-Za-z]{2,})+)\s*$", line.strip())
            if name_m:
                extracted["father_name"] = name_m.group(1).strip()
                break
    m = _GENDER_RE.search(text)
    if m:
        extracted["gender"] = m.group(1).upper()

    dates = [_iso_date(*d) for d in DATE_TRIPLET_RE.findall(text)]
    used: set[str] = set()

    m = _DOB_LABEL_RE.search(text)
    if m:
        extracted["date_of_birth"] = _iso_date(*m.groups())
        if extracted["date_of_birth"]:
            used.add(extracted["date_of_birth"])
    m = _ISSUE_LABEL_RE.search(text)
    if m:
        extracted["issue_date"] = _iso_date(*m.groups())
        if extracted["issue_date"]:
            used.add(extracted["issue_date"])
    m = _EXPIRY_LABEL_RE.search(text)
    if m:
        extracted["expiry_date"] = _iso_date(*m.groups())
        if extracted["expiry_date"]:
            used.add(extracted["expiry_date"])

    # Positional fallback for scanned cards whose labels and values live on
    # separate lines: NADRA cards print DOB, then issue, then expiry.
    remaining = [d for d in dates if d and d not in used]
    if "date_of_birth" not in extracted and remaining:
        extracted["date_of_birth"] = remaining.pop(0)
    if "issue_date" not in extracted and remaining:
        extracted["issue_date"] = remaining.pop(0)
    if "expiry_date" not in extracted and remaining:
        extracted["expiry_date"] = remaining.pop(0)

    if extracted.get("cnic") and extracted.get("full_name"):
        extracted["is_verified"] = True


def regex_extract(text: str, doc_type: str) -> dict:
    extracted: dict = {}

    email = EMAIL_RE.findall(text)
    if email:
        extracted["email"] = email[0].lower()

    # Generic phone extraction is skipped for CNICs and transcripts: on those
    # documents the digits belong to the card/document number, not a phone.
    if doc_type not in ("cnic", "transcript"):
        phone = PHONE_RE.findall(text)
        if phone:
            extracted["phone"] = phone[0].strip().replace(" ", "")

    cnic = CNIC_RE.findall(text)
    if cnic:
        extracted["cnic"] = cnic[0].replace(" ", "")

    if doc_type in ("resume", "degree"):
        years = [int(y) for y in YEAR_RE.findall(text)]
        if years:
            extracted["graduation_year"] = max(years)

    cgpa = CGPA_RE.findall(text)
    if cgpa:
        val = next((m[0] or m[1] for m in cgpa if m[0] or m[1]), None)
        if val:
            extracted["cgpa"] = float(val)

    name = _extract_name(text)
    if name:
        extracted["full_name"] = name

    skills = [s for s in SKILL_KEYWORDS if re.search(rf"\b{re.escape(s)}\b", text.lower())]
    if skills:
        extracted["skills"] = skills

    doc_no = _DOC_NUMBER_RE.search(text)
    if doc_no and doc_no.group(1) != extracted.get("cnic"):
        extracted["document_number"] = doc_no.group(1).strip().rstrip(".,;:")

    if doc_type == "transcript":
        uni = re.search(r"(?:university|institute|college)\s*(?:of\s*)?([A-Z][A-Za-z .&'-]+)", text)
        if uni:
            extracted["university"] = uni.group(1).strip()
        # Transcripts are usually not independently "verified" — flag for review.
        extracted["is_verified"] = False
    if doc_type == "degree":
        deg = re.search(r"\b(B\.?(Sc|A|E|S)\b|Bachelor(?:'s)?\s+of\s+[A-Za-z ]+|Master(?:'s)?\s+of\s+[A-Za-z ]+|MS\b|M\.?Sc\b|MBA\b|PhD\b)", text)
        if deg:
            extracted["degree"] = deg.group(0).strip()
    if doc_type == "offer_letter":
        position = _POSITION_RE.search(text)
        if position:
            extracted["position"] = position.group(1).strip().rstrip(".,;")
        company = _COMPANY_RE.search(text)
        if company:
            extracted["issuer"] = company.group(1).strip().rstrip(".,;")
        if "issuer" not in extracted:
            m = re.search(
                r"\b(?:from|at)\s+(?:M/S\s+)?([A-Z][A-Za-z0-9&.'-]+(?:\s+[A-Z][A-Za-z0-9&.'-]+)?)\s*[.,\s]",
                text, re.IGNORECASE,
            )
            if m and re.search(
                r"(institute|university|college|technolog|software|solutions|pvt|privat|corp|inc\.?|ltd\.?)",
                m.group(1), re.IGNORECASE,
            ):
                extracted["issuer"] = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(".,;")
        start = _JOINING_RE.search(text)
        if start:
            extracted["joining_date"] = start.group(1).strip()
        ending = _ENDING_RE.search(text)
        if ending:
            extracted["ending_date"] = ending.group(1).strip()
    if doc_type == "cnic":
        _extract_cnic_fields(text, extracted)

    # On offer/internship letters the phone printed on the document belongs to
    # the issuing institute, so expose it as institute_phone (not the candidate's).
    return _finalize_extraction(extracted, doc_type)


def _finalize_extraction(data: dict, doc_type: str) -> dict:
    """Normalize the extracted dict for a document type.

    On offer/internship letters the phone printed on the document belongs to the
    issuing institute, so it is exposed as ``institute_phone``. Their start/end
    dates are exposed as ``joining_date``/``ending_date`` (the labels printed on
    the letter), and these fields are placed right after ``full_name`` because
    reports render fields in dict order, truncated early.
    """
    data.setdefault("is_verified", None)
    if doc_type in ("offer_letter", "internship_letter"):
        if "phone" in data and "institute_phone" not in data:
            data["institute_phone"] = data.pop("phone")
        if "start_date" in data and "joining_date" not in data:
            data["joining_date"] = data.pop("start_date")
        if "expiry_date" in data and "ending_date" not in data:
            data["ending_date"] = data.pop("expiry_date")
        if "joining_date" in data:
            data["joining_date"] = _format_printed_date(data["joining_date"])
        if "ending_date" in data:
            data["ending_date"] = _format_printed_date(data["ending_date"])
        priority = ("full_name", "institute_phone", "joining_date", "ending_date")
        ordered = {key: data.pop(key) for key in priority if key in data}
        ordered.update(data)
        data = ordered
    return data


SKILL_KEYWORDS = [
    "python", "java", "c++", "javascript", "typescript", "react", "node", "django",
    "fastapi", "flask", "sql", "mongodb", "postgres", "mysql", "docker", "kubernetes",
    "git", "linux", "machine learning", "deep learning", "nlp", "tensorflow", "pytorch",
    "pandas", "numpy", "opencv", "flutter", "html", "css", "tailwind", "aws", "azure",
    "firebase", "communication", "leadership", "teamwork", "problem solving", "analytics",
]


async def extract(text: str, doc_type: str) -> dict:
    if not text or len(text.strip()) < 10:
        return {"is_verified": False}

    user_prompt = EXTRACTION_USER.format(doc_type=doc_type, text=text[:8000])
    notes = EXTRACTION_TYPE_NOTES.get(doc_type)
    if notes:
        user_prompt += f"\n\nSpecific guidance for {doc_type} documents:\n{notes}"

    if groq_client.available:
        try:
            resp = await groq_client.complete_json(
                EXTRACTION_SYSTEM,
                user_prompt,
                max_tokens=1500,
            )
            parsed = groq_client.parse_json(resp["content"])
            parsed = {k: v for k, v in parsed.items() if v is not None and v != ""}
            # Guarantee regex fields even if LLM missed them.
            fallback = regex_extract(text, doc_type)
            for k, v in fallback.items():
                parsed.setdefault(k, v)
            return _finalize_extraction(parsed, doc_type)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM extraction failed, using regex: %s", exc)

    return regex_extract(text, doc_type)

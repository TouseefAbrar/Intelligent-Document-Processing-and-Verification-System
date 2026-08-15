"""Document classification service.

Primary path uses a Groq LLM (JSON mode) for robust semantic classification.
A keyword/rule scorer guarantees a result even when no AI backend is wired.
"""
from __future__ import annotations

import re

from app.core.logging import get_logger
from app.services.ai.groq_client import groq_client
from app.services.ai.prompts import CLASSIFICATION_SYSTEM, CLASSIFICATION_USER
from app.services.coverage import normalize_doc_type

logger = get_logger("services.classification")

_KEYWORD_RULES: list[tuple[str, set[str]]] = [
    ("cnic", {"national identity card", "identity card", "cnic no", "cnic number", "national id card"}),
    ("offer_letter", {"offer letter", "letter of offer", "job offer", "employment offer", "we are pleased to offer you", "we are delighted to offer", "joiner", "joining date", "annual ctc", "salary package", "compensation package", "position of"}),
    ("transcript", {"transcript", "semester gpa", "gpa:", "cgpa:", "grade point average", "official transcript", "credit hours", "grade sheet", "gradesheet", "mark sheet", "marksheet", "marks obtained", "result card"}),
    ("degree", {"degree", "bachelor", "b.s.", "b.sc", "bs ", "masters", "master of", "msc", "ms ", "university degree", "convocation", "awarded the degree", "degree certificate", "graduation certificate"}),
    ("resume", {"curriculum vitae", "cv", "resume", "professional summary", "work experience", "objective", "skills", "references"}),
    ("internship_letter", {"internship offer", "internship letter", "intern at", "training offer", "internship program", "we are pleased to offer", "intern"}),
    ("recommendation_letter", {"recommendation", "letter of recommendation", "to whom it may concern", "i recommend", "strongly recommend", "academic reference"}),
    ("certificate", {"certificate", "certifies that", "this is to certify", "successfully completed", "awarded", "participation certificate", "appreciation"}),
]

_UNI_RE = re.compile(r"(university|institute|college|campus)\b", re.IGNORECASE)

# Markers that are unique to academic transcripts (grades, GPAs, credit hours,
# semesters). A degree certificate carries none of these — but transcripts very
# often carry the degree rule's keywords ("Bachelor of Science", university name).
_TRANSCRIPT_MARKERS = (
    "transcript",
    "transcript of records",
    "official transcript",
    "grade sheet",
    "gradesheet",
    "mark sheet",
    "marksheet",
    "marks obtained",
    "grade point average",
    "credit hour",
    "semester",
    "cgpa",
    "gpa",
    "result card",
)

# Degree keywords that also appear on transcripts (program being studied) and
# must NOT count against a transcript once grade/GPA markers are present.
_DEGREE_ON_TRANSCRIPT_RE = re.compile(
    r"\b(bachelor|master|b\.?\s?sc\b|b\.?s\.?\b|m\.?\s?sc\b|m\.?s\.?\b|b\.?a\.?\b|m\.?a\.?\b)\b",
    re.IGNORECASE,
)


def keyword_classify(text: str) -> dict:
    text_l = text.lower()
    scores = {doc_type: 0 for doc_type, _ in _KEYWORD_RULES}
    for doc_type, keywords in _KEYWORD_RULES:
        for kw in keywords:
            if kw in text_l:
                scores[doc_type] += 1

    # Transcripts list courses, grades, GPAs, credit hours and semesters; degree
    # certificates do not. When those markers are present the document is a
    # transcript, even when it also names the degree and the university (the
    # exact keywords the degree rule keys on) — this stops transcripts being
    # mislabelled as degrees.
    transcript_hits = sum(1 for kw in _TRANSCRIPT_MARKERS if kw in text_l)
    if transcript_hits:
        scores["transcript"] += transcript_hits * 3
        if _UNI_RE.search(text_l):
            scores["degree"] -= 0.5  # neutralize the university boost below
        if _DEGREE_ON_TRANSCRIPT_RE.search(text_l):
            scores["degree"] -= 1  # "Bachelor of..." = program, not an award
    elif _UNI_RE.search(text_l):
        scores["degree"] += 0.5

    total = sum(max(v, 0.0) for v in scores.values()) or 1.0
    best, best_score = max(scores.items(), key=lambda kv: kv[1])
    if best_score <= 0:
        return {"doc_type": "other", "confidence": 0.1, "reason": "No strong keyword match"}
    return {
        "doc_type": best,
        "confidence": round(min(0.95, best_score / total + 0.25), 3),
        "reason": f"Keyword scoring ({best_score} hits)",
    }


async def classify(text: str) -> dict:
    if not text or len(text.strip()) < 10:
        return {"doc_type": "other", "confidence": 0.05, "reason": "No OCR text available"}

    if groq_client.available:
        try:
            resp = await groq_client.complete_json(
                CLASSIFICATION_SYSTEM, CLASSIFICATION_USER.format(text=text[:6000]), max_tokens=200
            )
            parsed = groq_client.parse_json(resp["content"])
            doc_type = normalize_doc_type(parsed.get("doc_type"))
            valid = {"resume", "cnic", "offer_letter", "degree", "transcript", "internship_letter",
                     "recommendation_letter", "certificate", "other"}
            if doc_type not in valid:
                doc_type = "other"
            return {
                "doc_type": doc_type,
                "confidence": round(float(parsed.get("confidence", 0.7)), 3),
                "reason": str(parsed.get("reason", "LLM classification")),
                "model": resp.get("model"),
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM classification failed, falling back to rules: %s", exc)

    return keyword_classify(text)

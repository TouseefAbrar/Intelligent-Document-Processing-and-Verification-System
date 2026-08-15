"""Duplicate-upload detection.

Two complementary layers:
  * exact SHA-256 match — the same bytes uploaded again (works for PDFs and
    images, catches "same document twice under a different filename")
  * perceptual dHash comparison — visually identical images that were
    re-saved/re-encoded (Hamming distance on 16x16 dHash fingerprints)

Duplicate checks are scoped to the current submission batch, which is the
real "the user uploaded the same document twice" case. Exact SHA-256 matches
are also checked across other documents in the batch regardless of type.
"""
from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.core.logging import get_logger

logger = get_logger("services.duplicates")

try:
    import imagehash
    from PIL import Image
except ImportError:  # pragma: no cover
    imagehash = None


def compute_phash(path: Path) -> str:
    """Return a perceptual hash hex string, or '' when unavailable."""
    if imagehash is None:
        return ""
    try:
        return str(imagehash.dhash(Image.open(path).convert("RGB"), hash_size=16))
    except Exception as exc:  # noqa: BLE001
        logger.warning("pHash failed for %s: %s", path, exc)
        return ""


def hamming(a: str, b: str) -> float:
    """Normalised Hamming distance 0..1 (0 = identical)."""
    if not a or not b:
        return 0.0
    if len(a) != len(b):
        return 1.0
    diff = sum(x != y for x, y in zip(a, b))
    return diff / len(a)


def similarity(a: str, b: str) -> float:
    """Similarity 0..1 where 1 = identical image."""
    return 1.0 - hamming(a, b)


def is_duplicate(candidate_hash: str, existing_hashes: list[str]) -> dict:
    best = (0.0, "")
    for other in existing_hashes:
        sim = similarity(candidate_hash, other)
        if sim > best[0]:
            best = (sim, other)
    sim, other_hash = best
    return {
        "is_duplicate": bool(sim) and sim >= settings.DUPLICATE_HASH_THRESHOLD,
        "similarity": round(sim, 4),
        "matched_hash": other_hash,
        "method": "dhash",
        "matched_file": "",
    }


def detect_duplicate(db, doc) -> dict:
    """Detect whether ``doc`` duplicates another document in the same batch.

    Returns a dict mirroring the legacy shape plus richer details:

        {is_duplicate, similarity, method, matched_hash, matched_file, reason}
    """
    result = {
        "is_duplicate": False,
        "similarity": 0.0,
        "method": "sha256",
        "matched_hash": "",
        "matched_file": "",
        "reason": "",
    }

    batch_id = getattr(doc, "submission_id", None)

    # 1) Exact byte-level duplicate (SHA-256). Works for every file type.
    #    Only documents that have already finished the pipeline can count as
    #    matches: every upload in a batch is inserted before processing starts,
    #    so an unprocessed sibling is not yet a "previous upload".
    processed = {"PROCESSING", "PENDING"}
    if batch_id is not None:
        others = (
            db.query(type(doc))
            .filter(type(doc).submission_id == batch_id, type(doc).id != doc.id)
            .all()
        )
    else:
        others = []
    others = [
        o for o in others
        if (o.verification or {}).get("status", "PROCESSING") not in processed
    ]
    for other in others:
        if getattr(other, "sha256", "") and other.sha256 == doc.sha256:
            return {
                **result,
                "is_duplicate": True,
                "similarity": 1.0,
                "method": "sha256",
                "matched_hash": other.sha256,
                "matched_file": other.file_name,
                "reason": "Identical file content (SHA-256) already uploaded in this batch",
            }

    # 2) Perceptual hash for images (covers re-encoded / renamed copies).
    path = Path(doc.stored_path)
    ext = getattr(doc, "extension", "")
    if ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"} and path.exists():
        doc.phash = compute_phash(path)
        existing_hashes = [(getattr(d, "phash", ""), getattr(d, "file_name", "")) for d in others]
        existing_hashes = [(h, n) for h, n in existing_hashes if h]
        if existing_hashes and doc.phash:
            best_sim, best_hash, best_file = 0.0, "", ""
            for other_hash, other_file in existing_hashes:
                sim = similarity(doc.phash, other_hash)
                if sim > best_sim:
                    best_sim, best_hash, best_file = sim, other_hash, other_file
            result["similarity"] = round(best_sim, 4)
            if best_sim >= settings.DUPLICATE_HASH_THRESHOLD:
                return {
                    **result,
                    "is_duplicate": True,
                    "method": "dhash",
                    "matched_hash": best_hash,
                    "matched_file": best_file,
                    "reason": f"Visually identical to already-uploaded document (dHash similarity {best_sim:.0%})",
                }

    result["method"] = "dhash" if ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"} else "sha256"
    return result

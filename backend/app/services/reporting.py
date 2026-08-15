"""Professional verification report generation (HTML / JSON / PDF)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.core.logging import get_logger
from app.services.extraction import _finalize_extraction

logger = get_logger("services.reporting")

DOC_TYPE_LABELS = {
    "resume": "Resume",
    "cnic": "CNIC",
    "offer_letter": "Offer Letter",
    "degree": "Degree",
    "transcript": "Transcript",
    "internship_letter": "Internship Letter",
    "recommendation_letter": "Recommendation Letter",
    "certificate": "Certificate",
    "other": "Other",
}


def _severity_badge(severity: str) -> str:
    colors = {"critical": "#e5484d", "warning": "#f5a524", "info": "#3b82f6"}
    return f'<span class="badge" style="background:{colors.get(severity, "#6b7280")}22;color:{colors.get(severity, "#6b7280")};border-color:{colors.get(severity, "#6b7280")}"> {severity.upper()} </span>'


def _status_badge(status: str) -> str:
    colors = {
        "PASSED": "#12a150",
        "FLAGGED": "#f5a524",
        "FAILED": "#e5484d",
        "PROCESSING": "#6b7280",
        "MISSING": "#e5484d",
        "INVALID FILE TYPE": "#e5484d",
        "DUPLICATE": "#f5a524",
        "BLURRY": "#f5a524",
        "WRONG DOCUMENT TYPE": "#e5484d",
        "INCONSISTENCY DETECTED": "#e5484d",
        "FORGERY DETECTED": "#7f1d1d",
    }
    c = colors.get(status, "#6b7280")
    return f'<span class="badge" style="background:{c}22;color:{c};border-color:{c}">{status}</span>'


def build_report_json(submission) -> dict:
    type_by_file = {getattr(d, "file_name", ""): d.doc_type for d in submission.documents}
    docs = []
    for d in submission.documents:
        dup = d.duplicate or {}
        label = DOC_TYPE_LABELS.get(d.doc_type, d.doc_type.title())
        if dup.get("is_duplicate"):
            matched_type = type_by_file.get(dup.get("matched_file", ""), "")
            base = DOC_TYPE_LABELS.get(matched_type, matched_type.title() or d.doc_type.title())
            label = f"{base} (duplicate)"
        extracted = d.extracted or {}
        if d.doc_type in ("offer_letter", "internship_letter"):
            extracted = _finalize_extraction(dict(extracted), d.doc_type)
        docs.append(
            {
                "id": d.id,
                "file_name": d.file_name,
                "doc_type": d.doc_type,
                "expected_doc_type": getattr(d, "expected_doc_type", "") or "",
                "doc_type_label": label,
                "classification_confidence": d.classification_confidence,
                "ocr_confidence": d.ocr_confidence,
                "ocr_provider": d.ocr_provider,
                "language": d.language,
                "status": d.verification.get("status"),
                "extracted": extracted,
                "issues": d.verification.get("issues", []),
                "recommended_actions": d.verification.get("recommended_actions", []),
                "quality": d.quality,
                "duplicate": d.duplicate,
                "forgery": d.forgery or {},
            }
        )
    return {
        "report_id": f"EEF-{submission.id:05d}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "submission_id": submission.id,
        "applicant_ref": submission.applicant_ref,
        "status": submission.status,
        "completeness_score": submission.completeness_score,
        "overall_confidence": submission.overall_confidence,
        "missing_documents": submission.missing_documents,
        "duplicate_documents": submission.duplicate_documents,
        "summary": submission.summary,
        "documents": docs,
    }


def _forgery_panel(forgery: dict) -> str:
    """Render a forensic / forgery-analysis panel (empty when nothing suspicious)."""
    level = (forgery or {}).get("level", "GREEN")
    if level not in ("YELLOW", "RED"):
        return ""
    color = "#f5a524" if level == "YELLOW" else "#e5484d"
    signals = (forgery.get("signals") or [])
    rows = "".join(
        f"<li><b>{s.get('label', s.get('name', 'Signal'))}</b> "
        f"[{s.get('result', 'clear').upper()}] — {s.get('detail', '')}</li>"
        for s in signals if s.get("result") != "clear"
    ) or "<li>No individual signal detailed</li>"
    llm = forgery.get("llm") or {}
    llm_html = ""
    if llm:
        llm_html = (
            f"<p style='margin:6px 0 0;font-size:12px;'>"
            f"LLM verdict: <b>{llm.get('verdict', '')}</b> "
            f"({(llm.get('confidence') or 0) * 100:.0f}% confidence)</p>"
        )
    return (
        f'<div style="margin:10px 0;padding:10px 12px;border-radius:8px;'
        f'background:{color}14;border:1px solid {color}55;font-size:13px;">'
        f'&#128272; <b>Forgery / tampering analysis — {level}</b> '
        f'(score {(forgery.get("score") or 0) * 100:.0f}%, confidence '
        f'{(forgery.get("confidence") or 0) * 100:.0f}%)'
        f'<ul style="margin:6px 0 0 16px;">{rows}</ul>{llm_html}</div>'
    )


def _render_document_rows(report: dict) -> str:
    rows = []
    for doc in report["documents"]:
        issues_html = "".join(
            f"<li>{_severity_badge(i['severity'])} {i['message']}</li>" for i in doc["issues"]
        ) or "<li style='color:#12a150'>No issues detected</li>"
        extracted = doc["extracted"] or {}
        fields = "".join(
            f"<tr><td>{k.replace('_', ' ').title()}</td><td>{_fmt_value(v)}</td></tr>"
            for k, v in extracted.items()
        ) or "<tr><td colspan=2>No fields extracted</td></tr>"
        dup = doc.get("duplicate") or {}
        dup_html = ""
        if dup.get("is_duplicate"):
            dup_html = (
                f'<div style="margin:10px 0;padding:10px 12px;border-radius:8px;'
                f'background:rgba(245,165,36,0.12);border:1px solid rgba(245,165,36,0.3);font-size:13px;">'
                f'&#9888; Duplicate of <b>{dup.get("matched_file") or "another document in this batch"}</b>'
                f' &middot; {dup.get("similarity", 0) * 100:.0f}% match ({dup.get("method", "hash")})'
                f'</div>'
            )
        forgery_html = _forgery_panel(doc.get("forgery") or {})
        rows.append(
            f"""
            <div class="card">
              <div class="card-head">
                <span><b>{doc['doc_type_label']}</b> &mdash; {doc['file_name']}</span>
                {_status_badge(doc['status'])}
              </div>
              {dup_html}
              {forgery_html}
              <table>
                <tr><th>Field</th><th>Value</th></tr>
                {fields}
              </table>
              <h4>Verification Issues</h4>
              <ul>{issues_html}</ul>
              <p class="muted">OCR: {doc['ocr_provider']} ({'{:.0%}'.format(doc['ocr_confidence'])} confidence) &middot;
              Classification: {'{:.0%}'.format(doc['classification_confidence'])}</p>
            </div>
            """
        )
    return "\n".join(rows)


def build_report_html(report: dict) -> str:
    missing = "".join(f"<li>{DOC_TYPE_LABELS.get(m, m)}</li>" for m in report["missing_documents"]) or "<li>None</li>"
    duplicates = "".join(f"<li>{d}</li>" for d in report["duplicate_documents"]) or "<li>None</li>"
    forged = [
        d for d in report["documents"]
        if (d.get("forgery") or {}).get("level") in ("YELLOW", "RED")
    ]
    forged_rows = "".join(
        f"<li><b>{d['file_name']}</b> — {(d.get('forgery') or {}).get('level')} · "
        f"score {(d.get('forgery') or {}).get('score', 0) * 100:.0f}% · "
        f"{'; '.join((d.get('forgery') or {}).get('summary') or [])[:160]}</li>"
        for d in forged
    ) or "<li>None</li>"
    summary = report.get("summary") or {}
    inconsistencies = summary.get("inconsistencies") or []
    inconsistency_rows = "".join(
        f"<li><b>{i.get('field_label', i.get('field', 'Field'))}</b>: {i.get('document_a')} = '{i.get('value_a')}' vs {i.get('document_b')} = '{i.get('value_b')}'</li>"
        for i in inconsistencies
    ) or "<li>None</li>"
    highlights = "".join(f"<li>{h}</li>" for h in summary.get("highlights", [])) or "<li>No highlights recorded</li>"
    concerns = "".join(f"<li>{c}</li>" for c in summary.get("concerns", [])) or "<li>No concerns recorded</li>"

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>EEF Verification Report {report['report_id']}</title>
<style>
  body{{font-family:'Segoe UI',Arial,sans-serif;background:#0f1115;color:#e6e6e6;margin:0;padding:32px;}}
  .wrap{{max-width:980px;margin:auto;}}
  h1{{font-size:26px;margin:0 0 4px;}}
  .muted{{color:#9aa0a6;font-size:13px;}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:20px 0;}}
  .stat{{background:#181b22;border:1px solid #2a2e37;border-radius:10px;padding:14px 16px;}}
  .stat .v{{font-size:26px;font-weight:700;}}
  .card{{background:#181b22;border:1px solid #2a2e37;border-radius:12px;padding:18px;margin:14px 0;}}
  .card-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;}}
  table{{width:100%;border-collapse:collapse;font-size:14px;}}
  th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid #262b34;}}
  th{{color:#9aa0a6;font-weight:600;}}
  .badge{{padding:2px 8px;border-radius:20px;border:1px solid;font-size:11px;font-weight:700;}}
  ul{{margin:6px 0 6px 18px;}}
  li{{margin:3px 0;}}
  .footer{{margin-top:26px;padding-top:14px;border-top:1px solid #2a2e37;color:#9aa0a6;font-size:12px;}}
</style></head><body><div class="wrap">
<h1>Ezitech Document Verification Report</h1>
<p class="muted">Report {report['report_id']} &middot; Generated {report['generated_at']} &middot; Applicant ref: {report['applicant_ref'] or 'N/A'}</p>

<div class="grid">
  <div class="stat"><div class="muted">Overall Status</div><div class="v">{_status_badge(report['status'])}</div></div>
  <div class="stat"><div class="muted">Completeness</div><div class="v">{'{:.0%}'.format(report['completeness_score'])}</div></div>
  <div class="stat"><div class="muted">Confidence</div><div class="v">{'{:.0%}'.format(report['overall_confidence'])}</div></div>
  <div class="stat"><div class="muted">Documents</div><div class="v">{len(report['documents'])}</div></div>
</div>

<div class="card"><h3>Summary</h3>
  <p>{summary.get('overall_comment', 'No comment generated.')}</p>
  <p><b>Recommended action:</b> {summary.get('recommended_action', 'REVIEW')}</p>
  <h4>Highlights</h4><ul>{highlights}</ul>
  <h4>Concerns</h4><ul>{concerns}</ul>
</div>

<div class="card"><h3>Missing Documents</h3><ul>{missing}</ul></div>
<div class="card"><h3>Duplicate Uploads</h3><ul>{duplicates}</ul></div>
<div class="card"><h3>Forgery &amp; Tampering Analysis</h3><ul>{forged_rows}</ul></div>
<div class="card"><h3>Cross-Document Inconsistencies</h3><ul>{inconsistency_rows}</ul></div>

<h3>Document-Level Analysis</h3>
{_render_document_rows(report)}

<div class="footer">Generated automatically by the Ezitech Engineering Framework &mdash; Intelligent Document Processing &amp; Verification Engine (EEF, AI-004).</div>
</div></body></html>"""


def generate_report(submission, with_pdf: bool = False) -> tuple[Path, str]:
    """Write JSON + HTML (and optional PDF) report. Returns (html_path, url)."""
    report = build_report_json(submission)

    json_path = settings.report_dir / f"submission_{submission.id}.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    html_path = settings.report_dir / f"submission_{submission.id}.html"
    html_path.write_text(build_report_html(report), encoding="utf-8")

    if with_pdf:
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.pdfgen import canvas as _canvas

            pdf_path = settings.report_dir / f"submission_{submission.id}.pdf"
            build_pdf_report(report, str(pdf_path))
            return pdf_path, f"/api/v1/reports/{submission.id}?format=pdf"
        except Exception as exc:  # noqa: BLE001
            logger.warning("PDF generation skipped: %s", exc)

    return html_path, f"/api/v1/reports/{submission.id}?format=html"


def _fmt_value(v):
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if v is None:
        return ""
    return str(v)


def build_pdf_report(report: dict, dest: str) -> None:
    """Render a complete professional PDF report with reportlab platypus.

    Uses Paragraphs and Tables so long field values wrap instead of being
    truncated, and renders every extracted field, every issue, plus the
    Executive Summary, Highlights, Concerns and Cross-Document
    Inconsistencies sections.
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    page = A4
    margin = 16 * mm

    styles = {
        "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=16, leading=19, spaceAfter=2),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12, leading=15, spaceBefore=12, spaceAfter=5, textColor=colors.HexColor("#111827")),
        "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=10, leading=13, spaceBefore=8, spaceAfter=3, textColor=colors.HexColor("#374151")),
        "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#6b7280"), spaceAfter=4),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=12.5, alignment=TA_LEFT),
        "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=9.5, leading=12, leftIndent=14, bulletIndent=2, spaceAfter=1),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, leading=11),
        "cellb": ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=8.5, leading=11),
    }

    story = []

    def section(title: str) -> None:
        story.append(Paragraph(title, styles["h2"]))

    def bullets(items, empty="None") -> None:
        for it in items or [empty]:
            story.append(Paragraph(f"<bullet>&bull;</bullet>{_fmt_value(it)}", styles["bullet"]))

    # Header
    story.append(Paragraph("Ezitech Document Verification Report", styles["h1"]))
    story.append(
        Paragraph(
            f"{report['report_id']} &nbsp;|&nbsp; Generated {report['generated_at']}"
            f"&nbsp;|&nbsp; Applicant: {report['applicant_ref'] or 'N/A'}",
            styles["meta"],
        )
    )
    story.append(
        Paragraph(
            f"<b>Overall Status:</b> {report['status']} &nbsp;&nbsp;"
            f"<b>Completeness:</b> {report['completeness_score']:.0%} &nbsp;&nbsp;"
            f"<b>Confidence:</b> {report['overall_confidence']:.0%} &nbsp;&nbsp;"
            f"<b>Documents:</b> {len(report['documents'])}",
            styles["body"],
        )
    )

    # Executive summary
    summary = report.get("summary") or {}
    section("Executive Summary")
    story.append(Paragraph(_fmt_value(summary.get("overall_comment") or "No comment generated."), styles["body"]))
    story.append(Paragraph(f"<b>Recommended action:</b> {_fmt_value(summary.get('recommended_action') or 'REVIEW')}", styles["body"]))
    story.append(Paragraph("Highlights", styles["h3"]))
    bullets(summary.get("highlights"))
    story.append(Paragraph("Concerns", styles["h3"]))
    bullets(summary.get("concerns"))

    # Missing / duplicates / inconsistencies / forgery
    section("Missing Documents")
    bullets(report["missing_documents"])
    section("Duplicate Uploads")
    bullets(report["duplicate_documents"])
    section("Forgery & Tampering Analysis")
    forged_docs = [
        d for d in report["documents"]
        if (d.get("forgery") or {}).get("level") in ("YELLOW", "RED")
    ]
    if forged_docs:
        for d in forged_docs:
            forg = d.get("forgery") or {}
            lines = [f"Level: {forg.get('level')} (score {forg.get('score', 0):.0%}, confidence {forg.get('confidence', 0):.0%})"]
            lines += [f"{s.get('label', s.get('name', 'Signal'))} [{s.get('result', 'clear').upper()}]: {s.get('detail', '')}"
                      for s in forg.get("signals") or [] if s.get("result") != "clear"]
            llm = forg.get("llm") or {}
            if llm:
                lines.append(f"LLM verdict: {llm.get('verdict')} ({llm.get('confidence', 0):.0%} confidence)")
            story.append(Paragraph(f"<b>{_fmt_value(d.get('file_name'))}</b>", styles["h3"]))
            bullets(lines)
    else:
        bullets([], empty="No forgery indicators detected")
    section("Cross-Document Inconsistencies")
    inconsistencies = summary.get("inconsistencies") or []
    if inconsistencies:
        rows = [[Paragraph("Field", styles["cellb"]), Paragraph("Document A", styles["cellb"]), Paragraph("Value A", styles["cellb"]), Paragraph("Document B", styles["cellb"]), Paragraph("Value B", styles["cellb"])]]
        for i in inconsistencies:
            rows.append([
                Paragraph(f"{_fmt_value(i.get('field_label') or i.get('field', 'Field'))}", styles["cell"]),
                Paragraph(_fmt_value(i.get("document_a")), styles["cell"]),
                Paragraph(_fmt_value(i.get("value_a")), styles["cell"]),
                Paragraph(_fmt_value(i.get("document_b")), styles["cell"]),
                Paragraph(_fmt_value(i.get("value_b")), styles["cell"]),
            ])
        table = Table(rows, colWidths=[45 * mm, 38 * mm, None, 38 * mm, None], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(table)
    else:
        bullets([], empty="None")

    # Document-level analysis
    section("Document-Level Analysis")
    for doc in report["documents"]:
        story.append(
            Paragraph(
                f"{_fmt_value(doc['doc_type_label'])} &mdash; {_fmt_value(doc['file_name'])}",
                ParagraphStyle("dochead", parent=styles["h2"], fontSize=10.5, spaceBefore=10, textColor=colors.HexColor("#111827")),
            )
        )
        dup = doc.get("duplicate") or {}
        meta = f"Status: {_fmt_value(doc['status'])} &nbsp;|&nbsp; OCR: {_fmt_value(doc['ocr_provider'])} ({doc['ocr_confidence']:.0%}) &nbsp;|&nbsp; Classification: {doc['classification_confidence']:.0%}"
        if dup.get("is_duplicate"):
            meta += f" &nbsp;|&nbsp; Duplicate of {_fmt_value(dup.get('matched_file') or 'another document in this batch')} ({dup.get('similarity', 0) * 100:.0f}% match)"
        forg = doc.get("forgery") or {}
        if forg.get("level") in ("YELLOW", "RED"):
            meta += f" &nbsp;|&nbsp; Forgery analysis: {forg.get('level')} (score {forg.get('score', 0):.0%})"
        story.append(Paragraph(meta, styles["meta"]))

        extracted = doc["extracted"] or {}
        if extracted:
            rows = [[Paragraph("Field", styles["cellb"]), Paragraph("Value", styles["cellb"])]]
            for k, v in extracted.items():
                rows.append([Paragraph(k.replace("_", " ").title(), styles["cell"]), Paragraph(_fmt_value(v), styles["cell"])])
            table = Table(rows, colWidths=[52 * mm, None], repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(table)
        else:
            story.append(Paragraph("No fields extracted.", styles["body"]))

        story.append(Paragraph("Verification Issues", styles["h3"]))
        issues = doc.get("issues") or []
        if issues:
            for issue in issues:
                sev = _fmt_value(issue.get("severity") or "info").upper()
                story.append(Paragraph(f"<bullet>&bull;</bullet><b>[{sev}]</b> {_fmt_value(issue.get('message'))}", styles["bullet"]))
        else:
            story.append(Paragraph("No issues detected.", styles["body"]))
        story.append(Spacer(1, 4))

    doc = SimpleDocTemplate(
        dest,
        pagesize=page,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
        title=f"EEF Verification Report {report['report_id']}",
        author="Ezitech Engineering Framework",
    )
    doc.build(story)


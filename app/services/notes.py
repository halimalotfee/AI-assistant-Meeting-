import os
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from markdown_it import MarkdownIt
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.models.notes import MeetingSummary, Topic, ActionItem

from openai import OpenAI


from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from app.models.notes import Topic, ActionItem, MeetingSummary

client = OpenAI()

#PROMPT 
_SYSTEM_PROMPT = """You are a meeting notes generator.
Given a raw meeting transcript (with optional timestamps), produce a clean, structured summary.

Respond in JSON with the following keys:

- executive_summary: string
- objectives: array of strings
- topics: array of objects
  - title: string
  - description: string (short summary of what was discussed on this topic)
  - start: optional string timestamp, e.g. "00:12:34"
  - end: optional string timestamp
- decisions: array of strings (each is one important decision)
- actions: array of objects
  - owner: optional string (person responsible)
  - action: string (what needs to be done)
  - due: optional string (deadline or time frame)
- outcomes: array of strings (what was achieved or the current status of main objectives)
- next_steps: array of strings (clear next steps or follow-ups, including next meeting info if mentioned)

Keep it concise and faithful to the transcript. Keep language the same as the transcript.
If unsure about owner/due, leave them null.
If some sections are not clearly mentioned in the transcript, infer briefly or leave them empty.
"""

def _build_user_prompt(transcript_text: str, lang: str = "auto") -> str:
    return f"""LANGUAGE: {lang}
TRANSCRIPT:
{transcript_text}
"""

def generate_structured_notes(transcript_text: str, language: str = "auto") -> MeetingSummary:
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(transcript_text, language)},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    data = completion.choices[0].message.content

    import json
    parsed = json.loads(data)

    topics = [Topic(**t) for t in parsed.get("topics", [])]
    actions = [ActionItem(**a) for a in parsed.get("actions", [])]

    return MeetingSummary(
        executive_summary=(parsed.get("executive_summary") or "").strip(),
        objectives=parsed.get("objectives", []) or [],
        topics=topics,
        decisions=parsed.get("decisions", []) or [],
        actions=actions,
        outcomes=parsed.get("outcomes", []) or [],
        next_steps=parsed.get("next_steps", []) or [],
    )



def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def render_markdown(summary: MeetingSummary, transcript_text: str) -> str:
    lines: List[str] = []
    lines.append("# Meeting Report")
    lines.append("")

    lines.append("## Summary")
    lines.append(summary.executive_summary or "_(Not available)_")
    lines.append("")

    if summary.objectives:
        lines.append("## Meeting Objectives")
        for i, obj in enumerate(summary.objectives, start=1):
            lines.append(f"{i}. {obj}")
        lines.append("")

    if summary.topics:
        lines.append("## Key Discussion Points")
        for i, t in enumerate(summary.topics, start=1):
            lines.append(f"### {i}. {t.title}")
            if t.description:
                lines.append(t.description)
            if t.start or t.end:
                times = []
                if t.start: times.append(f"start {t.start}")
                if t.end: times.append(f"end {t.end}")
                lines.append(f"_({', '.join(times)})_")
            lines.append("")
        lines.append("")

    if summary.decisions:
        lines.append("## Important Decisions")
        for i, d in enumerate(summary.decisions, start=1):
            lines.append(f"{i}. {d}")
        lines.append("")

    if summary.actions:
        lines.append("## Action Items")
        for i, a in enumerate(summary.actions, start=1):
            who = f"**{a.owner}** - " if a.owner else ""
            due = f" _(due {a.due})_" if a.due else ""
            lines.append(f"{i}. {who}{a.action}{due}")
        lines.append("")

    if summary.outcomes:
        lines.append("## Meeting Outcomes")
        for i, o in enumerate(summary.outcomes, start=1):
            lines.append(f"{i}. {o}")
        lines.append("")

    if summary.next_steps:
        lines.append("## Next Steps")
        for i, s in enumerate(summary.next_steps, start=1):
            lines.append(f"{i}. {s}")
        lines.append("")

    lines.append("---")
    lines.append("## Full Transcript")
    lines.append("")
    lines.append("```text")
    lines.append(transcript_text.strip())
    lines.append("```")
    return "\n".join(lines)


def save_markdown(md_text: str, out_dir: str) -> str:
    _ensure_dir(out_dir)
    md_path = os.path.join(out_dir, "meeting-notes.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_text)
    return md_path

def save_pdf_simple(md_text: str, out_dir: str) -> str:
    """
    Export PDF simple.
    Le Markdown sera aplati
    """
    _ensure_dir(out_dir)
    pdf_path = os.path.join(out_dir, "meeting-notes.pdf")
    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    # Marges
    x = 40
    y = height - 40
    max_width = width - 80

    import textwrap
    for paragraph in md_text.split("\n"):
        paragraph = paragraph.replace("## ", "").replace("# ", "").replace("**", "")
        for line in textwrap.wrap(paragraph, width=95):
            c.drawString(x, y, line)
            y -= 14
            if y < 40:
                c.showPage()
                y = height - 40
        y -= 6  # espace après paragraphe

    c.showPage()
    c.save()
    return pdf_path

def make_report_id() -> str:
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
    rid = uuid.uuid4().hex[:6]
    return f"{ts}_{rid}"

def generate_pdf_report(summary: MeetingSummary, transcript: str, pdf_path: str) -> str:
    """
    PDF structuré selon le template 
    """
    doc = SimpleDocTemplate(pdf_path, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    body_style = styles["BodyText"]
    body_style.leading = 14

    # SUMMARY
    elements.append(Paragraph("SUMMARY", styles["Heading1"]))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(summary.executive_summary or "No summary available.", body_style))
    elements.append(Spacer(1, 12))

    # Meeting Objectives
    elements.append(Paragraph("1. Meeting Objectives", styles["Heading2"]))
    if summary.objectives:
        for idx, obj in enumerate(summary.objectives, start=1):
            elements.append(Paragraph(f"{idx}. {obj}", body_style))
    else:
        if summary.topics:
            for idx, t in enumerate(summary.topics, start=1):
                elements.append(Paragraph(f"{idx}. {t.title}", body_style))
        else:
            elements.append(Paragraph("Objectives were not explicitly specified.", body_style))
    elements.append(Spacer(1, 12))

    # Key Discussion Points
    elements.append(Paragraph("2. Key Discussion Points", styles["Heading2"]))
    if summary.topics:
        for i, topic in enumerate(summary.topics, start=1):
            elements.append(Paragraph(f"2.{i} Topic: {topic.title}", styles["Heading3"]))
            if topic.description:
                elements.append(Paragraph(topic.description, body_style))
            else:
                elements.append(Paragraph("No detailed description provided.", body_style))
            elements.append(Spacer(1, 4))
    else:
        elements.append(Paragraph("No topics were extracted from this meeting.", body_style))
    elements.append(Spacer(1, 12))

    # Important Decisions
    elements.append(Paragraph("3. Important Decisions", styles["Heading2"]))
    if summary.decisions:
        for i, d in enumerate(summary.decisions, start=1):
            elements.append(Paragraph(f"{i}. {d}", body_style))
    else:
        elements.append(Paragraph("No explicit decisions were captured.", body_style))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph("4. Action Items", styles["Heading2"]))
    if summary.actions:
        data = [["#", "Owner", "Action", "Deadline"]]
        for i, a in enumerate(summary.actions, start=1):
            data.append([
                str(i),
                a.owner or "-",
                a.action,
                a.due or "-",
            ])
        t = Table(data, hAlign="LEFT", colWidths=[30, 100, 260, 80])
        t.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
            ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
        ]))
        elements.append(t)
    else:
        elements.append(Paragraph("No action items were identified.", body_style))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph("5. Meeting Outcomes", styles["Heading2"]))
    if summary.outcomes:
        for i, o in enumerate(summary.outcomes, start=1):
            elements.append(Paragraph(f"{i}. {o}", body_style))
    else:
        elements.append(Paragraph("Outcomes were not explicitly specified.", body_style))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph("6. Next Steps", styles["Heading2"]))
    if summary.next_steps:
        for i, s in enumerate(summary.next_steps, start=1):
            elements.append(Paragraph(f"{i}. {s}", body_style))
    else:
        elements.append(Paragraph("No specific next steps were documented.", body_style))
    elements.append(Spacer(1, 16))

    elements.append(Paragraph("Appendix – Full Transcript", styles["Heading2"]))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(transcript[:20000], body_style))

    doc.build(elements)
    return pdf_path

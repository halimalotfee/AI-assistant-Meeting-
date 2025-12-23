from typing import Optional
import os, json, traceback

from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Form
from fastapi.responses import JSONResponse, FileResponse

from app.schemas.reports import TranscribeResponse, Transcript, TranscriptSegment
from app.services.transcription import (
    transcribe_audio,
    TranscriptionError,
    assign_speakers_round_robin,
)
from app.services.notes import (
    generate_structured_notes,
    render_markdown,
    save_markdown,
    generate_pdf_report,
    make_report_id,
)
from app.models.notes import NotesResponse, MeetingSummary

router = APIRouter(prefix="/reports", tags=["reports"])

DATA_ROOT = os.getenv("DATA_ROOT", "/data/reports")


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_endpoint(
    file: UploadFile = File(...),
    language_hint: str | None = Query(default=None, description="ex: 'fr', 'en'"),
    diarization: str = Query(
        default="none",
        pattern="^(none|alternate)$",
        description="none=pas de speaker; alternate=heuristique simple selon pauses",
    ),
    gap_threshold: float = Query(
        default=1.0,
        ge=0.2,
        le=5.0,
        description="seuil de pause (s) pour alternance",
    ),
    max_speakers: int = Query(
        default=4,
        ge=1,
        le=8,
        description="Nombre max. de speakers (approximation, round-robin)"
    ),
):

    lang_hint_clean=(language_hint or "").strip() if language_hint is not None else ""
    if lang_hint_clean.lower()=="auto":
        lang_hint_clean=""
    try:
        content = await file.read()
       
        '''if diarization == "advanced":
            text, segs, lang = await transcribe_audio_with_advanced_diarization(
                content,
                file.filename,
                lang_hint_clean or None,
            )
        else:
            text, segs, lang = await transcribe_audio(
                content,
                file.filename,
                lang_hint_clean or None,
            )
            if diarization == "alternate":
                segs = assign_speakers_alternate(
                    segs,
                    gap_threshold=gap_threshold,
                    max_speakers=2,
                )'''
        text, segs, lang = await transcribe_audio(
            content,
            file.filename,
            lang_hint_clean or None,
        )
        if diarization == "alternate":
            segs = assign_speakers_round_robin(
                segs,
                gap_threshold=gap_threshold,
                max_speakers=max_speakers,
            )
        transcript = Transcript(
            language=lang or "unknown",
            text=text or "",
            segments=[TranscriptSegment(**s) for s in segs],
        )
        return TranscribeResponse(transcript=transcript)

    except TranscriptionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print("TRACE:\n", traceback.format_exc(), flush=True)
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")
    
@router.post("/notes", response_model=NotesResponse)
async def generate_notes_endpoint(
    file: Optional[UploadFile] = File(default=None),
    transcript: Optional[str] = Form(default=None),
    language_hint: str = Form(default="auto"),
    diarization: str = Form(default="none"),
    gap_threshold: float = Form(default=1.0),
    export_pdf: bool = Form(default=False),
):
    """
    Génèration des notes de réunion 
    """
    if not file and not transcript:
        raise HTTPException(status_code=400, detail="Provide either 'file' or 'transcript'.")

    
    lang_hint_clean = (language_hint or "").strip()
    if lang_hint_clean.lower() == "auto":
        lang_hint_clean = ""

    transcript_text: Optional[str] = None
    lang: Optional[str] = None  

    if file:
        content = await file.read()
        try:
            text, segs, lang_detected = await transcribe_audio(
                content,
                file.filename,
                lang_hint_clean or None,  
            )
            transcript_text = text
            if lang_detected:
                lang = lang_detected
            elif lang_hint_clean:
                lang = lang_hint_clean
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")
    else:
        try:
            maybe = json.loads(transcript)
            transcript_text = maybe.get("text") or transcript
        except Exception:
            transcript_text = transcript

        if lang_hint_clean:
            lang = lang_hint_clean

    if not transcript_text or not transcript_text.strip():
        raise HTTPException(status_code=400, detail="Transcript is empty.")

    try:
        summary: MeetingSummary = generate_structured_notes(
            transcript_text,
            lang or lang_hint_clean or None,  # au cas où
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Notes generation failed: {e}")

    report_id = make_report_id()
    out_dir = os.path.join(DATA_ROOT, report_id)
    md_text = render_markdown(summary, transcript_text)
    md_path = save_markdown(md_text, out_dir)
    pdf_path = None
    if export_pdf:
        pdf_path = os.path.join(out_dir, "meeting-report.pdf")
        generate_pdf_report(summary, transcript_text, pdf_path)

    md_filename = os.path.basename(md_path)
    pdf_filename = os.path.basename(pdf_path) if pdf_path else None

    exports = {
        "markdown_path": md_path,
        "pdf_path": pdf_path,
        "markdown_url": f"/reports/files/{report_id}/{md_filename}",
        "pdf_url": f"/reports/files/{report_id}/{pdf_filename}" if pdf_filename else None,
    }

    return JSONResponse(
        content=NotesResponse(
            report_id=report_id,
            language=lang or lang_hint_clean or "unknown",
            transcript_text=transcript_text,
            summary=summary,
            exports=exports,
        ).model_dump()
    )
@router.get("/files/{report_id}/{filename}")
async def download_report_file(report_id: str, filename: str):
    """
    Sert un fichier de rapport (Markdown ou PDF) pour téléchargement.
    Utilisé par les URLs markdown_url / pdf_url renvoyées à Streamlit.
    """
    file_path = os.path.join(DATA_ROOT, report_id, filename)

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # Déterminer le type MIME
    if filename.endswith(".pdf"):
        media_type = "application/pdf"
    elif filename.endswith(".md"):
        media_type = "text/markdown"
    else:
        media_type = "application/octet-stream"

    return FileResponse(
        file_path,
        media_type=media_type,
        filename=filename,
    )

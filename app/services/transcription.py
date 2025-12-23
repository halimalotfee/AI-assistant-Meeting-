import io
from typing import Tuple, List, Dict

from pydub import AudioSegment
from pydub.utils import which
from openai import OpenAI
import os
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Tuple, Optional

from app.core.config import settings

OPENAI_API_KEY = settings.OPENAI_API_KEY
ASR_MODEL_ID = settings.ASR_MODEL_ID or "gpt-4o-mini-transcribe"
BACKEND = getattr(settings, "BACKEND", None) or "openai"

MAX_BYTES = 24 * 1024 * 1024  
CHUNK_SEC = 600               

AudioSegment.converter = which("ffmpeg")
AudioSegment.ffmpeg = AudioSegment.converter
AudioSegment.ffprobe = which("ffprobe")

class TranscriptionError(Exception):
    pass
from openai import OpenAI

def _make_openai_client() -> OpenAI:
    
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        raise TranscriptionError("OPENAI_API_KEY is missing.")
    return OpenAI(api_key=api_key)


def _load_and_resample(file_bytes: bytes, filename: str) -> AudioSegment:
    buf = io.BytesIO(file_bytes)
    buf.name = filename or "audio.bin"
    audio = AudioSegment.from_file(buf)
    return audio.set_channels(1).set_frame_rate(16000)

def _export_chunk_wav(seg: AudioSegment) -> bytes:
    out = io.BytesIO()
    seg.export(out, format="wav")
    return out.getvalue()

def _openai_stt_bytes(client: OpenAI, audio_bytes: bytes, fname: str, language_hint: str | None):
    bio = io.BytesIO(audio_bytes)
    bio.name = fname
    model_id = ASR_MODEL_ID.lower()
    if "whisper" in model_id:
        resp_format = "verbose_json"
    else:
        resp_format = "json"

    return client.audio.transcriptions.create(
        model=ASR_MODEL_ID,
        file=bio,
        response_format=resp_format,
        language=(language_hint or None)  
    )

def _parse_verbose_json(data: dict, language_hint: str | None):
  
    text = data.get("text") or ""
    language = data.get("language") or language_hint or "unknown"

    segments_json = data.get("segments") or []
    segments = []

    for s in segments_json:
        if isinstance(s, dict):
            start = float(s.get("start", 0.0) or 0.0)
            end   = float(s.get("end", 0.0)   or 0.0)
            text_s = (s.get("text") or "").strip()
        else:
            start = float(getattr(s, "start", 0.0) or 0.0)
            end   = float(getattr(s, "end", 0.0)   or 0.0)
            text_s = (getattr(s, "text", "") or "").strip()

        segments.append({"start": start, "end": end, "text": text_s})

    if not segments:
        segments = [{"start": 0.0, "end": 0.0, "text": text}]

    return text, segments, language

def _openai_transcribe_chunked(file_bytes: bytes, filename: str, language_hint: str | None):
    if not OPENAI_API_KEY:
        raise TranscriptionError("OPENAI_API_KEY is missing.")
    client = _make_openai_client()

    audio = _load_and_resample(file_bytes, filename)

    single = _export_chunk_wav(audio)
    if len(single) <= MAX_BYTES:
        resp = _openai_stt_bytes(client, single, "chunk.wav", language_hint)
        data = {
            "text": getattr(resp, "text", None),
            "language": getattr(resp, "language", None),
            "segments": getattr(resp, "segments", None),
        }
        return _parse_verbose_json(data, language_hint)

    total_ms = len(audio)
    step = CHUNK_SEC * 1000
    chunks: list[AudioSegment] = [audio[i:i+step] for i in range(0, total_ms, step)]

    full_text_parts: list[str] = []
    all_segments: list[Dict] = []
    offset = 0.0
    language_final = language_hint or "unknown"

    jobs = []
    offsets = []  

    running_ms = 0
    for i, seg in enumerate(chunks):
        b = _export_chunk_wav(seg)
        parts = [seg[: len(seg)//2], seg[len(seg)//2:]] if len(b) > MAX_BYTES else [seg]

        local_off = 0.0
        for j, sseg in enumerate(parts):
            sb = _export_chunk_wav(sseg)
            jobs.append((i, j, sb))
            offsets.append(running_ms/1000.0 + local_off)
            local_off += len(sseg)/1000.0

        running_ms += len(seg)


    full_text_parts = []
    all_segments = []
    language_final = language_hint or "unknown"

    def worker(args):
        i, j, sb = args
        resp = _openai_stt_bytes(client, sb, f"chunk_{i}_{j}.wav", language_hint)
        data = {
            "text": getattr(resp, "text", None),
            "language": getattr(resp, "language", None),
            "segments": getattr(resp, "segments", None),
        }
        return (i, j, data)

    max_workers = 4
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(worker, job): k for k, job in enumerate(jobs)}
        for fut in as_completed(futures):
            k = futures[fut]
            try:
                i, j, data = fut.result()
            except Exception as e:
                all_segments.append({"start": 0.0, "end": 0.0, "text": f"[ERROR chunk {k}: {e}]"})
                continue

            t, segs, lang = _parse_verbose_json(data, language_hint)
            if lang and language_final == "unknown":
                language_final = lang
            if t:
                full_text_parts.append(t)

            off = offsets[k]
            for s in segs:
                s["start"] = float(s["start"]) + off
                s["end"]   = float(s["end"]) + off
                all_segments.append(s)
        results = []  

    def worker(args):
        i, j, sb = args
        resp = _openai_stt_bytes(client, sb, f"chunk_{i}_{j}.wav", language_hint)
        data = {
            "text": getattr(resp, "text", None),
            "language": getattr(resp, "language", None),
            "segments": getattr(resp, "segments", None),
        }
        return (i, j, data)

    max_workers = 4
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(worker, job): k for k, job in enumerate(jobs)}
        for fut in as_completed(futures):
            k = futures[fut]
            try:
                i, j, data = fut.result()
            except Exception as e:
                results.append((offsets[k], f"[ERROR chunk {k}: {e}]", []))
                continue

            t, segs, lang = _parse_verbose_json(data, language_hint)
            if lang and language_final == "unknown":
                language_final = lang

            results.append((offsets[k], t, segs))

    results.sort(key=lambda x: x[0])

    full_text_parts = []
    all_segments = []
    for off, t, segs in results:
        if t:
            full_text_parts.append(t)
        for s in segs:
            s["start"] = float(s["start"]) + off
            s["end"]   = float(s["end"]) + off
            all_segments.append(s)

    all_segments.sort(key=lambda s: s["start"])

    full_text = " ".join([p.strip() for p in full_text_parts if p.strip()])
    if not all_segments:
        all_segments = [{"start": 0.0, "end": 0.0, "text": full_text}]
    return full_text, all_segments, language_final
        
    

async def transcribe_audio(file_bytes: bytes, filename: str, language_hint: str | None = None):
    if BACKEND != "openai":
        raise TranscriptionError("Set BACKEND=openai to use OpenAI STT.")
    return _openai_transcribe_chunked(file_bytes, filename, language_hint)


'''async def transcribe_audio_with_advanced_diarization(
    audio_bytes: bytes,
    filename: str,
    language_hint: Optional[str] = None,
) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
    """
    Transcrit l'audio,Applique la diarisation avancée 
    Retourne texte + segments enrichis en 'speaker'
    """
    text, segs, lang = await transcribe_audio(
        audio_bytes,
        filename,
        language_hint,
    )

    speaker_segments = diarize_audio_bytes(audio_bytes)

    segs_with_speakers = assign_speakers_by_overlap(segs, speaker_segments)

    return text, segs_with_speakers, lang'''

'''def assign_speakers_alternate(
    segments: List[Dict],
    gap_threshold: float = 1.0,
    max_speakers: int = 2
) -> List[Dict]:
    if not segments:
        return segments
    current = 0
    speakers = [f"Speaker {i+1}" for i in range(max_speakers)]
    out: List[Dict] = []
    prev_end = segments[0].get("end", 0.0)
    for i, s in enumerate(segments):
        start = s.get("start", 0.0)
        end = s.get("end", start)
        if i > 0 and (start - prev_end) > gap_threshold:
            current = (current + 1) % max_speakers
        s2 = dict(s)
        s2["speaker"] = speakers[current]
        out.append(s2)
        prev_end = end
    return out'''
def assign_speakers_round_robin(
    segments: list[dict],
    gap_threshold: float = 1.0,
    max_speakers: int = 6,
) -> list[dict]:
  
    if not segments:
        return segments

    current_speaker_idx = 1
    prev_end = segments[0].get("end", 0.0)

    segments[0]["speaker"] = f"Speaker {current_speaker_idx}"

    for i in range(1, len(segments)):
        seg = segments[i]
        start = float(seg.get("start", prev_end))
        end = float(seg.get("end", start))
        gap = max(0.0, start - prev_end)

        if gap >= gap_threshold:
            current_speaker_idx = (current_speaker_idx % max_speakers) + 1

        seg["speaker"] = f"Speaker {current_speaker_idx}"
        prev_end = end

    return segments

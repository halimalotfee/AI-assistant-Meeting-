import os
import tempfile
from typing import List, Dict, Any

from pyannote.audio import Pipeline

_pipeline = None

def get_diarization_pipeline() -> Pipeline:
    global _pipeline
    if _pipeline is None:
        hf_token = os.getenv("HUGGINGFACE_TOKEN")
        if not hf_token:
            raise RuntimeError("HUGGINGFACE_TOKEN is not set in environment.")
        _pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization",
            use_auth_token=hf_token,
        )
    return _pipeline


def diarize_audio_bytes(audio_bytes: bytes, file_suffix: str = ".wav") -> List[Dict[str, Any]]:
    """
    Prend des bytes audio, les écrit dans un fichier temporaire,
    applique pyannote, et renvoie une liste de segments :
    [
      {"start": float, "end": float, "speaker": "SPEAKER_00"},
      ...
    ]
    """
    pipeline = get_diarization_pipeline()

    # audio dans un fichier temporaire
    with tempfile.NamedTemporaryFile(suffix=file_suffix, delete=True) as tmp:
        tmp.write(audio_bytes)
        tmp.flush()

        diarization = pipeline(tmp.name)

    segments = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append(
            {
                "start": float(turn.start),
                "end": float(turn.end),
                "speaker": str(speaker),
            }
        )
    return segments


def assign_speakers_by_overlap(
    text_segments: List[Dict[str, Any]],
    speaker_segments: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Assigne un speaker à chaque segment texte en fonction du chevauchement max
    avec les segments de diarisation.
    - text_segments: ce qui vient de Whisper
    - speaker_segments: ce qui vient de pyannote (start, end, speaker)
    """
    def overlap(a_start, a_end, b_start, b_end) -> float:
        return max(0.0, min(a_end, b_end) - max(a_start, b_start))

    results = []
    for seg in text_segments:
        ts = float(seg.get("start", 0.0))
        te = float(seg.get("end", ts))
        best_speaker = None
        best_ov = 0.0

        for sp in speaker_segments:
            ov = overlap(ts, te, sp["start"], sp["end"])
            if ov > best_ov:
                best_ov = ov
                best_speaker = sp["speaker"]

        new_seg = dict(seg)
        if best_speaker is not None:
            new_seg["speaker"] = best_speaker
        else:
            new_seg["speaker"] = "UNKNOWN"

        results.append(new_seg) #Retourne une nouvelle liste de segments texte avec une clé speaker


    return results

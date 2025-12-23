from typing import List, Optional
from pydantic import BaseModel, Field

class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str
    speaker: Optional[str] = None

class Transcript(BaseModel):
    language: str
    text: str
    segments: List[TranscriptSegment] = Field(default_factory=list)

class TranscribeResponse(BaseModel):
    transcript: Transcript

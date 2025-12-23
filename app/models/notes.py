from pydantic import BaseModel, Field
from typing import List, Optional, Dict


class Topic(BaseModel):
    title: str
    description: Optional[str] = None
    start: Optional[str] = None  # "HH:MM:SS" si disponible
    end: Optional[str] = None


class ActionItem(BaseModel):
    owner: Optional[str] = None
    action: str
    due: Optional[str] = None  


class MeetingSummary(BaseModel):
    executive_summary: str = Field(..., description="Résumé clair et concis")
    objectives: List[str] = []
    topics: List[Topic] = []
    decisions: List[str] = []
    actions: List[ActionItem] = []
    outcomes: List[str] = []
    next_steps: List[str] = []


class NotesResponse(BaseModel):
    report_id: str
    language: str
    transcript_text: str
    summary: MeetingSummary
    exports: Dict[str, Optional[str]]

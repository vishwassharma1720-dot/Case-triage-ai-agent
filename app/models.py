from typing import List, Literal, Dict, Any

from pydantic import BaseModel, Field


class ToolRequest(BaseModel):
    action: Literal[
        "compare_fields",
        "fuzzy_score",
        "timeline_gap",
        "find_other_cases",
        "finish",
    ]


class FinalVerdict(BaseModel):

    verdict: Literal[
        "DUPLICATE",
        "NOT_DUPLICATE",
        "UNSURE",
    ]

    confidence: float

    evidence: List[str]


class AgentState(BaseModel):

    case1_id: str
    case2_id: str

    evidence: List[str] = Field(default_factory=list)

    tool_history: List[Dict[str, Any]] = Field(default_factory=list)

    steps: int = 0
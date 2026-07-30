import json
import logging
import google.generativeai as genai
from typing import Dict, Literal
from pydantic import ValidationError

from app.models import AgentState, ToolRequest, FinalVerdict
from app.prompts import (
    TOOL_SELECTION_PROMPT,
    FINAL_VERDICT_PROMPT,
)
from app.tools import (
    compare_fields,
    fuzzy_score,
    timeline_gap,
    find_other_cases,
)

logger = logging.getLogger(__name__)


class DuplicateInvestigationAgent:
    """
    Autonomous AI agent for investigating duplicate CRM support cases.
    
    Uses Gemini to decide which tools to run, accumulates evidence,
    and generates a final verdict with confidence and reasoning.
    """

    MAX_STEPS = 5
    MAX_RETRIES = 2

    def __init__(self, api_key: str, dataframe):
        """
        Initialize the agent with Gemini API and a dataframe of cases.
        
        Args:
            api_key: Google AI API key for Gemini access.
            dataframe: Pandas DataFrame with columns: case_id, subject, description, 
                      account_name, contact_email, priority, channel, status, created_at.
        """
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-3.5-flash-lite")
        self.df = dataframe
        
        # Case ID lookup for O(1) access
        self.case_lookup: Dict[str, Dict] = {
            str(row["case_id"]): row.to_dict() 
            for _, row in dataframe.iterrows()
        }

        # Tool registry: maps action names to bound methods
        self.tools = {
            "compare_fields": self._compare_fields,
            "fuzzy_score": self._fuzzy_score,
            "timeline_gap": self._timeline_gap,
            "find_other_cases": self._find_other_cases,
        }

    def investigate(self, case1: Dict, case2: Dict) -> Dict:
        """
        Main investigation loop: iteratively gather evidence and produce a verdict.
        
        Workflow:
        1. Initialize state with case pair.
        2. Repeat up to MAX_STEPS times:
           - Ask model which tool to run next.
           - If "finish", break loop.
           - Otherwise, execute tool and store result + evidence.
        3. Send collected evidence to model for final verdict.
        
        Args:
            case1, case2: Row dicts with case data.
            
        Returns:
            Dict with keys:
                - state: AgentState (evidence, tool_history, steps)
                - verdict: FinalVerdict (verdict, confidence, evidence list)
        """
        state = AgentState(
            case1_id=str(case1["case_id"]),
            case2_id=str(case2["case_id"]),
        )

        while state.steps < self.MAX_STEPS:
            action = self._select_next_tool(case1, case2, state)

            if action == "finish":
                logger.info(
                    f"Agent finished investigation for {case1['case_id']} vs {case2['case_id']} "
                    f"after {state.steps} steps"
                )
                break

            try:
                result = self.tools[action](case1, case2)
                state.tool_history.append({
                    "tool": action,
                    "result": result,
                })
                state.evidence.append(f"{action}: {json.dumps(result)}")
                logger.debug(f"Tool '{action}' executed: {result}")
            except Exception as e:
                logger.error(f"Tool '{action}' failed: {e}")
                state.evidence.append(f"{action}: ERROR - {str(e)}")

            state.steps += 1

        verdict = self._final_verdict(case1, case2, state)

        return {
            "case1_id": state.case1_id,
            "case2_id": state.case2_id,
            "state": state.model_dump(),
            "verdict": verdict.model_dump() if isinstance(verdict, FinalVerdict) else verdict,
        }

    def _select_next_tool(
        self,
        case1: Dict,
        case2: Dict,
        state: AgentState,
    ) -> Literal["compare_fields", "fuzzy_score", "timeline_gap", "find_other_cases", "finish"]:
        """
        Ask Gemini which tool to run next based on current evidence.
        
        Handles:
        - Malformed JSON responses (retries with backoff).
        - Free-tier rate limits (graceful fallback).
        - Already-executed tools (avoids duplication).
        
        Args:
            case1, case2: Case dicts.
            state: Current investigation state.
            
        Returns:
            Tool name string or "finish".
        """
        executed_tools = [t["tool"] for t in state.tool_history]
        
        prompt = f"""{TOOL_SELECTION_PROMPT}

Already executed tools: {executed_tools}

Current evidence:
{chr(10).join(state.evidence) if state.evidence else "(No evidence collected yet)"}

Case 1:
Case ID: {case1.get("case_id", "N/A")}
Subject: {case1.get("subject", "N/A")}
Description: {case1.get("description", "N/A")[:200]}
Account: {case1.get("account_name", "N/A")}
Contact Name: {case1.get("contact_name", "N/A")}
Email: {case1.get("contact_email", "N/A")}
Priority: {case1.get("priority", "N/A")}
Channel: {case1.get("channel", "N/A")}
Status: {case1.get("status", "N/A")}
Created At: {case1.get("created_at", "N/A")}

Case 2:
Case ID: {case2.get("case_id", "N/A")}
Subject: {case2.get("subject", "N/A")}
Description: {case2.get("description", "N/A")[:200]}
Account: {case2.get("account_name", "N/A")}
Contact Name: {case2.get("contact_name", "N/A")}
Email: {case2.get("contact_email", "N/A")}
Priority: {case2.get("priority", "N/A")}
Channel: {case2.get("channel", "N/A")}
Status: {case2.get("status", "N/A")}
Created At: {case2.get("created_at", "N/A")}

Respond with ONLY valid JSON in this format:
{{"action": "compare_fields"}}

OR

{{"action": "fuzzy_score"}}

OR

{{"action": "timeline_gap"}}

OR

{{"action": "find_other_cases"}}

OR

{{"action": "finish"}}
"""

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.model.generate_content(prompt)
                text = response.text.strip()

                if text.startswith("```"):
                    text = text.replace("```json", "").replace("```", "").strip()
                data = json.loads(text)
                
                # Validate using ToolRequest schema
                tool_req = ToolRequest(action=data["action"])
                if tool_req.action in executed_tools:
                    return "finish"
                logger.info(f"Tool selected: {tool_req.action}")
                return tool_req.action
                
            except json.JSONDecodeError as e:
                logger.warning(f"Attempt {attempt + 1}: Malformed JSON from model: {e}")
                if attempt == self.MAX_RETRIES - 1:
                    logger.error("Max retries exhausted for tool selection. Returning 'finish'.")
                    return "finish"
                    
            except ValidationError as e:
                logger.warning(f"Attempt {attempt + 1}: Invalid tool action: {e}")
                if attempt == self.MAX_RETRIES - 1:
                    logger.error("Max retries exhausted. Returning 'finish'.")
                    return "finish"
                    
            except Exception as e:
                logger.error(f"Attempt {attempt + 1}: Gemini request failed: {e}")
                if attempt == self.MAX_RETRIES - 1:
                    logger.error("Max retries exhausted. Returning 'finish'.")
                    return "finish"

        return "finish"

    def _final_verdict(
        self,
        case1: Dict,
        case2: Dict,
        state: AgentState,
    ) -> FinalVerdict:
        """
        Generate final verdict based on collected evidence.
        
        Handles:
        - Malformed JSON responses.
        - Graceful fallback to UNSURE on failure.
        
        Args:
            case1, case2: Case dicts.
            state: Investigation state with all accumulated evidence.
            
        Returns:
            FinalVerdict object with verdict, confidence, and evidence.
        """
        prompt = f"""{FINAL_VERDICT_PROMPT}

Case 1:
Case ID: {case1.get("case_id", "N/A")}
Subject: {case1.get("subject", "N/A")}
Description: {case1.get("description", "N/A")[:200]}
Account: {case1.get("account_name", "N/A")}
Contact Name: {case1.get("contact_name", "N/A")}
Email: {case1.get("contact_email", "N/A")}
Priority: {case1.get("priority", "N/A")}
Channel: {case1.get("channel", "N/A")}
Status: {case1.get("status", "N/A")}
Created At: {case1.get("created_at", "N/A")}

Case 2:
Case ID: {case2.get("case_id", "N/A")}
Subject: {case2.get("subject", "N/A")}
Description: {case2.get("description", "N/A")[:200]}
Account: {case2.get("account_name", "N/A")}
Contact Name: {case2.get("contact_name", "N/A")}
Email: {case2.get("contact_email", "N/A")}
Priority: {case2.get("priority", "N/A")}
Channel: {case2.get("channel", "N/A")}
Status: {case2.get("status", "N/A")}
Created At: {case2.get("created_at", "N/A")}

Evidence collected:
{chr(10).join(state.evidence) if state.evidence else "(No evidence collected yet)"}

Respond with ONLY valid JSON in this format:
{{
  "verdict": "DUPLICATE",
  "confidence": 0.95,
  "evidence": [
    "Reason 1",
    "Reason 2"
  ]
}}
"""

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.model.generate_content(prompt)
                text = response.text.strip()

                if text.startswith("```"):
                    text = text.replace("```json", "").replace("```", "").strip()
                data = json.loads(text)
                
                # Validate using FinalVerdict schema
                verdict = FinalVerdict(**data)
                logger.info(f"Verdict: {verdict.verdict} (confidence: {verdict.confidence})")
                return verdict
                
            except (json.JSONDecodeError, ValidationError, ValueError) as e:
                logger.warning(
                    f"Attempt {attempt + 1}: Failed to parse/validate verdict response: {e}"
                )
                if attempt == self.MAX_RETRIES - 1:
                    logger.error(
                        f"Max retries exhausted. Returning UNSURE fallback."
                    )
                    return FinalVerdict(
                        verdict="UNSURE",
                        confidence=0.0,
                        evidence=[
                            "Model could not generate reliable verdict.",
                            f"Evidence collected: {len(state.evidence)} items",
                            "Marking as UNSURE for human review due to model failures."
                        ]
                    )
                    
            except Exception as e:
                logger.error(f"Attempt {attempt + 1}: Unexpected error: {e}")
                if attempt == self.MAX_RETRIES - 1:
                    return FinalVerdict(
                        verdict="UNSURE",
                        confidence=0.0,
                        evidence=["Unexpected error during verdict generation. Requires manual review."]
                    )

        # Fallback (should not reach here)
        return FinalVerdict(
            verdict="UNSURE",
            confidence=0.0,
            evidence=["Unknown error. Requires human review."]
        )

    # Tool helper methods (simple wrappers around tools.py functions)

    def _compare_fields(self, case1: Dict, case2: Dict) -> Dict:
        """Compare CRM fields (account, email, priority, channel, status)."""
        return compare_fields(case1, case2)

    def _fuzzy_score(self, case1: Dict, case2: Dict) -> Dict:
        """Calculate fuzzy similarity scores for account, subject, description."""
        return fuzzy_score(case1, case2)

    def _timeline_gap(self, case1: Dict, case2: Dict) -> Dict:
        """Calculate time gap between case creation timestamps."""
        return timeline_gap(case1, case2)

    def _find_other_cases(self, case1: Dict, case2: Dict) -> Dict:
        """Find other cases for the same account or contact email."""
        return {
            "case1_similar": find_other_cases(case1, self.df),
            "case2_similar": find_other_cases(case2, self.df),
        }
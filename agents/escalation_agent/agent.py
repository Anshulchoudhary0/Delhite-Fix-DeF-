# pyrefly: ignore [missing-import]
from google.adk.agents import Agent
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
import os

load_dotenv()

class EscalationResult(BaseModel):
    message: str = Field(
        description="The drafted message. If days_pending > 4, this is a polite but firm follow-up status update request. If days_pending <= 4, this is a simple tracking instruction message."
    )
    escalation_step: str = Field(
        description="The next escalation action step recommended (e.g. 'Local Ward Councillor', 'CPGRAMS portal', or 'None')."
    )

root_agent = Agent(
    name="escalation_agent",
    model="gemini-3.1-flash-lite",
    instruction="""You are an escalation coordinator for Delhi civic complaints.
Given:
1. The original complaint text.
2. The number of days passed since filing with no resolution (days_pending).

Your job:
- If days_pending is greater than 4: Draft a polite but firm follow-up message asking for a status update, and suggest the next escalation step (either contacting the local ward councillor or filing through the Delhi government's CPGRAMS public grievance portal).
- If days_pending is 4 or less: Return a simple "complaint filed, here's how to track it" message and suggest tracking info.

Provide your response in the structured output conforming to the schema.
""",
    output_schema=EscalationResult
)

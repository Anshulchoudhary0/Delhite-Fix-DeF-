"""
Escalation Agent Module for DelhiFix.

Single Responsibility:
  Coordinates follow-up and escalation recommendations for grievances that 
  have been filed but remain unresolved after a certain number of days.

Inputs:
  - Original complaint text.
  - Days pending since initial submission.

Outputs:
  - EscalationResult: A structured Pydantic model containing:
    * message: Follow-up email draft or tracking advice.
    * escalation_step: Next recommended step (e.g. Ward Councillor, CPGRAMS, or None).

DelhiFix Pipeline Context:
  Bypasses the normal routing and drafting loop when the resident reports 
  an existing unresolved complaint (indicated by the presence of days_pending).
"""

# pyrefly: ignore [missing-import]
from google.adk.agents import Agent
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
import os

load_dotenv()

# Design Decision:
# Standardizes the escalation output. The recommended escalation step is displayed 
# as metadata status, and the message is converted into a mailto draft by the coordinator.
class EscalationResult(BaseModel):
    message: str = Field(
        description="The drafted message. If days_pending > 4, this is a polite but firm follow-up status update request. If days_pending <= 4, this is a simple tracking instruction message."
    )
    escalation_step: str = Field(
        description="The next escalation action step recommended (e.g. 'Local Ward Councillor', 'CPGRAMS portal', or 'None')."
    )

# Design Decision - Decoupling Escalation Logic:
# Decoupling escalation rules from the main drafting agent ensures that formatting templates 
# do not bleed into the follow-up logic.
# Behavior:
# The agent enforces a threshold-based behavior:
#   1. days_pending > 4: Generates a firm follow-up letter asking for a status report 
#      and routes to Local Councillor or CPGRAMS.
#   2. days_pending <= 4: Declines to escalate (advising wait/track), keeping the system
#      from spamming agencies prematurely.
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

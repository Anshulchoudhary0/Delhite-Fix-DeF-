# pyrefly: ignore [missing-import]
from google.adk.agents import Agent
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
import os

load_dotenv()

class VerificationResult(BaseModel):
    verified: bool = Field(
        description="True if the complaint passes both checks (is specific enough to act on and routed to the correct department), False otherwise."
    )
    feedback: str = Field(
        description="Specific feedback on what to fix if verification fails (e.g. missing location details, wrong department mapping). Empty string if verified."
    )
    draft_text: str = Field(
        description="The validated drafted complaint. If verified is True, this must match the original draft exactly."
    )

root_agent = Agent(
    name="verifier_agent",
    model="gemini-3.1-flash-lite",
    instruction="""You are a complaint verification agent for Delhi civic issues.
Given:
1. The drafted complaint text.
2. The classifier's category and department decision.

Verify two things:
1. Is the complaint specific enough to act on? It must contain a clear location and clear description of the issue (not vague).
2. Is the department routing correct for the category? Refer to these rules:
   - MCD handles potholes, garbage/sanitation, streetlight, illegal construction, stray animal.
   - Delhi Jal Board handles water leakage.
   - BSES/Tata Power handles electricity/power issues.
   - DPCC handles pollution/air quality issues (open burning of garbage, industrial smoke, construction dust without water spraying, visible vehicle smoke).

If either check fails, mark verified as False and write constructive feedback in 'feedback' indicating what needs to be fixed.
If both checks pass, mark verified as True, leave 'feedback' empty, and output the original drafted complaint in 'draft_text' unchanged.
""",
    output_schema=VerificationResult
)

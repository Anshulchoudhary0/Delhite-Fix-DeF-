"""
Verifier Agent Module for DelhiFix.

Single Responsibility:
  Inspects drafted civic grievances to ensure they contain actionable details 
  (specific location and details) and are routed to the correct government department.

Inputs:
  - Drafted complaint text.
  - Classifier decisions (Category, Department).

Outputs:
  - VerificationResult: A structured Pydantic model containing:
    * verified: Boolean (True if the draft passes all checks).
    * feedback: Constructive correction comments if verification fails.
    * draft_text: The validated draft (matching original draft if verified is True).

DelhiFix Pipeline Context:
  Acts as the quality check gate immediately following the Drafting Agent. 
  If verification fails, its generated feedback fuels a self-correction loop 
  for a redraft pass.
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
# The structured Pydantic output lets the coordinator programmaticly decide 
# whether to proceed with the draft or route it back to the drafting agent with the 
# feedback field populated.
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

# Design Decision - Generator-Critic Pattern:
# Splitting drafting and verification into separate agents enforces a "critic" model that 
# keeps the drafting model accountable.
# Behavior:
# The verifier checks two aspects:
#   1. Specificity: Ensures location and issue details are present.
#   2. Routing Alignment: Enforces strict department mapping rules (MCD vs DJB vs BSES vs DPCC).
# If either check fails, verified is set to False and actionable guidance is returned in 'feedback'.
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

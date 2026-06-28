"""
Duplicate Check Agent Module for DelhiFix.

Single Responsibility:
  Checks if a newly reported civic issue has already been recently filed at 
  the same location to prevent redundant, spam, or duplicate entries.

Inputs:
  - Resident's new complaint report (description and location).
  - List of active reports recently logged (locations and categories).

Outputs:
  - DuplicateCheckResult: A structured Pydantic model containing:
    * is_duplicate: Boolean (True if the new complaint matches an active one).
    * reason: One-line explanation suggesting the user check status instead of refiling.

DelhiFix Pipeline Context:
  Executes in parallel with the Classifier Agent on the New Complaint Path. 
  If it flags the input as a duplicate, the Coordinator halts drafting immediately.
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
# Returning a typed model ensures consistency. If a duplicate is detected, 
# the returned reason is formatted and displayed directly to the resident in the UI.
class DuplicateCheckResult(BaseModel):
    is_duplicate: bool = Field(
        description="True if the new complaint matches an existing active complaint in location and category, False otherwise."
    )
    reason: str = Field(
        description="A one-line reason. If duplicate, suggest checking the existing complaint status instead of filing a new one."
    )

# Design Decision - Concurrency Isolation:
# Isolating duplicate checking into a separate agent lets the coordinator execute this check 
# concurrently with classification, saving API turnaround time.
# Behavior:
# The agent checks for semantic overlapping in location descriptions (e.g. Rohini Sector 15 vsRohini Sector 15 Near Metro) 
# and matching categories. It behaves defensively: if the location or category overlaps significantly,
# it marks is_duplicate as True to avoid spamming government portals.
root_agent = Agent(
    name="duplicate_check_agent",
    model="gemini-3.1-flash-lite",
    instruction="""You are a duplicate complaint detector for Delhi civic issues.
Given:
1. The resident's new complaint report (description and location).
2. A short list of recently logged active reports from this session (including location and category).

Determine if the new report is a duplicate of any existing logged report. If it matches the category and general location (same street, neighborhood, or sector), mark is_duplicate as True and suggest they check the status of the existing one. Otherwise, mark is_duplicate as False. Always provide a clear, one-line reasoning.
""",
    output_schema=DuplicateCheckResult
)

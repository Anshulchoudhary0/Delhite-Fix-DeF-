# pyrefly: ignore [missing-import]
from google.adk.agents import Agent
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
import os

load_dotenv()

class DuplicateCheckResult(BaseModel):
    is_duplicate: bool = Field(
        description="True if the new complaint matches an existing active complaint in location and category, False otherwise."
    )
    reason: str = Field(
        description="A one-line reason. If duplicate, suggest checking the existing complaint status instead of filing a new one."
    )

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

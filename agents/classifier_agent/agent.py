# pyrefly: ignore [missing-import]
from google.adk.agents import Agent
# pyrefly: ignore [missing-import]
from google.adk.skills import load_skill_from_dir
# pyrefly: ignore [missing-import]
from google.adk.tools.skill_toolset import SkillToolset
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field
from typing import Literal
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
import os

load_dotenv()

# Structured output schema
class CivicIssueClassification(BaseModel):
    category: Literal["pothole", "garbage/sanitation", "streetlight", "water leakage", "illegal construction", "stray animal", "pollution/air quality", "other"] = Field(
        description="The category of the civic issue."
    )
    department: str = Field(
        description="The department responsible. Refer to the 'civic-routing-skill' skill for mapping."
    )
    urgency: Literal["high", "medium", "low"] = Field(
        description="Urgency level. Set to high if it poses a safety hazard, medium, or low."
    )
    reasoning: str = Field(
        description="A one-line explanation of the classification reasoning."
    )

# Load the civic routing skill
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
skill_path = os.path.join(project_root, "skills", "civic-routing-skill")
civic_skill = load_skill_from_dir(skill_path)
skill_toolset = SkillToolset(skills=[civic_skill])

root_agent = Agent(
    name="classifier_agent",
    model="gemini-3.1-flash-lite",
    instruction="""You are a civic issue classifier for Delhi. Given a resident's description of an issue (and optionally a photo), analyze and classify it.
    
IMPORTANT: You have access to a skill toolset. You MUST call the tool to load the 'civic-routing-skill' skill to retrieve the correct department mapping rules and check which category belongs to which department before answering.

You MUST call the 'set_model_response' tool to return the final structured classification. Do not reply with conversational text or explanation outside of the 'set_model_response' tool call.

Rules:
1. Category must be one of: pothole, garbage/sanitation, streetlight, water leakage, illegal construction, stray animal, pollution/air quality, other.
2. Determine the correct department and urgency based on the rules in the 'civic-routing-skill' skill.
3. Always provide a clear, one-line reasoning.
""",
    output_schema=CivicIssueClassification,
    tools=[skill_toolset]
)

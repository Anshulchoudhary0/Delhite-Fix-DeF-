"""
Classifier Agent Module for DelhiFix.

Single Responsibility:
  Analyzes resident civic grievance reports to determine the issue category,
  assign the responsible government department, and gauge urgency.

Inputs:
  - Unstructured resident complaint description.

Outputs:
  - CivicIssueClassification: A structured Pydantic model containing:
    * category: Literal category (pothole, garbage, streetlight, water leak, etc.).
    * department: Responsible municipal department (MCD, DJB, DPCC, BSES, etc.).
    * urgency: Urgency rating (high, medium, low).
    * reasoning: One-line explanation of the classification rationale.

DelhiFix Pipeline Context:
  Invoked in the New Complaint Path. Runs concurrently with the Duplicate Check Agent. 
  Its classification outputs are used by the Drafting Agent (to format the letter) 
  and the Verifier Agent (to check routing accuracy).
"""

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

# Design Decision:
# Enforcing a strict schema with Pydantic validation ensures that the classification 
# outputs adhere to strict categories. The literal constraints block invalid categories, 
# preventing subsequent drafting logic from breaking.
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

# Design Decision - Skill Toolset Isolation:
# Rather than hardcoding the mapping between categories, urgency rules, and Delhi government 
# departments in the agent instruction prompt, we load these rules dynamically from the 
# 'civic-routing-skill' folder. This ensures the agent is modular and permits updating the 
# routing/ownership matrix without modifying the underlying Python code or agent prompting.
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
skill_path = os.path.join(project_root, "skills", "civic-routing-skill")
civic_skill = load_skill_from_dir(skill_path)
skill_toolset = SkillToolset(skills=[civic_skill])

# Behavior:
# When executing, the agent queries the toolset to match the issue description against 
# the department criteria, returns the structured schema using the set_model_response tool, 
# and avoids raw conversational text.
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

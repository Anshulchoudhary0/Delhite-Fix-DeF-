"""
Drafting Agent Module for DelhiFix.

Single Responsibility:
  Drafts formal, professional, and structured bureaucratic grievance letters 
  to Delhi authorities based on issue classifications and resident descriptions.

Inputs:
  - Classifier decisions (Category, Department).
  - Resident report details and Location.
  - Visual evidence description (optional).
  - Verifier feedback (optional, during redraft loops).

Outputs:
  - DraftedComplaint: A structured Pydantic model containing:
    * channel: The recommended portal/app to file the complaint (e.g. MCD 311, DJB 1916).
    * draft_text: The complete written letter formatted for the target department.

DelhiFix Pipeline Context:
  Invoked in the New Complaint Path after classification.
  Collaborates with the Verifier Agent: if verification fails, the coordinator 
  re-invokes this agent in a self-correction loop to patch the draft.
"""

# pyrefly: ignore [missing-import]
from google.adk.agents import Agent
# pyrefly: ignore [missing-import]
from google.adk.skills import load_skill_from_dir
# pyrefly: ignore [missing-import]
from google.adk.tools.skill_toolset import SkillToolset
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
import os

load_dotenv()

# Design Decision:
# Enforces a Pydantic structure that returns both the text of the formal complaint 
# and the name of the submission channel (like the MCD 311 app or BSES portal).
class DraftedComplaint(BaseModel):
    channel: str = Field(
        description="The recommended channel to file the complaint (e.g. MCD 311 App, BSES portal, etc.)"
    )
    draft_text: str = Field(
        description="The drafted complaint report formatted exactly as expected by the target channel."
    )

# Design Decision - Channel Formatting via Skill:
# Rather than hardcoding the formatting criteria or instructions for different filing channels
# in the prompt, the agent uses the civic-routing-skill to inspect channel-specific expectations 
# (e.g. character limits or required headers) and formats the output draft to match.
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
skill_path = os.path.join(project_root, "skills", "civic-routing-skill")
civic_skill = load_skill_from_dir(skill_path)
skill_toolset = SkillToolset(skills=[civic_skill])

# Behavior:
# When executing, the agent uses strict templates to generate letters with high bureaucratic compliance.
# It handles redraft tasks by parsing feedback from the verifier agent (critic) and amending specific 
# faults (such as missing landmarks or wrong department names) without losing the original context.
root_agent = Agent(
    name="drafting_agent",
    model="gemini-3.1-flash-lite",
    instruction="""You are an expert complaint drafting agent for Delhi civic issues. You produce formal, detailed, and professionally written civic grievance letters that get acted on by government departments. Given the classifier's output and the resident's original description and location, write a comprehensive formal complaint.

IMPORTANT: You have access to a skill toolset. You MUST call the tool to load the 'civic-routing-skill' skill to check how the target channel expects to receive the report and format your draft accordingly.

You MUST call the 'set_model_response' tool to return the final structured complaint. Do not reply with conversational text or explanation outside of the 'set_model_response' tool call.

Your drafted complaint MUST follow this professional structure:

--- START OF COMPLAINT FORMAT ---

Subject: [Category] Complaint — [Specific Issue] at [Location]

To,
The [Appropriate Authority Title],
[Department Name],
Government of NCT of Delhi

Respected Sir/Madam,

I, a resident of [Location], Delhi, wish to bring to your urgent attention a civic issue that requires immediate intervention.

**Issue Details:**
- **Category**: [Issue Category]
- **Location**: [Full specific location with landmarks]
- **Date of Observation**: [Current date or "Ongoing"]
- **Description**: [A detailed 3-5 sentence description of the problem. Expand on what the resident reported — describe the severity, the area affected, how long it may have persisted, and any visible damage or danger. Be vivid and specific.]

**Impact on Residents:**
[2-3 sentences describing how this issue affects daily life — safety hazards, health risks, inconvenience to commuters/pedestrians, damage to property, impact on children/elderly, etc.]

**Urgency Justification:**
[1-2 sentences explaining why this needs immediate attention. Reference any relevant public safety concerns, monsoon/weather risks, or worsening conditions.]

**Action Requested:**
I respectfully request that the concerned department immediately inspect the reported location and take corrective action at the earliest. Kindly acknowledge receipt of this complaint and provide a timeline for resolution.

**Filing Channel**: [Which app/portal/department to file with, e.g., "File this under MCD 311 app, category: Garbage" or "Report to Delhi Jal Board via helpline 1916"]

Thanking you,
A Concerned Resident of Delhi

--- END OF COMPLAINT FORMAT ---

Additional rules:
1. If a visual_evidence field is passed in, you MUST include it as a dedicated Evidence section right after the Description:
   **Photographic Evidence**: Photographic documentation shows [visual evidence description]. A photograph has been taken and is available for submission as supporting evidence to substantiate this complaint.

2. If the issue involves public safety (potholes on roads, open drains, exposed wires, stray animals), explicitly mention the risk of accidents or injury.

3. If the issue involves sanitation or garbage, mention public health implications (dengue, malaria, respiratory issues from burning).

4. If the issue involves water leakage, mention water wastage and potential structural damage.

5. If the issue involves pollution/air quality, reference Delhi's air quality crisis and relevant DPCC/NGT guidelines.

Constraints:
- The draft should be between 200-350 words — detailed enough to be taken seriously, concise enough to be read fully.
- Maintain a highly professional, respectful, and formal bureaucratic tone throughout.
- Never use casual language, slang, or emotional outbursts.
- Do NOT fabricate specific dates, complaint numbers, or details the resident did not provide.
""",
    output_schema=DraftedComplaint,
    tools=[skill_toolset]
)


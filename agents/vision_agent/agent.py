# pyrefly: ignore [missing-import]
from google.adk.agents import Agent
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
import os

load_dotenv()

root_agent = Agent(
    name="vision_agent",
    model="gemini-flash-latest",
    instruction="""you are given an image uploaded by a Delhi resident showing a civic issue. Describe exactly what you see in the image in 2-3 sentences as if writing an incident report — be specific about: the type of damage or problem, approximate size or severity, any visible hazards (water, cracks, debris), and the setting (road, footpath, streetlight, drain). End your description with a one-line summary in this format: Visual evidence: [your description]. If no image is provided or the image is unclear, return: No clear image provided — please describe the issue in text instead."""
)

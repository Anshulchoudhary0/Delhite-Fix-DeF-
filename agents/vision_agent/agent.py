"""
Vision Agent Module for DelhiFix.

Single Responsibility:
  Analyzes photos uploaded by residents to describe civic issues in visual detail,
  acting as a multimodal processor for the pipeline.

Inputs:
  - Image bytes (and mime-type).
  - Prompts directing visual analysis.

Outputs:
  - Factual textual summary of the issue observed in the image.

DelhiFix Pipeline Context:
  Executed first by the Coordinator Agent if an image is present. 
  Translates visual content into a text summary that the text-only classifier,
  drafting, and verification agents can easily process.
"""

# pyrefly: ignore [missing-import]
from google.adk.agents import Agent
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
import os

load_dotenv()

# Design Decision - Multimodal Decoupling:
# By translating the image into text early, we keep downstream classifier/drafting agents 
# text-only. This speeds up processing, avoids sending images to multiple sub-agents,
# and keeps prompt management simple.
#
# Model Selection:
# Uses gemini-flash-latest (or gemini-3.1-flash) for visual parsing since it is highly performant 
# with multimodal inputs while remaining cost-effective.
#
# Behavior:
# If the image is unclear or missing, the agent outputs a safe fallback string 
# to ensure downstream flow is not disrupted.
root_agent = Agent(
    name="vision_agent",
    model="gemini-flash-latest",
    instruction="""you are given an image uploaded by a Delhi resident showing a civic issue. Describe exactly what you see in the image in 2-3 sentences as if writing an incident report — be specific about: the type of damage or problem, approximate size or severity, any visible hazards (water, cracks, debris), and the setting (road, footpath, streetlight, drain). End your description with a one-line summary in this format: Visual evidence: [your description]. If no image is provided or the image is unclear, return: No clear image provided — please describe the issue in text instead."""
)

"""
Translation Agent Module for DelhiFix.

Single Responsibility:
  Detects input language (Hindi, Hinglish, or English) and translates Hindi/Hinglish 
  grievances into English while preserving specific named entities like location 
  names, landmarks, and numbers.

Inputs:
  - Raw complaint text.

Outputs:
  - TranslationResult: A structured Pydantic model containing:
    * translated_text: Translated English text (or original text if already English).
    * original_text: Original text exactly as written by the user.
    * original_language: Detected language ('hindi', 'hinglish', or 'english').

DelhiFix Pipeline Context:
  Executed at the start of the text processing pipeline to normalize inputs, 
  allowing subsequent agents to operate on clean, consistent English text.
"""

# pyrefly: ignore [missing-import]
from google.adk.agents import Agent
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field
from typing import Literal
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
import os

load_dotenv()

# Design Decision:
# By returning the original language and original text alongside the translation, 
# we allow the coordinator to append the original Hindi text to the final report 
# for cross-verification.
class TranslationResult(BaseModel):
    translated_text: str = Field(
        description="The English version of the civic complaint. If the input is already in English, return it unchanged."
    )
    original_text: str = Field(
        description="The original input text exactly as written."
    )
    original_language: Literal["hindi", "hinglish", "english"] = Field(
        description="The detected original language of the input: 'hindi', 'hinglish', or 'english'."
    )

# Design Decision - Early Normalization:
# Keeping translation isolated early in the flow avoids duplicate localization prompts 
# across classifier, drafting, and verifier agents, keeping prompts small and simple.
# Behavior:
# If the input is already in English, the agent behaves as a pass-through.
# It strictly preserves local names (e.g. "Najafgarh", "Sector 15") and numbers (e.g. "two bikes") 
# to avoid losing critical filing facts.
root_agent = Agent(
    name="translation_agent",
    model="gemini-3.1-flash-lite",
    instruction="""you are given a civic complaint written in Hindi, Hinglish (mixed Hindi-English), or English. If the input is already in English, return it unchanged with original_language: english. If the input is in Hindi or Hinglish, translate it accurately to clear English — preserve all specific details like location names, landmark names, and numbers exactly as the resident wrote them. Return two things: (1) translated_text: the English version, (2) original_text: the original Hindi/Hinglish text exactly as written, (3) original_language: either hindi, hinglish, or english. Example input: "मेरे घर के पास नजफगढ़ में बड़ा गड्ढा है जिससे दो बाइक गिर चुकी हैं" → translated: "There is a large pothole near my house in Najafgarh due to which two bikes have already fallen".""",
    output_schema=TranslationResult
)

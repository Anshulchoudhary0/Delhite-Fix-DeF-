# pyrefly: ignore [missing-import]
from google.adk.agents import Agent
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field
from typing import Literal
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
import os

load_dotenv()

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

root_agent = Agent(
    name="translation_agent",
    model="gemini-3.1-flash-lite",
    instruction="""you are given a civic complaint written in Hindi, Hinglish (mixed Hindi-English), or English. If the input is already in English, return it unchanged with original_language: english. If the input is in Hindi or Hinglish, translate it accurately to clear English — preserve all specific details like location names, landmark names, and numbers exactly as the resident wrote them. Return two things: (1) translated_text: the English version, (2) original_text: the original Hindi/Hinglish text exactly as written, (3) original_language: either hindi, hinglish, or english. Example input: "मेरे घर के पास नजफगढ़ में बड़ा गड्ढा है जिससे दो बाइक गिर चुकी हैं" → translated: "There is a large pothole near my house in Najafgarh due to which two bikes have already fallen".""",
    output_schema=TranslationResult
)

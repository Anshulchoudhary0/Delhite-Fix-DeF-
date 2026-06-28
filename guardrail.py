"""
Guardrail Module for DelhiFix.

Single Responsibility:
  Screens incoming resident reports for inappropriate language, profanity, 
  harassment, or off-topic spam (e.g. programming queries, cooking recipes) 
  before inputs reach the multi-agent drafting pipeline.

Inputs:
  - Raw complaint text.

Outputs:
  - (is_valid, rejection_reason): Tuple[bool, str].
    * is_valid: True if input is appropriate and civic-related.
    * rejection_reason: Descriptive rejection string on failure.

DelhiFix Pipeline Context:
  Acts as a gatekeeper executed by the Coordinator Agent early in the execution flow.
  Blocks execution if the report fails validation, returning an early rejection.
"""

import os
import json
import asyncio
# pyrefly: ignore [missing-import]
from google import genai
# pyrefly: ignore [missing-import]
from google.genai import types

_client = None

# Design Decision - Lazy Initialization:
# Clients are instantiated only on demand to prevent import-time exceptions 
# if environmental API keys are missing or invalid during startup.
def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            _client = genai.Client(api_key=api_key)
    return _client

async def validate_report(text: str) -> tuple[bool, str]:
    """
    Validates a resident's report.
    Returns (is_valid, rejection_reason).
    """
    if not text or not isinstance(text, str):
        return False, "The report content is empty."
        
    cleaned_text = text.strip()
    if len(cleaned_text) < 4:
        return False, "The report content is too short (must be at least 4 characters)."
        
    # Design Decision - Hybrid Validation:
    # First, run a static check for common profanities. This executes with zero latency
    # and protects the API from unnecessary calls.
    import string
    profanities = {"fuck", "shit", "bitch", "asshole", "idiot", "bastard", "abuse"}
    words = [w.strip(string.punctuation) for w in cleaned_text.lower().split()]
    if any(w in profanities for w in words):
        return False, "The report contains inappropriate language or profanity."
        
    client = _get_client()
    if not client:
        # Failsafe Decision:
        # If the client cannot be initialized (e.g., missing API key), we fail-open 
        # to prevent locking out all user interaction.
        return True, ""
        
    try:
        # Design Decision - LLM Content Moderation:
        # The prompt checks for two criteria: (1) offensive content and (2) civic relevance.
        # This keeps user submissions aligned with municipal infrastructure and public safety, 
        # filtering out general chit-chat, programming questions, or recipes.
        prompt = f"""
        Analyze this user input text:
        "{cleaned_text}"
        
        Determine two things:
        1. Does it contain abusive language, profanity, harassment, or offensive content?
        2. Is it clearly spam or completely unrelated to civic issues (such as municipal problems, road conditions, sanitation, electricity, water, public safety, illegal construction, stray animals, general public grievances, etc.)? General conversation, tech questions, cooking recipes, buying/selling products, etc. are unrelated.
        
        Respond with a JSON object in this format:
        {{
            "is_appropriate": true/false,
            "is_civic_related": true/false,
            "reason": "a very brief reason if invalid, otherwise empty"
        }}
        """
        response = await client.aio.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        res_data = json.loads(response.text.strip())
        is_appropriate = res_data.get("is_appropriate", True)
        is_civic_related = res_data.get("is_civic_related", True)
        
        if not is_appropriate:
            return False, "The report contains inappropriate language, profanity, or abuse."
            
        if not is_civic_related:
            return False, "The input does not appear to be related to civic issues or grievances."
            
        return True, ""
        
    except Exception as e:
        # Failsafe Decision:
        # If the API call fails (network timeout, rate-limits, etc.), we print a warning 
        # and allow the report to pass (failsafe open) to avoid locking users out.
        print(f"Warning in guardrail validation API call: {e}")
        return True, ""

import os
import json
import asyncio
# pyrefly: ignore [missing-import]
from google import genai
# pyrefly: ignore [missing-import]
from google.genai import types

_client = None

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
        
    # Static check for common offensive words
    import string
    profanities = {"fuck", "shit", "bitch", "asshole", "idiot", "bastard", "abuse"}
    words = [w.strip(string.punctuation) for w in cleaned_text.lower().split()]
    if any(w in profanities for w in words):
        return False, "The report contains inappropriate language or profanity."
        
    client = _get_client()
    if not client:
        # If no API key, fallback to allowing the report to proceed to avoid blocking
        return True, ""
        
    try:
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
        # If the API call fails (e.g. rate limit), allow it to pass to the next stage rather than blocking
        print(f"Warning in guardrail validation API call: {e}")
        return True, ""

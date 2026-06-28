# ==============================================================================
# SECURITY & PRIVACY NOTICE:
# - Resident phone numbers and exact addresses are not written to any
#   persistent database. They are processed entirely in memory.
# - The Gemini API key is loaded only from environment variables.
# ==============================================================================

import sys
import os
import asyncio

# Ensure the root of the project is in sys.path so ADK loader can import 'agents'
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# pyrefly: ignore [missing-import]
from google.adk.agents import BaseAgent
# pyrefly: ignore [missing-import]
from google.adk.events import Event
# pyrefly: ignore [missing-import]
from google.adk.runners import Runner
# pyrefly: ignore [missing-import]
from google.adk.sessions import InMemorySessionService
# pyrefly: ignore [missing-import]
from google.adk.utils.content_utils import extract_text_from_content
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field
from typing import Optional, Any, AsyncGenerator
import json
import urllib.parse
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
from typing_extensions import override

# Load environment variables
load_dotenv()

# Import sub-agents
from agents.duplicate_check_agent.agent import root_agent as duplicate_check_agent
from agents.classifier_agent.agent import root_agent as classifier_agent
from agents.drafting_agent.agent import root_agent as drafting_agent
from agents.verifier_agent.agent import root_agent as verifier_agent
from agents.escalation_agent.agent import root_agent as escalation_agent
from agents.vision_agent.agent import root_agent as vision_agent
from agents.translation_agent.agent import root_agent as translation_agent
from agents.awareness_agent.agent import root_agent as awareness_agent


class CoordinatorInput(BaseModel):
    issue_description: Optional[str] = Field(None, description="Description of the new civic issue.")
    location: Optional[str] = Field(None, description="Location of the new civic issue.")
    recent_reports: Optional[list[dict]] = Field(default_factory=list, description="Recently logged reports to check for duplicates.")
    complaint_text: Optional[str] = Field(None, description="Original complaint text if requesting escalation.")
    days_pending: Optional[int] = Field(None, description="Days pending since filing for escalation check.")
    image_path: Optional[str] = Field(None, description="Path to the uploaded image file.")


class CoordinatorResult(BaseModel):
    category: str = Field(description="The category of the complaint (e.g. pothole, water leakage, etc.).")
    department: str = Field(description="The department responsible for resolving the complaint.")
    verified_complaint_text: str = Field(description="The final verified civic complaint text.")
    mailto_link: str = Field(description="A pre-filled mailto link in the format: mailto:?subject=...&body=...")
    is_duplicate: bool = Field(description="True if the complaint was identified as a duplicate.")
    status_message: str = Field(description="A status message indicating the outcome of the flow.")
    original_text: Optional[str] = Field(None, description="The original Hindi/Hinglish text if translation was performed.")
    visual_evidence: Optional[str] = Field(None, description="The visual evidence description from the vision agent if a photo was provided.")
    original_language: str = Field("english", description="The original language of the input (e.g. 'hindi', 'hinglish', or 'english').")
    urgency: str = Field("unknown", description="The urgency level of the complaint.")
    environmental_impact: Optional[str] = Field(None, description="The environmental awareness impact message.")


agent_runners = {}
shared_session_service = InMemorySessionService()

async def run_agent_helper(agent, prompt_or_parts: Any) -> Any:
    """Helper to run an agent and return its structured output model or raw text with automatic retries on rate limits."""
    # pyrefly: ignore [missing-import]
    from google.genai import types
    import asyncio
    import json
    
    max_retries = 5
    retry_delay = 2.0
    
    for attempt in range(max_retries):
        try:
            if agent.name not in agent_runners:
                agent_runners[agent.name] = Runner(
                    agent=agent,
                    app_name=agent.name,
                    session_service=shared_session_service
                )
            runner = agent_runners[agent.name]
            
            # Create session
            session = await runner.session_service.create_session(app_name=agent.name, user_id="coordinator")
            
            if isinstance(prompt_or_parts, list):
                parts = prompt_or_parts
            else:
                parts = [types.Part.from_text(text=prompt_or_parts)]
                
            # Run agent
            events = runner.run_async(
                session_id=session.id,
                user_id=session.user_id,
                new_message=types.Content(
                    role="user",
                    parts=parts
                )
            )
            
            final_text = None
            async for event in events:
                if event.content and event.content.role == "model" and event.content.parts:
                    text = "".join(p.text for p in event.content.parts if p.text and not p.thought)
                    if text.strip():
                        final_text = text
                    
            if final_text:
                cleaned_text = final_text.strip()
                if cleaned_text.startswith("```json"):
                    cleaned_text = cleaned_text[7:]
                if cleaned_text.startswith("```"):
                    cleaned_text = cleaned_text[3:]
                if cleaned_text.endswith("```"):
                    cleaned_text = cleaned_text[:-3]
                cleaned_text = cleaned_text.strip()
                
                if not agent.output_schema:
                    return cleaned_text
                
                parsed_data = json.loads(cleaned_text)
                return agent.output_schema.model_validate(parsed_data)
            
            break
        except Exception as e:
            err_str = str(e)
            if any(x in err_str for x in ["429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE"]):
                print(f"Temporary error (429/503/RESOURCE_EXHAUSTED/UNAVAILABLE) calling agent {agent.name}. Retrying in {retry_delay:.1f}s... (Attempt {attempt+1}/{max_retries})")
                await asyncio.sleep(retry_delay)
                retry_delay *= 1.5
                continue
            else:
                print(f"Error calling agent {agent.name}: {e}")
                raise e
            
    return None


class CoordinatorAgent(BaseAgent):
    model: str = Field("gemini-3.1-flash-lite", description="Model name.")

    @override
    async def _run_async_impl(self, ctx: Any) -> AsyncGenerator[Event, None]:
        # Parse inputs (could be JSON or plain text)
        issue_description = None
        location = None
        recent_reports = []
        complaint_text = None
        days_pending = None
        image_path = None

        # Get raw input text from user content or session events
        raw_text = ""
        if ctx.user_content:
            raw_text = extract_text_from_content(ctx.user_content)
        if not raw_text:
            events = ctx._get_events(current_invocation=True)
            for event in reversed(events):
                if event.author == "user" and event.content:
                    raw_text = extract_text_from_content(event.content)
                    if raw_text:
                        break
        
        # Try parsing raw_text as JSON
        if raw_text:
            raw_text = raw_text.strip()
            try:
                # Strip markdown code blocks if present
                cleaned = raw_text
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                if cleaned.startswith("```"):
                    cleaned = cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()
                
                data = json.loads(cleaned)
                if isinstance(data, dict):
                    issue_description = data.get("issue_description")
                    location = data.get("location")
                    recent_reports = data.get("recent_reports", [])
                    complaint_text = data.get("complaint_text")
                    days_pending = data.get("days_pending")
                    image_path = data.get("image_path")
            except Exception:
                # Treat entire raw_text as issue_description
                issue_description = raw_text

        # Variables to store extra outputs
        original_text = None
        visual_evidence = None
        original_language = "english"

        # Check if there is an image in user content or recent events
        image_bytes = None
        mime_type = None
        
        if ctx.user_content and ctx.user_content.parts:
            for part in ctx.user_content.parts:
                if part.inline_data and part.inline_data.mime_type and part.inline_data.mime_type.startswith("image/"):
                    image_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type
                    break
        
        if not image_bytes:
            events = ctx._get_events(current_invocation=True)
            for event in reversed(events):
                if event.author == "user" and event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.inline_data and part.inline_data.mime_type and part.inline_data.mime_type.startswith("image/"):
                            image_bytes = part.inline_data.data
                            mime_type = part.inline_data.mime_type
                            break
                    if image_bytes:
                        break
                        
        if not image_bytes and image_path and os.path.exists(image_path):
            try:
                with open(image_path, "rb") as f:
                    image_bytes = f.read()
                import mimetypes
                mime_type, _ = mimetypes.guess_type(image_path)
                if not mime_type:
                    mime_type = "image/jpeg"
            except Exception as e:
                print(f"Error reading image file from path {image_path}: {e}")

        # Check if the input text itself is a simulated photo input
        simulated_photo = False
        text_for_sim = complaint_text if days_pending is not None else issue_description
        if text_for_sim and text_for_sim.strip().startswith("[PHOTO INPUT]:"):
            simulated_photo = True
            visual_evidence = text_for_sim.strip()[14:].strip()
            # Use that description as the complaint text going into the rest of the pipeline
            if days_pending is not None:
                complaint_text = visual_evidence
            else:
                issue_description = visual_evidence

        # (1) If image is uploaded, call vision_agent first
        if image_bytes and not simulated_photo:
            # pyrefly: ignore [missing-import]
            from google.genai import types
            parts = [
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type or "image/jpeg"),
                types.Part.from_text(text="Describe the civic issue shown in this image.")
            ]
            vision_desc = await run_agent_helper(vision_agent, parts)
            if vision_desc:
                visual_evidence = vision_desc.strip()
                # Use description as the complaint text going into the rest of the pipeline
                if days_pending is not None:
                    complaint_text = visual_evidence
                else:
                    issue_description = visual_evidence

        # Determine the text content to validate
        text_to_validate = complaint_text if days_pending is not None else issue_description

        # (2) If contains Hindi/Hinglish (Devanagari \u0900–\u097F or Hinglish keywords), call translation_agent first
        import re
        is_hindi_hinglish = False
        if text_to_validate:
            if re.search(r"[\u0900-\u097F]", text_to_validate):
                is_hindi_hinglish = True
            else:
                # Check for common Hinglish/Hindi words written in Latin script
                hinglish_pattern = r"\b(mein|mere|ghar|ke|paas|hai|bhai|bahut|bada|badi|se|ko|ne|ki|ka|kar|par|hi|bhi|aur|yaar|ye|wo|isse|gaddha|gaddhe|paani|sarak|sadak|nagar|nuksan|samasya)\b"
                if re.search(hinglish_pattern, text_to_validate.lower()):
                    is_hindi_hinglish = True

        if is_hindi_hinglish:
            original_text = text_to_validate
            translation_result = await run_agent_helper(translation_agent, text_to_validate)
            if translation_result and hasattr(translation_result, "translated_text"):
                translated = translation_result.translated_text
                original_language = getattr(translation_result, "original_language", "hindi")
                if days_pending is not None:
                    complaint_text = translated
                else:
                    issue_description = translated
                text_to_validate = translated
        
        # Run Guardrail validation
        from guardrail import validate_report
        is_valid, rejection_reason = await validate_report(text_to_validate or "")
        
        if not is_valid:
            polite_rejection = f"We are sorry, but your input was rejected: {rejection_reason} Please submit a valid Delhi civic grievance."
            result_dict = {
                "category": "unknown",
                "department": "unknown",
                "verified_complaint_text": "",
                "mailto_link": "",
                "is_duplicate": False,
                "status_message": polite_rejection,
                "original_text": original_text,
                "visual_evidence": visual_evidence,
                "original_language": original_language,
                "urgency": "unknown",
                "environmental_impact": None
            }
            
            markdown_content = f"**[INPUT REJECTED]**\n\n{polite_rejection}"
            
            # pyrefly: ignore [missing-import]
            from google.genai import types
            content_part = types.Part.from_text(text=markdown_content)
            model_content = types.Content(role="model", parts=[content_part])
            
            validated_output = self._validate_output_data(result_dict)
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                branch=ctx.branch,
                content=model_content,
                output=validated_output
            )
            return

        # Determine path (Escalation vs New Complaint)
        subject = ""
        body_text = ""
        gmail_link = ""
        to_email = "complaints@delhi.gov.in"
        if days_pending is not None:
            # Escalation Path
            escalation_prompt = f"""
            Original Complaint: {complaint_text or ''}
            Days Pending: {days_pending}
            """
            escalation_result = await run_agent_helper(escalation_agent, escalation_prompt)
            
            if escalation_result is None:
                msg = f"Your complaint has been pending for {days_pending} days. Please follow up with your local ward office."
                step = "Ward Councillor"
            else:
                msg = getattr(escalation_result, "message", "")
                step = getattr(escalation_result, "escalation_step", "")
            
            if visual_evidence:
                msg += f"\n\nVisual evidence: {visual_evidence}"

            subject = f"Civic Grievance Follow-up (Pending {days_pending} days)"
            body_text = msg
            # Ensure carriage returns (\r\n) are used for mailto body newlines
            msg_crlf = msg.replace("\r\n", "\n").replace("\n", "\r\n")
            mailto_link = f"mailto:{to_email}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(msg_crlf)}"
            gmail_link = f"https://mail.google.com/mail/?view=cm&fs=1&to={to_email}&su={urllib.parse.quote(subject)}&body={urllib.parse.quote(msg_crlf)}"
            
            result_dict = {
                "category": "unknown",
                "department": "unknown",
                "verified_complaint_text": msg,
                "mailto_link": mailto_link,
                "is_duplicate": False,
                "status_message": f"Escalation follow-up drafted. Recommended step: {step}",
                "original_text": original_text,
                "visual_evidence": visual_evidence,
                "original_language": original_language,
                "urgency": "unknown",
                "environmental_impact": None
            }
        else:
            # New Complaint Path
            # 1. Check for duplicates and 2. Classify (in parallel if checking duplicates)
            is_duplicate = False
            duplicate_reason = ""
            classifier_result = None

            if recent_reports:
                duplicate_check_prompt = f"""
                New Complaint Description: {issue_description or ''}
                Location: {location or ''}
                Recent Reports: {recent_reports}
                """
                classifier_prompt = f"Resident Report: {issue_description or ''}"
                
                # Run duplicate check and classification in parallel
                duplicate_task = run_agent_helper(duplicate_check_agent, duplicate_check_prompt)
                classifier_task = run_agent_helper(classifier_agent, classifier_prompt)
                
                duplicate_result, classifier_result = await asyncio.gather(duplicate_task, classifier_task)
                
                if duplicate_result is not None:
                    is_duplicate = getattr(duplicate_result, "is_duplicate", False)
                    duplicate_reason = getattr(duplicate_result, "reason", "")
            else:
                # If no recent reports, skip duplicate check completely and run classifier
                classifier_prompt = f"Resident Report: {issue_description or ''}"
                classifier_result = await run_agent_helper(classifier_agent, classifier_prompt)
                
            if is_duplicate:
                result_dict = {
                    "category": "unknown",
                    "department": "unknown",
                    "verified_complaint_text": "",
                    "mailto_link": "",
                    "is_duplicate": True,
                    "status_message": duplicate_reason or "Duplicate complaint detected.",
                    "original_text": original_text,
                    "visual_evidence": visual_evidence,
                    "original_language": original_language,
                    "urgency": "unknown",
                    "environmental_impact": None
                }
            else:
                category = "other"
                department = "unknown"
                urgency = "medium"
                if classifier_result is not None:
                    category = getattr(classifier_result, "category", "other")
                    department = getattr(classifier_result, "department", "unknown")
                    urgency = getattr(classifier_result, "urgency", "medium")
                    
                # 3. Draft
                draft_prompt = f"""
                Classifier Output: Category={category}, Department={department}
                Resident Report: {issue_description or ''}
                Location: {location or ''}
                Visual Evidence: {visual_evidence or ''}
                """
                draft_result = await run_agent_helper(drafting_agent, draft_prompt)
                
                draft_text = ""
                if draft_result is not None:
                    draft_text = getattr(draft_result, "draft_text", "")
                    
                # 4. Verify & Self-Correct
                verify_prompt = f"""
                Drafted Complaint: {draft_text}
                Classifier Decision: Category={category}, Department={department}
                """
                verify_result = await run_agent_helper(verifier_agent, verify_prompt)
                
                verified = False
                feedback = ""
                if verify_result is not None:
                    verified = getattr(verify_result, "verified", False)
                    feedback = getattr(verify_result, "feedback", "")
                    
                if not verified:
                    # Redraft once
                    redraft_prompt = f"""
                    Classifier Output: Category={category}, Department={department}
                    Resident Report: {issue_description or ''}
                    Location: {location or ''}
                    Previous Draft: {draft_text}
                    Feedback to Fix: {feedback}
                    Visual Evidence: {visual_evidence or ''}
                    """
                    redraft_result = await run_agent_helper(drafting_agent, redraft_prompt)
                    
                    if redraft_result is not None:
                        draft_text = getattr(redraft_result, "draft_text", "")
                        
                    # Verify final draft
                    final_verify_prompt = f"""
                    Drafted Complaint: {draft_text}
                    Classifier Decision: Category={category}, Department={department}
                    """
                    final_verify_result = await run_agent_helper(verifier_agent, final_verify_prompt)
                    if final_verify_result is not None:
                        verified = getattr(final_verify_result, "verified", False)
                
                if visual_evidence:
                    draft_text += f"\n\nVisual evidence: {visual_evidence}"

                if category.lower() == "other":
                    subj_category = f"{department} Issue" if department.lower() != "unknown" else "Civic Grievance"
                else:
                    subj_category = category.title()
                subject = f"Civic Complaint: {subj_category} at {location or 'Delhi'}"
                # Ensure carriage returns (\r\n) are used for mailto body newlines
                draft_text_crlf = draft_text.replace("\r\n", "\n").replace("\n", "\r\n")
                mailto_link = f"mailto:{to_email}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(draft_text_crlf)}"
                body_text = draft_text
                gmail_link = f"https://mail.google.com/mail/?view=cm&fs=1&to={to_email}&su={urllib.parse.quote(subject)}&body={urllib.parse.quote(draft_text_crlf)}"
                
                status_msg = "Complaint verified and drafted successfully."
                if not verified:
                    status_msg = "Complaint drafted but failed final verification. Please review before filing."
                    
                # Call Awareness Agent for all drafted complaints (not just verified ones)
                environmental_impact = None
                awareness_prompt = f"Category: {category}\nDepartment: {department}\nLocation: {location or 'Delhi'}\nComplaint Summary: {issue_description or ''}"
                awareness_result = await run_agent_helper(awareness_agent, awareness_prompt)
                if awareness_result is not None:
                    environmental_impact = getattr(awareness_result, "environmental_impact", None)
                    
                result_dict = {
                    "category": category,
                    "department": department,
                    "verified_complaint_text": draft_text,
                    "mailto_link": mailto_link,
                    "is_duplicate": False,
                    "status_message": status_msg,
                    "original_text": original_text,
                    "visual_evidence": visual_evidence,
                    "original_language": original_language,
                    "urgency": urgency,
                    "environmental_impact": environmental_impact
                }

        # Format output as a beautiful, premium markdown message instead of messy raw JSON
        # Note: Avoid using non-ASCII emojis to prevent encoding crashes on Windows console outputs.
        if result_dict.get("is_duplicate"):
            markdown_content = f"[DUPLICATE DETECTED] **Duplicate Complaint Detected**\n\n{result_dict['status_message']}"
        elif days_pending is not None:
            # Escalation path
            markdown_content = f"""### [Escalation Grievance Drafted]
 
* **Status**: {result_dict['status_message']}
 
---
 
{result_dict['verified_complaint_text']}
 
---
 
[Send via Gmail (Web)]({gmail_link})
 
**Or copy the details manually:**
* **Subject**: `{subject}`
* **Body**:
```text
{body_text}
```
"""
        else:
            # New Complaint Path
            status_prefix = "[VERIFIED]" if result_dict["status_message"] == "Complaint verified and drafted successfully." else "[WARNING]"
            markdown_content = f"""### [Civic Complaint Drafted]
 
* **Category**: {result_dict['category'].title()}
* **Department**: {result_dict['department']}
* **Status**: {status_prefix} {result_dict['status_message']}
 
---
 
{result_dict['verified_complaint_text']}
 
---
 
[Send via Gmail (Web)]({gmail_link})"""
            if result_dict.get("environmental_impact"):
                markdown_content += f"""
 
---
 
### 🌿 Your Environmental Impact
 
{result_dict['environmental_impact']}"""
                
            markdown_content += f"""
 
---
 
**Or copy the details manually:**
* **Subject**: `{subject}`
* **Body**:
```text
{body_text}
```
"""
        
        if original_language in ("hindi", "hinglish") and original_text:
            markdown_content += f"\n\nOriginal complaint (Hindi): {original_text}"

        # pyrefly: ignore [missing-import]
        from google.genai import types
        content_part = types.Part.from_text(text=markdown_content)
        model_content = types.Content(role="model", parts=[content_part])
        
        # Validate output schema
        validated_output = self._validate_output_data(result_dict)
        
        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            content=model_content,
            output=validated_output
        )

    @override
    async def _run_live_impl(self, ctx: Any) -> AsyncGenerator[Event, None]:
        raise NotImplementedError("Live mode is not supported for coordinator_agent.")
        yield


# Instantiate the root agent for discovery
root_agent = CoordinatorAgent(
    name="coordinator_agent",
    model="gemini-3.1-flash-lite",
    input_schema=CoordinatorInput,
    output_schema=CoordinatorResult,
)

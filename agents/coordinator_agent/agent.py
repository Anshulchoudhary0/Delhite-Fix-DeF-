# ==============================================================================
# SECURITY & PRIVACY NOTICE:
# - Resident phone numbers and exact addresses are not written to any
#   persistent database. They are processed entirely in memory.
# - The Gemini API key is loaded only from environment variables.
# ==============================================================================

"""
Coordinator Agent Module for DelhiFix.

Single Responsibility:
  Coordinates the multi-agent execution pipeline for processing and submitting 
  Delhi civic grievances. It acts as the central router (orchestrator) and DAG 
  executor of the application.

Inputs:
  - CoordinatorInput: A Pydantic model containing:
    * issue_description: Description of the civic issue (optional).
    * location: Specific location/landmark in Delhi (optional).
    * recent_reports: List of recently logged complaints for duplicate checking (optional).
    * complaint_text: Original complaint text if requesting escalation (optional).
    * days_pending: Number of days pending since filing, indicating escalation flow (optional).
    * image_path: Local filepath of an uploaded image (optional).

Outputs:
  - CoordinatorResult: A Pydantic model containing:
    * category: The classified category of the grievance.
    * department: The responsible Delhi government department.
    * verified_complaint_text: The final, professionally written complaint letter.
    * mailto_link: Pre-filled mailto URL for email submission.
    * is_duplicate: Boolean indicating whether a duplicate complaint was found.
    * status_message: Friendly text describing the pipeline's outcome.
    * original_text: Original Hindi/Hinglish text if translation was performed.
    * visual_evidence: Extracted visual details from the vision agent.
    * original_language: Detected original language (hindi/hinglish/english).
    * urgency: Urgency classification level.
    * environmental_impact: Contextual educational text mapping the complaint to Delhi's environment.

DelhiFix Pipeline Context:
  This agent acts as the gateway/orchestrator of the multi-agent system.
  1. Multimodal Check: Calls Vision Agent if an image is provided.
  2. Language Check: Calls Translation Agent if Hindi/Hinglish is detected.
  3. Security & Quality Check: Invokes Guardrail validation on normalized input.
  4. Routing:
     - Escalation Path: Calls Escalation Agent.
     - New Complaint Path: Runs Duplicate Check Agent & Classifier Agent in parallel.
       * If duplicate: aborts early.
       * If not duplicate: calls Drafting Agent, Verifier Agent (self-correction loop), and Awareness Agent.
  5. Formatter: Compiles results, generates Gmail draft URLs, and yields structured output.
"""

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
    """
    Helper to execute a sub-agent.
    
    Design Decision:
      1. Modular Isolation: Downstream agents are executed using their own runner instances 
         and transient in-memory sessions to prevent cross-agent prompt pollution.
      2. Resilience: Implements exponential backoff retry logic for transient errors 
         (429, 503, RESOURCE_EXHAUSTED, UNAVAILABLE) to guarantee robust service 
         delivery under heavy loads.
      3. Strict Output Handling: Standardizes stripping markdown JSON fences before Pydantic parsing.
    
    Behavior:
      Re-raises fatal errors (like invalid configurations or authentication issues) to halt 
      the pipeline immediately, while retrying transient errors up to 5 times.
    """
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
        # Implementation: Initialize local variables to hold parsed inputs.
        issue_description = None
        location = None
        recent_reports = []
        complaint_text = None
        days_pending = None
        image_path = None

        # Implementation: Try to extract raw user text input from the incoming context, 
        # checking both the direct user_content and the historic session events.
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
        
        # Design & Behavior:
        # The Gradio UI serializes inputs as a JSON string and sends them in a single call.
        # If parsing succeeds, we unpack structured fields. If it fails, we assume
        # the entire raw text is the issue description (graceful fallback for CLI/direct execution).
        if raw_text:
            raw_text = raw_text.strip()
            try:
                # Strip markdown code blocks if present (common when LLMs draft input payloads)
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
                issue_description = raw_text

        # Variables to store extra outputs
        original_text = None
        visual_evidence = None
        original_language = "english"

        # Implementation & Design:
        # Multimodal extraction. Check if image bytes were passed inline in the content 
        # parts (standard ADK pattern) or if a filepath was provided in the JSON payload.
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

        # Design Decision - Visual Emulation:
        # For testing or headless runs, simulated image inputs can be passed as text prefixed with '[PHOTO INPUT]:'.
        # If detected, we unpack it as visual evidence and bypass the vision agent.
        simulated_photo = False
        text_for_sim = complaint_text if days_pending is not None else issue_description
        if text_for_sim and text_for_sim.strip().startswith("[PHOTO INPUT]:"):
            simulated_photo = True
            visual_evidence = text_for_sim.strip()[14:].strip()
            if days_pending is not None:
                complaint_text = visual_evidence
            else:
                issue_description = visual_evidence

        # Design Decision - Multimodal Decoupling:
        # We invoke the vision_agent first to translate raw image bytes into a descriptive textual summary.
        # This shields all subsequent text-based agents from needing multimodal inputs, making the pipeline
        # modular, cheaper, and faster since only one model call handles the image.
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
                if days_pending is not None:
                    complaint_text = visual_evidence
                else:
                    issue_description = visual_evidence

        # Determine the text content to validate
        text_to_validate = complaint_text if days_pending is not None else issue_description

        # Design Decision - Multilingual Input Management:
        # Civic reports in Delhi are frequently written in Hindi (Devanagari) or Hinglish (Hindi written in Latin script).
        # Normalizing the text to English early ensures that downstream agents (classifier, drafting, verifier) can 
        # focus purely on English structure, enhancing accuracy and reducing context token sizes.
        import re
        is_hindi_hinglish = False
        if text_to_validate:
            # Check for Devanagari range
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
        
        # Design Decision - Defensive Input Guardrails:
        # We run the input through guardrail.py to catch abuse, spam, and non-civic inputs (e.g. recipes, code).
        # This acts as a firewall, protecting the pipeline from executing expensive sub-agent calls on garbage input.
        # Behavior: If guardrail validation fails, we immediately short-circuit the execution, return a polite
        # rejection message in the output, and skip invoking any other agents.
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

        # Design Decision - Pipeline Branching:
        # The coordinator routes requests based on whether it is a tracking/follow-up request (Escalation Path)
        # or a brand new report (New Complaint Path).
        subject = ""
        body_text = ""
        gmail_link = ""
        to_email = "complaints@delhi.gov.in"
        if days_pending is not None:
            # ──────────────────────────────────────────────────────────
            # ESCALATION PATH
            # ──────────────────────────────────────────────────────────
            # Behavior: Invoked when the resident supplies a non-empty days_pending value.
            # Routing: Calls escalation_agent to draft follow-up correspondence and recommend
            # official follow-up bodies (like the local ward councillor or CPGRAMS).
            escalation_prompt = f"""
            Original Complaint: {complaint_text or ''}
            Days Pending: {days_pending}
            """
            escalation_result = await run_agent_helper(escalation_agent, escalation_prompt)
            
            # Implementation Fallback:
            # If the escalation agent fails, we fall back to a simple, safe default message 
            # to avoid throwing exceptions, recommending Councillor action as standard.
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
            # ──────────────────────────────────────────────────────────
            # NEW COMPLAINT PATH
            # ──────────────────────────────────────────────────────────
            # Routing: Involves checking for duplicates, classifying routing, drafting, and self-correcting.
            is_duplicate = False
            duplicate_reason = ""
            classifier_result = None

            # Design Decision - Concurrency Optimization:
            # If recent reports exist, we run duplicate check and classification in parallel using asyncio.gather.
            # This concurrency reduces latency significantly compared to sequential execution.
            if recent_reports:
                duplicate_check_prompt = f"""
                New Complaint Description: {issue_description or ''}
                Location: {location or ''}
                Recent Reports: {recent_reports}
                """
                classifier_prompt = f"Resident Report: {issue_description or ''}"
                
                duplicate_task = run_agent_helper(duplicate_check_agent, duplicate_check_prompt)
                classifier_task = run_agent_helper(classifier_agent, classifier_prompt)
                
                duplicate_result, classifier_result = await asyncio.gather(duplicate_task, classifier_task)
                
                if duplicate_result is not None:
                    is_duplicate = getattr(duplicate_result, "is_duplicate", False)
                    duplicate_reason = getattr(duplicate_result, "reason", "")
            else:
                # Behavior: Skip duplicate check entirely if there are no recent complaints passed.
                classifier_prompt = f"Resident Report: {issue_description or ''}"
                classifier_result = await run_agent_helper(classifier_agent, classifier_prompt)
                
            # Behavior: If duplicate detected, short-circuit the drafting pipeline and notify the resident.
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
                    
                # 3. Draft Complaint letter
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
                    
                # 4. Verify & Self-Correct (Critic-Generator Loop)
                # Design Decision:
                # Drafting quality varies. We feed the drafted output into verifier_agent.
                # If verifier fails verification, we perform one redraft cycle, feeding the verifier's 
                # constructive feedback back to the drafting_agent. This loop improves compliance 
                # with department routing and formatting guidelines without hardcoding validation logic.
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
                    # Redraft once with feedback
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
                        
                    # Verify final draft after redrafting
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
                draft_text_crlf = draft_text.replace("\r\n", "\n").replace("\n", "\r\n")
                mailto_link = f"mailto:{to_email}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(draft_text_crlf)}"
                body_text = draft_text
                gmail_link = f"https://mail.google.com/mail/?view=cm&fs=1&to={to_email}&su={urllib.parse.quote(subject)}&body={urllib.parse.quote(draft_text_crlf)}"
                
                status_msg = "Complaint verified and drafted successfully."
                if not verified:
                    status_msg = "Complaint drafted but failed final verification. Please review before filing."
                    
                # Design Decision - Environmental Education Integration:
                # We trigger the awareness_agent for all drafted complaints to output an educational
                # fact sheet linking the grievance to Delhi's air quality and waste management crisis.
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

        # Format output as a premium, highly formatted markdown report.
        # Implementation Detail: Avoid using emojis that might crash Windows command shell encoding.
        if result_dict.get("is_duplicate"):
            markdown_content = f"[DUPLICATE DETECTED] **Duplicate Complaint Detected**\n\n{result_dict['status_message']}"
        elif days_pending is not None:
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

        # Build output Events to communicate status back to the framework/runner
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

    @override
    async def _run_live_impl(self, ctx: Any) -> AsyncGenerator[Event, None]:
        # Design decision: The pipeline relies on sequential API calls and is not designed for streaming.
        raise NotImplementedError("Live mode is not supported for coordinator_agent.")
        yield


# Instantiate the root agent for discovery
root_agent = CoordinatorAgent(
    name="coordinator_agent",
    model="gemini-3.1-flash-lite",
    input_schema=CoordinatorInput,
    output_schema=CoordinatorResult,
)

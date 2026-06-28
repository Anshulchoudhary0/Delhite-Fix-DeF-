"""
DelhiFix Web Application Interface.

Single Responsibility:
  Serves as the user interface (UI) and frontend layer for the DelhiFix 
  civic grievance pipeline. It runs a Gradio server featuring premium custom CSS, 
  real-time AQI tracking, and distinct flows for filing new grievances vs escalating 
  unresolved issues.

Inputs:
  - Interactive user inputs: text descriptions, location, file uploads (photos), 
    and days pending.

Outputs:
  - Premium styled HTML pages, status badges, complaint draft boxes, 
    one-click Gmail web compose links, and AQI widgets.

DelhiFix Pipeline Context:
  Binds the Gradio UI directly to the multi-agent Coordinator Agent runner. 
  It handles session creation, serializes input parameters into JSON payloads 
  for the coordinator, and handles visual response rendering and error handling.
"""

import sys
import os
import json
import asyncio
from urllib.parse import parse_qs, quote
# pyrefly: ignore [missing-import]
import gradio as gr

# Design Decision - Gmail Redirect:
# Traditional mailto: links often open broken or unconfigured native desktop mail clients. 
# We convert mailto links to direct Gmail web compose URLs to guarantee a smooth, 
# zero-friction submission flow directly in the resident's web browser.
def convert_mailto_to_gmail(mailto_url):
    if not mailto_url or not mailto_url.startswith("mailto:"):
        return ""
    if "?" in mailto_url:
        parts = mailto_url.split("?", 1)
        to_email = parts[0].replace("mailto:", "")
        query_str = parts[1]
    else:
        to_email = mailto_url.replace("mailto:", "")
        query_str = ""
        
    query = parse_qs(query_str)
    subject = query.get("subject", [""])[0]
    body = query.get("body", [""])[0]
    
    gmail_url = f"https://mail.google.com/mail/?view=cm&fs=1&to={quote(to_email)}&su={quote(subject)}&body={quote(body)}"
    return gmail_url

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# pyrefly: ignore [missing-import]
from google.genai import types
# pyrefly: ignore [missing-import]
from google.adk.runners import Runner
# pyrefly: ignore [missing-import]
from google.adk.sessions import InMemorySessionService
from agents.coordinator_agent.agent import root_agent as coordinator_agent

# ── Premium CSS ──────────────────────────────────────────────────────────────

css = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

/* ── Reset & Globals ─────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; }

body {
    background: linear-gradient(145deg, #06091a 0%, #0c1333 35%, #15183d 65%, #0e0f26 100%) !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    min-height: 100vh;
}

.gradio-container {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    background: transparent !important;
    max-width: 1280px !important;
    margin: 0 auto !important;
    padding: 0 20px 40px !important;
    border: none !important;
    box-shadow: none !important;
}

/* ── Hero Header ─────────────────────────────────────── */
.hero-header {
    text-align: center;
    padding: 48px 20px 36px;
    position: relative;
}

.hero-header::before {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 600px;
    height: 600px;
    background: radial-gradient(circle, rgba(99, 102, 241, 0.08) 0%, transparent 70%);
    pointer-events: none;
    z-index: 0;
}

.hero-header h1 {
    font-size: 2.75rem !important;
    font-weight: 800 !important;
    letter-spacing: -0.03em !important;
    background: linear-gradient(135deg, #c7d2fe 0%, #818cf8 40%, #6366f1 70%, #a78bfa 100%) !important;
    -webkit-background-clip: text !important;
    -webkit-text-fill-color: transparent !important;
    background-clip: text !important;
    margin: 0 0 8px !important;
    position: relative;
    z-index: 1;
}

.hero-header p {
    font-size: 1.05rem !important;
    color: #94a3b8 !important;
    font-weight: 400 !important;
    margin: 0 !important;
    letter-spacing: 0.01em !important;
    position: relative;
    z-index: 1;
}

/* ── Glass Card ──────────────────────────────────────── */
.glass-card {
    background: rgba(15, 20, 50, 0.55) !important;
    backdrop-filter: blur(20px) !important;
    -webkit-backdrop-filter: blur(20px) !important;
    border: 1px solid rgba(99, 102, 241, 0.12) !important;
    border-radius: 20px !important;
    padding: 32px !important;
    box-shadow:
        0 4px 30px rgba(0, 0, 0, 0.3),
        inset 0 1px 0 rgba(255, 255, 255, 0.04) !important;
    transition: border-color 0.3s ease, box-shadow 0.3s ease !important;
}

.glass-card:hover {
    border-color: rgba(99, 102, 241, 0.22) !important;
    box-shadow:
        0 8px 40px rgba(0, 0, 0, 0.35),
        0 0 60px rgba(99, 102, 241, 0.04),
        inset 0 1px 0 rgba(255, 255, 255, 0.06) !important;
}

/* ── Section Headers ─────────────────────────────────── */
.section-title {
    font-size: 1.15rem !important;
    font-weight: 700 !important;
    color: #e2e8f0 !important;
    letter-spacing: -0.01em !important;
    margin-bottom: 4px !important;
}

.section-subtitle {
    font-size: 0.82rem !important;
    color: #64748b !important;
    font-weight: 400 !important;
    margin-bottom: 20px !important;
}

/* ── Labels ──────────────────────────────────────────── */
.gradio-container label, .gradio-container .label-wrap span {
    color: #cbd5e1 !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    letter-spacing: 0.01em !important;
}

/* ── Inputs & Textareas ──────────────────────────────── */
.gradio-container textarea,
.gradio-container input[type="text"],
.gradio-container input[type="number"] {
    background: rgba(15, 23, 42, 0.65) !important;
    border: 1px solid rgba(99, 102, 241, 0.15) !important;
    color: #f1f5f9 !important;
    border-radius: 12px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.92rem !important;
    padding: 12px 16px !important;
    transition: all 0.25s ease !important;
}

.gradio-container textarea:focus,
.gradio-container input[type="text"]:focus,
.gradio-container input[type="number"]:focus {
    border-color: #6366f1 !important;
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15), 0 0 20px rgba(99, 102, 241, 0.06) !important;
    outline: none !important;
}

.gradio-container textarea::placeholder,
.gradio-container input::placeholder {
    color: #475569 !important;
    font-weight: 400 !important;
}

/* ── Read-only Output Fields ─────────────────────────── */
.gradio-container textarea[disabled],
.gradio-container input[disabled] {
    background: rgba(10, 15, 35, 0.5) !important;
    border: 1px solid rgba(255, 255, 255, 0.06) !important;
    color: #e2e8f0 !important;
    cursor: default !important;
}

/* ── Buttons ─────────────────────────────────────────── */
.submit-btn {
    background: linear-gradient(135deg, #6366f1 0%, #4f46e5 50%, #4338ca 100%) !important;
    color: #ffffff !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    border: none !important;
    border-radius: 12px !important;
    padding: 14px 28px !important;
    cursor: pointer !important;
    position: relative !important;
    overflow: hidden !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    box-shadow:
        0 4px 15px rgba(99, 102, 241, 0.3),
        0 1px 3px rgba(0, 0, 0, 0.2) !important;
    letter-spacing: 0.02em !important;
}

.submit-btn:hover {
    transform: translateY(-2px) !important;
    box-shadow:
        0 8px 25px rgba(99, 102, 241, 0.45),
        0 2px 6px rgba(0, 0, 0, 0.25) !important;
}

.submit-btn:active {
    transform: translateY(0) !important;
}

.escalate-btn {
    background: linear-gradient(135deg, #f59e0b 0%, #d97706 50%, #b45309 100%) !important;
    color: #ffffff !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    border: none !important;
    border-radius: 12px !important;
    padding: 14px 28px !important;
    cursor: pointer !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    box-shadow:
        0 4px 15px rgba(245, 158, 11, 0.3),
        0 1px 3px rgba(0, 0, 0, 0.2) !important;
    letter-spacing: 0.02em !important;
}

.escalate-btn:hover {
    transform: translateY(-2px) !important;
    box-shadow:
        0 8px 25px rgba(245, 158, 11, 0.45),
        0 2px 6px rgba(0, 0, 0, 0.25) !important;
}

/* ── Status Badges ───────────────────────────────────── */
.badge-row .textbox {
    text-align: center !important;
}

.badge-row .textbox textarea {
    text-align: center !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    letter-spacing: 0.02em !important;
    border-radius: 10px !important;
    background: rgba(99, 102, 241, 0.08) !important;
    border: 1px solid rgba(99, 102, 241, 0.2) !important;
}

/* ── Tabs ────────────────────────────────────────────── */
.gradio-container .tabs {
    border: none !important;
    background: transparent !important;
}

.gradio-container .tab-nav {
    border: none !important;
    background: rgba(15, 20, 50, 0.4) !important;
    border-radius: 14px !important;
    padding: 4px !important;
    gap: 4px !important;
    margin-bottom: 24px !important;
    backdrop-filter: blur(10px) !important;
    border: 1px solid rgba(99, 102, 241, 0.08) !important;
}

.gradio-container .tab-nav button {
    background: transparent !important;
    border: none !important;
    color: #64748b !important;
    font-weight: 500 !important;
    font-size: 0.9rem !important;
    border-radius: 10px !important;
    padding: 10px 24px !important;
    transition: all 0.25s ease !important;
    letter-spacing: 0.01em !important;
}

.gradio-container .tab-nav button:hover {
    color: #c7d2fe !important;
    background: rgba(99, 102, 241, 0.06) !important;
}

.gradio-container .tab-nav button.selected {
    background: linear-gradient(135deg, rgba(99, 102, 241, 0.2) 0%, rgba(79, 70, 229, 0.15) 100%) !important;
    color: #c7d2fe !important;
    font-weight: 600 !important;
    box-shadow: 0 2px 10px rgba(99, 102, 241, 0.15) !important;
}

.gradio-container .tabitem {
    border: none !important;
    background: transparent !important;
    padding: 0 !important;
}

/* ── Image Upload ────────────────────────────────────── */
.gradio-container .image-container,
.gradio-container .upload-container {
    border: 2px dashed rgba(99, 102, 241, 0.2) !important;
    border-radius: 14px !important;
    background: rgba(15, 23, 42, 0.3) !important;
    transition: all 0.3s ease !important;
}

.gradio-container .image-container:hover,
.gradio-container .upload-container:hover {
    border-color: rgba(99, 102, 241, 0.4) !important;
    background: rgba(99, 102, 241, 0.04) !important;
}

/* ── Accordion ───────────────────────────────────────── */
.gradio-container .accordion {
    border: 1px solid rgba(245, 158, 11, 0.12) !important;
    border-radius: 16px !important;
    background: rgba(15, 20, 50, 0.35) !important;
    backdrop-filter: blur(10px) !important;
    overflow: hidden !important;
    margin-top: 8px !important;
}

.gradio-container .accordion > .label-wrap {
    background: rgba(245, 158, 11, 0.05) !important;
    padding: 16px 20px !important;
}

.gradio-container .accordion > .label-wrap span {
    color: #fbbf24 !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
}

/* ── Markdown Output ─────────────────────────────────── */
.gradio-container .markdown-text,
.gradio-container .prose {
    color: #cbd5e1 !important;
    font-family: 'Inter', sans-serif !important;
}

.gradio-container .prose h1,
.gradio-container .prose h2,
.gradio-container .prose h3 {
    color: #e2e8f0 !important;
    font-weight: 700 !important;
}

.gradio-container .prose a {
    color: #818cf8 !important;
}

.gradio-container .prose strong {
    color: #f1f5f9 !important;
}

/* ── Divider ─────────────────────────────────────────── */
.divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(99, 102, 241, 0.15), transparent) !important;
    margin: 28px 0 !important;
    border: none !important;
}

/* ── Footer ──────────────────────────────────────────── */
.footer-text {
    text-align: center;
    padding: 24px 0 8px;
}

.footer-text p {
    color: #334155 !important;
    font-size: 0.78rem !important;
    font-weight: 400 !important;
    letter-spacing: 0.03em !important;
}

/* ── Responsive ──────────────────────────────────────── */
@media (max-width: 768px) {
    .hero-header h1 {
        font-size: 2rem !important;
    }
    .glass-card {
        padding: 20px !important;
        border-radius: 16px !important;
    }
}

/* ── Scrollbar ───────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
    background: rgba(99, 102, 241, 0.2);
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
    background: rgba(99, 102, 241, 0.35);
}

/* ── Hide Gradio Footer ──────────────────────────────── */
footer { display: none !important; }
"""

# ── Initialize ADK Runner ───────────────────────────────────────────────────

# Design Decision - Session Isolation:
# We maintain an in-memory session service. Each user request triggers the creation of 
# a unique, isolated session context. This keeps user history private and prevents 
# multi-user requests from leaking information into other active sessions.
session_service = InMemorySessionService()
app_runner = Runner(
    agent=coordinator_agent,
    app_name=coordinator_agent.name,
    session_service=session_service
)

# Design Decision - Cross-Request State for Duplicate Protection:
# Although user sessions are isolated, we store successfully drafted reports in a global 
# in-memory list (active_reports) and feed them to duplicate check calls. This permits the 
# system to flag duplicate civic issues filed by different users during the application's runtime.
active_reports = []


# ── Handler Functions ────────────────────────────────────────────────────────

# Behavior:
# Validates parameters, initializes a secure ADK session, runs the coordinator agent 
# asynchronously, and processes final outputs to render the UI badges and Gmail compose link.
async def handle_new_complaint(issue_description, location, image_path):
    if not issue_description and not image_path:
        return "N/A", "N/A", "N/A", "Please provide a description or upload an image.", "", ""
    if not location or not location.strip():
        return "N/A", "N/A", "N/A", "Please specify the location of the civic issue (Location is required).", "", ""

    try:
        session = await app_runner.session_service.create_session(app_name=coordinator_agent.name, user_id="web_user")
        
        # Implementation: Pack input parameters into a structured JSON payload string 
        # that the coordinator agent expects.
        payload = {
            "issue_description": issue_description or "",
            "location": location or "Delhi",
            "recent_reports": active_reports,
            "image_path": image_path or None
        }
        
        payload_str = json.dumps(payload)
        events = app_runner.run_async(
            session_id=session.id,
            user_id=session.user_id,
            new_message=types.Content(
                role="user",
                parts=[types.Part.from_text(text=payload_str)]
            )
        )
        
        final_text = ""
        async for event in events:
            if event.content and event.content.role == "model" and event.content.parts:
                text = "".join(p.text for p in event.content.parts if p.text and not p.thought)
                if text.strip():
                    final_text = text
                    
        session_details = await app_runner.session_service.get_session(
            app_name=coordinator_agent.name,
            user_id="web_user",
            session_id=session.id
        )
        
        output = None
        for event in session_details.events:
            if event.author == coordinator_agent.name and event.output:
                output = event.output
                
        if output:
            category = output.get("category", "unknown").title()
            department = output.get("department", "unknown")
            urgency = output.get("urgency", "unknown").title()
            verified_complaint_text = output.get("verified_complaint_text", "")
            mailto_link = output.get("mailto_link", "")
            status_message = output.get("status_message", "")
            environmental_impact = output.get("environmental_impact", "") or ""
            
            if output.get("is_duplicate"):
                status_message = f"Duplicate complaint detected: {status_message}"
                return category, department, urgency, status_message, "", ""
                
            if not verified_complaint_text:
                return category, department, urgency, status_message, "", ""
            
            # Save the valid (non-duplicate) report so future requests can detect duplicate attempts
            active_reports.append({
                "category": output.get("category", "unknown"),
                "location": location or "Delhi"
            })
            
            mailto_html = ""
            if mailto_link:
                gmail_url = convert_mailto_to_gmail(mailto_link)
                mailto_html = f"""
                <div style='text-align: center; margin-top: 16px;'>
                    <a href="{gmail_url}" target="_blank" style="text-decoration: none; display: block;">
                        <div style="
                            background: linear-gradient(135deg, #10b981 0%, #059669 50%, #047857 100%);
                            color: white;
                            border: none;
                            padding: 16px 28px;
                            font-size: 15px;
                            font-weight: 600;
                            border-radius: 12px;
                            cursor: pointer;
                            box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3), 0 1px 3px rgba(0,0,0,0.2);
                            transition: all 0.3s ease;
                            text-align: center;
                            font-family: 'Inter', sans-serif;
                            letter-spacing: 0.02em;
                        ">
                            Send via Gmail
                        </div>
                    </a>
                </div>
                """
            return category, department, urgency, verified_complaint_text, mailto_html, environmental_impact
            
        else:
            return "N/A", "N/A", "N/A", "No structured output received. Response:\n" + final_text, "", ""
    except Exception as e:
        # Design Decision - UI Error Boundaries:
        # Rather than displaying technical raw traceback exceptions directly to the resident, 
        # we catch rate limits (429) and server overloads (503) and translate them into 
        # actionable instructions (e.g. "wait a few seconds and submit again").
        err_str = str(e)
        if "503" in err_str or "UNAVAILABLE" in err_str:
            user_msg = "The AI model is currently experiencing extremely high demand. Please wait a few seconds and try submitting again."
        elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            user_msg = "Rate limit exceeded. Please wait a moment and try again."
        else:
            user_msg = f"Failed to run pipeline: {e}"
        return "Error", "Error", "Error", user_msg, "", ""

async def handle_escalation(complaint_text, days_pending):
    if not complaint_text:
        return "Please provide the complaint text for escalation.", ""
        
    try:
        session = await app_runner.session_service.create_session(app_name=coordinator_agent.name, user_id="web_user")
        
        payload = {
            "complaint_text": complaint_text,
            "days_pending": int(days_pending)
        }
        
        payload_str = json.dumps(payload)
        events = app_runner.run_async(
            session_id=session.id,
            user_id=session.user_id,
            new_message=types.Content(
                role="user",
                parts=[types.Part.from_text(text=payload_str)]
            )
        )
        
        final_text = ""
        async for event in events:
            if event.content and event.content.role == "model" and event.content.parts:
                text = "".join(p.text for p in event.content.parts if p.text and not p.thought)
                if text.strip():
                    final_text = text
                    
        session_details = await app_runner.session_service.get_session(
            app_name=coordinator_agent.name,
            user_id="web_user",
            session_id=session.id
        )
        
        output = None
        for event in session_details.events:
            if event.author == coordinator_agent.name and event.output:
                output = event.output
                
        if output:
            verified_complaint_text = output.get("verified_complaint_text", "")
            mailto_link = output.get("mailto_link", "")
            status_message = output.get("status_message", "")
            
            mailto_html = ""
            if mailto_link:
                gmail_url = convert_mailto_to_gmail(mailto_link)
                mailto_html = f"""
                <div style='text-align: center; margin-top: 16px;'>
                    <a href="{gmail_url}" target="_blank" style="text-decoration: none; display: block;">
                        <div style="
                            background: linear-gradient(135deg, #f59e0b 0%, #d97706 50%, #b45309 100%);
                            color: white;
                            border: none;
                            padding: 16px 28px;
                            font-size: 15px;
                            font-weight: 600;
                            border-radius: 12px;
                            cursor: pointer;
                            box-shadow: 0 4px 15px rgba(245, 158, 11, 0.3), 0 1px 3px rgba(0,0,0,0.2);
                            transition: all 0.3s ease;
                            text-align: center;
                            font-family: 'Inter', sans-serif;
                            letter-spacing: 0.02em;
                        ">
                            Send Escalation via Gmail
                        </div>
                    </a>
                </div>
                """
            
            res_text = f"**Status**: {status_message}\n\n---\n\n{verified_complaint_text}"
            return res_text, mailto_html
        else:
            return "No structured output received. Response:\n" + final_text, ""
    except Exception as e:
        err_str = str(e)
        if "503" in err_str or "UNAVAILABLE" in err_str:
            user_msg = "The AI model is currently experiencing extremely high demand. Please wait a few seconds and try submitting again."
        elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            user_msg = "Rate limit exceeded. Please wait a moment and try again."
        else:
            user_msg = f"Failed to run escalation pipeline: {e}"
        return user_msg, ""


# ── Live AQI Widget ──────────────────────────────────────────────────────────

# Design Decision - Live Environmental Context:
# We fetch live air quality metrics for Delhi (using open Open-Meteo Air Quality API coordinates). 
# Showing real-time PM2.5 levels directly above the filing form emphasizes the civic and 
# environmental priority of filing grievances (like garbage burning or construction dust).
def get_current_delhi_aqi_html():
    import requests
    url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    params = {
        "latitude": 28.6139,
        "longitude": 77.2090,
        "current": "us_aqi,pm2_5,pm10",
        "timezone": "Asia/Kolkata"
    }
    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        current = data.get("current", {})
        aqi = current.get("us_aqi")
        pm25 = current.get("pm2_5")
        pm10 = current.get("pm10")
        
        if aqi is None:
            return "<div style='padding: 12px; background: rgba(255,255,255,0.03); border-radius: 12px; text-align: center; color: #64748b; font-family: Inter, sans-serif; font-size: 0.85rem;'>AQI data temporarily unavailable</div>"
            
        if aqi <= 50:
            status = "Good"
            color = "#10b981"
            bg = "rgba(16, 185, 129, 0.06)"
            border = "rgba(16, 185, 129, 0.15)"
        elif aqi <= 100:
            status = "Moderate"
            color = "#eab308"
            bg = "rgba(234, 179, 8, 0.06)"
            border = "rgba(234, 179, 8, 0.15)"
        elif aqi <= 150:
            status = "Unhealthy for Sensitive Groups"
            color = "#f97316"
            bg = "rgba(249, 115, 22, 0.06)"
            border = "rgba(249, 115, 22, 0.15)"
        elif aqi <= 200:
            status = "Unhealthy"
            color = "#ef4444"
            bg = "rgba(239, 68, 68, 0.06)"
            border = "rgba(239, 68, 68, 0.15)"
        elif aqi <= 300:
            status = "Very Unhealthy"
            color = "#a855f7"
            bg = "rgba(168, 85, 247, 0.06)"
            border = "rgba(168, 85, 247, 0.15)"
        else:
            status = "Hazardous"
            color = "#ef4444"
            bg = "rgba(239, 68, 68, 0.08)"
            border = "rgba(239, 68, 68, 0.2)"
            
        html = f"""
        <div style='
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px 24px;
            background: {bg};
            border: 1px solid {border};
            border-radius: 14px;
            font-family: Inter, -apple-system, sans-serif;
            max-width: 640px;
            margin: 0 auto 8px;
        '>
            <div style='display: flex; align-items: center; gap: 12px;'>
                <div style='
                    width: 38px; height: 38px;
                    background: {bg};
                    border: 1px solid {border};
                    border-radius: 10px;
                    display: flex; align-items: center; justify-content: center;
                    font-size: 18px;
                '>🌿</div>
                <div>
                    <div style='font-size: 11px; color: #64748b; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase;'>Live Delhi AQI</div>
                    <div style='font-size: 17px; font-weight: 700; color: #f1f5f9; margin-top: 2px;'>{aqi} &mdash; <span style='color: {color};'>{status}</span></div>
                </div>
            </div>
            <div style='display: flex; gap: 20px; text-align: right;'>
                <div>
                    <div style='font-size: 10px; color: #64748b; font-weight: 500; letter-spacing: 0.05em;'>PM2.5</div>
                    <div style='font-size: 15px; font-weight: 600; color: #e2e8f0; margin-top: 2px;'>{pm25}</div>
                </div>
                <div style='border-left: 1px solid rgba(255,255,255,0.08); padding-left: 20px;'>
                    <div style='font-size: 10px; color: #64748b; font-weight: 500; letter-spacing: 0.05em;'>PM10</div>
                    <div style='font-size: 15px; font-weight: 600; color: #e2e8f0; margin-top: 2px;'>{pm10}</div>
                </div>
            </div>
        </div>
        """
        return html
    except Exception as e:
        return f"<div style='padding: 12px; background: rgba(255,255,255,0.03); border-radius: 12px; text-align: center; color: #f87171; font-family: Inter, sans-serif; font-size: 0.85rem;'>Failed to fetch live AQI data</div>"


# ── Build Gradio UI ──────────────────────────────────────────────────────────

with gr.Blocks(title="DelhiteFix — Delhi Civic Complaint  ") as demo:
    
    # ── Hero Header ──
    gr.HTML("""<div class="hero-header">
            <h1>Delhite Fix (DeF)</h1>
            <p>Transforming Delhi's Public Civic Complaints Filing Into an AI-Powered Pollution Fighter with Multi-Agent AI</p>
        </div>""")
    
    # ── Live AQI Badge ──
    gr.HTML(value=get_current_delhi_aqi_html)
    
    # ── Tabbed Interface ──
    with gr.Tabs():
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        #  TAB 1 — File New Complaint
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        with gr.Tab("File New Complaint", id="new_complaint"):
            with gr.Row(equal_height=False):
                
                # ── Left Column: Input Form ──
                with gr.Column(scale=5, elem_classes=["glass-card"]):
                    gr.HTML("<div class='section-title'>Describe Your Issue you've encountered</div>")
                    issue_desc_input = gr.Textbox(
                        label="What is the civic issue?",
                        placeholder="e.g. मेरे घर के पास बड़ा गड्ढा है / There is a pothole near my house causing accidents",
                        lines=4,
                        max_lines=8
                    )
                    
                    location_input = gr.Textbox(
                        label="Location (Required)",
                        placeholder="e.g. Najafgarh Road, Rohini Sector 15, Near Metro Station",
                        info="Be as specific as possible — include sector, landmark, or road name"
                    )
                    
                    image_input = gr.Image(
                        label="Upload a Photo (Optional)",
                        type="filepath",
                        height=160
                    )
                    
                    submit_btn = gr.Button(
                        "Submit Complaint",
                        elem_classes=["submit-btn"],
                        size="lg"
                    )
                
                # ── Right Column: Output ──
                with gr.Column(scale=5, elem_classes=["glass-card"]):
                    gr.HTML("<div class='section-title'>Formal Grievance Output</div>")
                    with gr.Row(elem_classes=["badge-row"]):
                        category_output = gr.Textbox(
                            label="Category",
                            interactive=False,
                            scale=1
                        )
                        dept_output = gr.Textbox(
                            label="Department",
                            interactive=False,
                            scale=1
                        )
                        urgency_output = gr.Textbox(
                            label="Urgency",
                            interactive=False,
                            scale=1
                        )
                    
                    complaint_output = gr.Textbox(
                        label="Your Ready-to-File Complaint",
                        lines=10,
                        max_lines=18,
                        interactive=False
                    )
                    
                    mailto_output = gr.HTML(label="Email Action")
                    
                    env_impact_output = gr.Markdown(
                        value="",
                        label="Environmental Impact"
                    )
            
            submit_btn.click(
                fn=handle_new_complaint,
                inputs=[issue_desc_input, location_input, image_input],
                outputs=[category_output, dept_output, urgency_output, complaint_output, mailto_output, env_impact_output]
            )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        #  TAB 2 — Escalate Existing Complaint
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        with gr.Tab("Escalate Existing Complaint", id="escalation"):
            with gr.Row(equal_height=False):
                
                # ── Left Column: Escalation Input ──
                with gr.Column(scale=5, elem_classes=["glass-card"]):
                    gr.HTML("<div class='section-title'>Escalation Details</div>")
                    gr.HTML("<div class='section-subtitle'>If your complaint has been pending with no resolution, draft an official follow-up</div>")
                    
                    esc_text_input = gr.Textbox(
                        label="Original / Drafted Complaint Text",
                        placeholder="Paste the complaint you previously filed here...",
                        lines=6,
                        max_lines=12
                    )
                    
                    esc_days_input = gr.Number(
                        label="Days Pending",
                        value=5,
                        precision=0,
                        info="How many days since you originally filed the complaint?"
                    )
                    
                    esc_submit_btn = gr.Button(
                        "Submit Escalation",
                        elem_classes=["escalate-btn"],
                        size="lg"
                    )
                
                # ── Right Column: Escalation Output ──
                with gr.Column(scale=5, elem_classes=["glass-card"]):
                    gr.HTML("<div class='section-title'>Escalation Output</div>")
                    gr.HTML("<div class='section-subtitle'>Your drafted follow-up ready to send</div>")
                    
                    esc_complaint_output = gr.Textbox(
                        label="Your Ready-to-File Escalation",
                        lines=10,
                        max_lines=18,
                        interactive=False
                    )
                    
                    esc_mailto_output = gr.HTML(label="Email Action (Escalation)")
            
            esc_submit_btn.click(
                fn=handle_escalation,
                inputs=[esc_text_input, esc_days_input],
                outputs=[esc_complaint_output, esc_mailto_output]
            )
    
    # ── Footer ──
    gr.HTML("""
        <div class="footer-text">
            <p>DelhiteFix &mdash; Powered by Google ADK &amp; Gemini</p>
        </div>
    """)


if __name__ == "__main__":
    demo.launch(css=css, theme=gr.themes.Default())

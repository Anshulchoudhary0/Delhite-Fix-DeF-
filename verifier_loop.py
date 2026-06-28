import asyncio
import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# pyrefly: ignore [missing-import]
from google.adk.runners import Runner
# pyrefly: ignore [missing-import]
from google.adk.sessions import InMemorySessionService
from agents.drafting_agent.agent import root_agent as drafting_agent
from agents.verifier_agent.agent import root_agent as verifier_agent

async def run_agent_helper(agent, prompt: str):
    """Helper to run an agent and return its structured output model."""
    runner = Runner(
        agent=agent,
        app_name=agent.name,
        session_service=InMemorySessionService()
    )
    
    # Create session
    session = await runner.session_service.create_session(app_name=agent.name, user_id="default_user")
    
    # pyrefly: ignore [missing-import]
    from google.genai import types
    import json
    
    # Run agent
    events = runner.run_async(
        session_id=session.id,
        user_id=session.user_id,
        new_message=types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)]
        )
    )
    
    final_text = None
    async for event in events:
        if event.content and event.content.role == "model" and event.content.parts:
            text = "".join(p.text for p in event.content.parts if p.text and not p.thought)
            if text.strip():
                final_text = text
            
    if final_text:
        try:
            cleaned_text = final_text.strip()
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:]
            if cleaned_text.startswith("```"):
                cleaned_text = cleaned_text[3:]
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]
            cleaned_text = cleaned_text.strip()
            
            parsed_data = json.loads(cleaned_text)
            if agent.output_schema:
                return agent.output_schema.model_validate(parsed_data)
            return parsed_data
        except Exception as e:
            print(f"Error parsing response JSON for agent {agent.name}: {e}\nRaw text: {final_text}")
            
    return None

async def run_self_correction_loop(issue_description: str, location: str, category: str, department: str):
    print(f"--- STARTING COMPLAINT DRAFT FOR: {category} at {location} ---")
    
    # Step 1: Draft the complaint
    draft_prompt = f"""
    Classifier Output: Category={category}, Department={department}
    Resident Report: {issue_description}
    Location: {location}
    """
    draft_result = await run_agent_helper(drafting_agent, draft_prompt)
    if draft_result is None:
        print("Error: Drafting agent failed to return a valid structured result.")
        return None
    print(f"\n[Drafting Agent Output]\nChannel: {draft_result.channel}\nDraft:\n{draft_result.draft_text}\n")
    
    # Step 2: Verify the complaint
    verify_prompt = f"""
    Drafted Complaint: {draft_result.draft_text}
    Classifier Decision: Category={category}, Department={department}
    """
    verify_result = await run_agent_helper(verifier_agent, verify_prompt)
    if verify_result is None:
        print("Error: Verifier agent failed to return a valid structured result.")
        return None
    print(f"[Verifier Agent Output]\nVerified: {verify_result.verified}\nFeedback: {verify_result.feedback}\n")
    
    # Step 3: Self-correction (Redraft once if verification fails)
    if not verify_result.verified:
        print("--- VERIFICATION FAILED: REDRAFTING WITH FEEDBACK ---")
        redraft_prompt = f"""
        Classifier Output: Category={category}, Department={department}
        Resident Report: {issue_description}
        Location: {location}
        Previous Draft: {draft_result.draft_text}
        Feedback to Fix: {verify_result.feedback}
        """
        redraft_result = await run_agent_helper(drafting_agent, redraft_prompt)
        if redraft_result is None:
            print("Error: Drafting agent failed to return a valid structured result for redraft.")
            return None
        print(f"\n[Drafting Agent Redraft Output]\nChannel: {redraft_result.channel}\nDraft:\n{redraft_result.draft_text}\n")
        
        # Verify the redrafted complaint
        final_verify_prompt = f"""
        Drafted Complaint: {redraft_result.draft_text}
        Classifier Decision: Category={category}, Department={department}
        """
        final_verify_result = await run_agent_helper(verifier_agent, final_verify_prompt)
        if final_verify_result is None:
            print("Error: Verifier agent failed to return a valid structured result for final verification.")
            return None
        print(f"[Final Verifier Agent Output]\nVerified: {final_verify_result.verified}\nReason: {final_verify_result.feedback}\n")
        return redraft_result.draft_text
        
    print("--- VERIFICATION PASSED ---")
    return draft_result.draft_text

if __name__ == "__main__":
    async def run_tests():
        print("==================================================")
        print("TEST CASE 1: INCORRECT ROUTING (TRIGGERS REDRAFT)")
        print("==================================================")
        await run_self_correction_loop(
            issue_description="There is garbage piled up near the park entrance",
            location="Sector 4, Dwarka",
            category="garbage/sanitation",
            department="Delhi Jal Board"
        )
        
        print("\n\n==================================================")
        print("TEST CASE 2: CORRECT ROUTING (PASSES VERIFICATION)")
        print("==================================================")
        await run_self_correction_loop(
            issue_description="There is garbage piled up near the park entrance",
            location="Sector 4, Dwarka",
            category="garbage/sanitation",
            department="MCD"
        )

    asyncio.run(run_tests())

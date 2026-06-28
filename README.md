# DelhiteFix (DeF) — Transforming Delhi's Public Civic Complaints Filing Into an AI-Powered Pollution Fighter with Multi-Agent AI

DelhiteFix is an AI-powered civic complaint assistant for Delhi residents, built using Google's Agent Development Kit (ADK) and Gemini. It transforms informal, multi-lingual, and multi-modal resident inputs (English, Hindi, Hinglish, or photos) into structured, formally written, and correctly routed civic grievances.

---

## 🏗️ Multi-Agent Architecture

The solution uses an orchestrated multi-agent design consisting of a central coordinator and several specialized utility agents:

```mermaid
graph TD
    A([" 📥 User Input\n   Image · Hindi "]) --> B

    B["🧠 COORDINATOR AGENT\n Orchestrates the entire pipeline\n Manages · Formats Output"]

    B --> C["📷 Vision Agent\n Converts photo → descriptiom"]
    B --> D["🌐 Translation Agent\n "]

    C --> E
    D --> E

    E{"🛡️ GUARDRAIL\n Security Check"}

    E -->|"❌ Rejected"| F(["INPUT REJECTED\n Spam · Profanity · Off-topic\n Pipeline stops here"])
    E -->|"✅ Valid"| G
    E -->|"✅ Valid"| H

    subgraph PARALLEL["⚡ Parallel Execution — asyncio.gather"]
        G["🔍 Duplicate-Check Agent\n Already reported this session?"]
        H["🗂️ Classifier Agent\n Issue type + Department routing"]
    end

    G -->|"♻️ Duplicate found"| I(["STOP\n Check your existing complaint"])
    G --> J
    H --> J

    J["✍️ Drafting Agent\n Writes formal complaint\n Under 150 words · Professional tone"]

    J --> K{"✅ VERIFIER AGENT\n Specific enough?\n Department correct?"}

    K -->|"❌ Too vague\n or wrong dept"| L["🔄 Redraft\n One retry with feedback"]
    L --> K
    K -->|"✅ Verified"| M

    M["🌿 Awareness Agent\n Environmental impact education\n AQI context "]

    M --> N(["📧 FINAL OUTPUT\n Category · Department · Verified Complaint\n Pre-filled gmail link · Environmental Impact"])

    N -. "Days later — still unresolved" .-> O["⚠️ Escalation Agent\n  Ward Councillor · DPCC"]

    style A fill:#1e1e1e,stroke:#555555,color:#ffffff
    style B fill:#1a1040,stroke:#7c4fcf,color:#ffffff
    style C fill:#2a1f00,stroke:#d4920a,color:#ffffff
    style D fill:#0d1a2a,stroke:#3a8ef0,color:#ffffff
    style E fill:#1a1040,stroke:#7c4fcf,color:#ffffff
    style F fill:#2a120d,stroke:#e05a3a,color:#ffffff
    style G fill:#0d2a2a,stroke:#1fb8a0,color:#ffffff
    style H fill:#0d2a2a,stroke:#1fb8a0,color:#ffffff
    style I fill:#2a120d,stroke:#e05a3a,color:#ffffff
    style J fill:#0d2a2a,stroke:#1fb8a0,color:#ffffff
    style K fill:#1a1040,stroke:#7c4fcf,color:#ffffff
    style L fill:#1a1040,stroke:#7c4fcf,color:#ffffff
    style M fill:#1a2a00,stroke:#7fba00,color:#ffffff
    style N fill:#0d2a15,stroke:#1fad5a,color:#ffffff
    style O fill:#2a120d,stroke:#e05a3a,color:#ffffff
```
```

---

## 📁 Directory Structure

```text
delhitefix/
├── agents/
│   ├── classifier_agent/
│   │   └── agent.py
│   ├── coordinator_agent/
│   │   └── agent.py
│   ├── drafting_agent/
│   │   └── agent.py
│   ├── duplicate_check_agent/
│   │   └── agent.py
│   ├── escalation_agent/
│   │   └── agent.py
│   ├── translation_agent/
│   │   └── agent.py
│   ├── verifier_agent/
│   │   └── agent.py
│   ├── vision_agent/
│   │   └── agent.py
│   └── awareness_agent/
│       └── agent.py
├── skills/
│   └── civic-routing-skill/
│       └── SKILL.md
├── tests/
│   ├── run_scenario_tests.py
│   ├── test_agent.py
│   ├── test_guardrail.py
│   └── test_translation_vision.py
├── app.py                  # Gradio Web UI
├── guardrail.py            # Layered static & LLM validation
├── requirements.txt        # Project dependencies
└── README.md
```

---

## 🛠️ Setup Instructions

### 1. Create and Activate Virtual Environment
```bash
# Create venv
python -m venv .venv

# Activate (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Activate (Windows CMD)
.venv\Scripts\activate.bat

# Activate (Linux/macOS)
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Create a `.env` file in the root directory and add your Gemini API key:
```env
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
```

---

## 🚀 Running the App

### Web User Interface (Gradio)
Start the web interface using the local python executable:
```bash
python app.py
```
Open your browser and navigate to the address shown in the terminal (usually `http://127.0.0.1:7860`).

### Running the CLI Harness
To run predefined scenario workflows in the console:
```bash
python coordinator_loop.py
```

---

## 🧪 Running Tests

To verify individual parts of the pipeline, run the corresponding test script:
```bash
# Test agents configuration
python tests/test_agent.py

# Test guardrail rules
python tests/test_guardrail.py

# Test vision and translation functionality
python tests/test_translation_vision.py
```

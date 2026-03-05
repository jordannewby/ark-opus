# Ares Engine

Ares Engine is a sophisticated, fully autonomous, asynchronous **Quad-Stack SEO Generation Pipeline**. It orchestrates multiple LLMs (DeepSeek R1/V3, Gemini 2.5 Pro/Flash) and external APIs (Exa.ai, DataForSEO MCP) to dynamically build deeply researched, psychologically persuasive, and mathematically vetted 2,000+ word Markdown articles.

It features a zero-wait UI streaming intermediate execution steps via Server-Sent Events (SSE) and includes an interactive Human-in-the-Loop (HITL) self-learning feedback loop.

## 🚀 Quickstart Guide

Follow these steps to set up and run the Ares Engine on any device, ensuring all dependencies and API requirements are met without breakage.

### 1. Prerequisites
Ensure you have the following installed on your machine:
*   [Python 3.10+](https://www.python.org/downloads/)
*   [Git](https://git-scm.com/downloads)
*   [Node.js / npm](https://nodejs.org/en/) (required for the DataForSEO MCP server)

### 2. Clone the Repository
Open a terminal and clone the project to your local machine:
```bash
git clone https://github.com/jordannewby/ares-engine.git
cd ares-engine
```

### 3. Set Up the Virtual Environment
Create an isolated Python environment to prevent dependency conflicts:
```bash
python -m venv venv
```

**Activate the environment:**
*   **Windows:**
    ```powershell
    .\venv\Scripts\activate
    ```
*   **Mac/Linux:**
    ```bash
    source venv/bin/activate
    ```

### 4. Install Dependencies
Install all exact dependencies locked in the requirements file:
```bash
pip install -r requirements.txt
```

### 5. Transfer Your API Keys 🚨
Because `.env` files hold sensitive passwords and API keys, Git intentionally ignores them! You must create a new `.env` file in the root directory of your cloned project (`ares-engine/.env`) and populate it with your keys.

Your `.env` file must contain at minimum:
```env
# Google Gemini API Keys (Used for prose drafting and UI tasks)
GEMINI_API_KEY="your-gemini-api-key-here"
GEMINI_PSYCH_API_KEY="your-gemini-api-key-here"

# DeepSeek API Key (Used for DeepSeek-R1 reasoning and DeepSeek-V3 blueprinting)
DEEPSEEK_API_KEY="your-deepseek-api-key-here"

# Exa.ai API Key (Used for natural language neural search discovery)
EXA_API_KEY="your-exa-api-key-here"
```

### 6. Start the Engine
Run the FastAPI development server:
```bash
uvicorn app.main:app --reload
```

Then, open your web browser and navigate to the frontend console:
`http://127.0.0.1:8000/`

---

## 🏗️ Core Architecture Overview

The backend operates entirely inside FastAPI (`app/main.py`), utilizing the `/generate` endpoint to stream live updates back to the UI (`static/js/console.js`). The orchestration follows a strict chronological loop:

1.  **Phase 0: Briefing (`app/services/briefing_agent.py`)**
    *   Uses `gemini-2.5-flash` to ask 3 targeted clarifying questions before heavy research begins.
2.  **Phase 1: Data Logic (`app/services/research_service.py`)**
    *   DeepSeek-R1 (`deepseek-reasoner`) uses dynamic tool-decision logic to orchestrate the DataForSEO MCP and Exa.ai Neural Search via async requests, extracting the "Information Gap".
3.  **Phase 2: Strategic Logic (`app/services/psychology_agent.py`)**
    *   DeepSeek-V3 (`deepseek-chat`) acts as the "Persuasion Architect," injecting the Information Gap into the PAS framework to return a structured JSON psychological blueprint.
4.  **Phase 3: Prose Logic (`app/services/writer_service.py`)**
    *   `gemini-2.5-pro` violently enforces a strict "Anti-AI" system prompt (`writer.md`), banning fluff words and drafting the heavy-duty Markdown article.
5.  **Phase 6: Self-Correction Loop (`app/services/feedback_service.py`)**
    *   When a human edits the generated Markdown in the UI, `gemini-2.5-flash` semantically diffs the original against the edit to extract permanent `UserStyleRule` entities to Neon PostgreSQL (scoped by `profile_name`), ensuring the AI converges on the user's exact writing style over time.

## 💾 Notes on Portability

*   **Database:** The project uses a serverless Neon PostgreSQL cluster. Connection details are stored in `.env` (which is gitignored). Each new device needs its own `.env` file with the correct `DATABASE_URL` and API keys.
*   **Git Syncing:** When working across multiple devices, always remember to `git pull` before you start working and `git commit` / `git push` when you are done to ensure your codebase stays perfectly in sync.

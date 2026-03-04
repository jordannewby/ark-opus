import os

def create_llm_paste():
    output_file = "llm_paste.md"
    target_dirs = ["app", "static"]
    
    with open(output_file, 'w', encoding='utf-8') as outfile:
        outfile.write("# Ares Engine - Project Blueprint & Source Code\n\n")
        
        # Write Phase Summary
        outfile.write("## 1. Project Phase Summary\n\n")
        outfile.write("""### Recent Updates
- **UX Redesign**: Revamped `ares_console.html` and `console.js` with a Cyber-Glassmorphism aesthetic (Deep blacks, Tailwind text coloring, glowing accents, spatial layout).
- **Briefing Agent (Phase 0)**: Implemented `/clarify` endpoint and `BriefingAgent` using `gemini-2.5-flash` to ask 3 targeted questions before heavy research begins. Wired a custom frontend modal to intercept the "GENERATE" action and inject the user's answers into the deep reasoning R1 agent.
- **Frontend Niche Overhaul**: Replaced the static Niche `<select>` dropdown with a free-form `<input>` text field to fully unlock Exa.ai's natural language Neural Search capabilities.
- **Stable API Migration**: Migrated all backend generative pipelines off the unstable `gemini-3-flash-preview` models to production-grade endpoints (`gemini-2.5-pro` for deep drafting, `gemini-2.5-flash` for background/UI tasks).
- **Observability**: Added global `DEBUG_MODE` environment variable for detailed backend tracebacks and streamed frontend SSE logs of the agent's actions (e.g. MCP Subprocess initialization, tool decisions).
- **Database Schema**: Performed manual SQLite migration to add `original_ai_content` and `human_edited_content` columns, allowing the HITL self-correction loop to save properly.
- **Agentic Schema Abstraction & Tool Streaming**: Implemented a recursive `_strip_webhook_noise` filter in `ResearchAgent` to remove massive webhook payloads from the DataForSEO MCP schemas, resolving DeepSeek-R1 `JSONDecodeError`s. Refactored the `/generate` endpoint in `main.py` to stream exactly which DataForSEO MCP tools the R1 agent executes directly to the frontend UI via SSE.
- **Core SEO Stack Enforcement**: Updated DeepSeek-R1's system prompt in `_agentic_tool_decision` to strictly enforce the selection of a 4-tool baseline (Keyword Ideas, Live SERP, Related Searches, On-Page Content Analysis) for unbreakable semantic resolution.

### Legacy Phases
- **Phase 1: Data Logic (DeepSeek-R1 + MCP)**: Uses `deepseek-reasoner` and DataForSEO MCP. Fixed parameter paralysis by increasing token limits and aligning JSON schemas.
- **Phase 1.5: Elite Discovery Layer**: Exa.ai Neural Search via custom HTTP client to extract semantic meaning and bypass restrictive legacy search snippets.
- **Phase 2: Strategic Logic (DeepSeek-V3)**: Hits `deepseek-chat` with PAS framework.
- **Phase 3: Prose Logic (Gemini 2.5 Pro)**: Heavy-duty final prose drafting using native `google-genai` SDK.
- **Phase 4 & 5: UX & SSE Orchestration**: Live generative pipelines via FastAPI StreamingResponse.
- **Phase 6: Human-In-The-Loop**: Collects overrides to build `UserStyleRule` entities via `gemini-2.5-flash` for self-learning.
""")

        # Write Tree Structure
        outfile.write("\n## 2. Project Structure\n```text\nAres Engine/\n")
        
        skip_dirs = {"__pycache__", "venv", ".git", ".github"}
        
        def print_tree(directory, prefix=""):
            entries = sorted(os.listdir(directory))
            entries = [e for e in entries if e not in skip_dirs and not e.endswith('.pyc')]
            
            for i, entry in enumerate(entries):
                path = os.path.join(directory, entry)
                is_last = (i == len(entries) - 1)
                connector = "└── " if is_last else "├── "
                outfile.write(f"{prefix}{connector}{entry}\n")
                
                if os.path.isdir(path):
                    extension = "    " if is_last else "│   "
                    print_tree(path, prefix + extension)

        # Print tree for app and static dirs to keep it clean
        for d in target_dirs:
            if os.path.exists(d):
                outfile.write(f"├── {d}/\n")
                print_tree(d, "│   ")
        outfile.write("```\n")

        # Write Core Files
        outfile.write("\n## 3. Core Project Files\n")
        
        allowed_extensions = {".py", ".html", ".js", ".css", ".md"}
        
        for root, dirs, files in os.walk("."):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            
            for file in files:
                filepath = os.path.join(root, file)
                
                # Skip the file we are currently building, script, DBs, JSONs, or massive logs
                if file in ["llm_paste.md", "build_llm_paste.py", "blog.db", "tools.txt", "tools.json"] or filepath.endswith(".txt"):
                    continue
                    
                ext = os.path.splitext(file)[1]
                if ext in allowed_extensions:
                    # Determine markdown syntax block language
                    lang = "python" if ext == ".py" else ext[1:]
                    
                    try:
                        with open(filepath, 'r', encoding='utf-8') as infile:
                            content = infile.read()
                            
                            # Standardize path display
                            display_path = filepath.replace(".\\", "").replace("\\", "/")
                            
                            outfile.write(f"\n### {display_path}\n```{lang}\n{content}\n```\n")
                    except Exception as e:
                        print(f"Skipping {filepath} due to error: {e}")

if __name__ == "__main__":
    create_llm_paste()
    print("Successfully generated llm_paste.md")

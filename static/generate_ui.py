html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ares Engine - Oracle Interface</title>
    <script src="https://cdn.tailwindcss.com?plugins=typography"></script>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@300;400;500&display=swap');
        :root {
            --bg-deep: #000000;
            --bg-elevated: #050505;
            --bg-panel: #0a0a0a;
            --accent: #d4af37; /* gold */
            --accent-glow: rgba(212, 175, 55, 0.4);
            --text-primary: #e5e5e5;
            --text-muted: #737373;
        }
        body { font-family: 'Inter', sans-serif; background: var(--bg-deep); color: var(--text-primary); }
        .mono { font-family: 'JetBrains Mono', monospace; }
        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #333; border-radius: 4px; }
        .agent-node { opacity: 0.3; transform: scale(0.95); transition: all 0.5s ease; filter: grayscale(100%); }
        .agent-node-active { opacity: 1 !important; transform: scale(1.05) !important; color: var(--accent) !important; filter: grayscale(0%) !important; text-shadow: 0 0 16px var(--accent-glow); animation: breathe 4s ease-in-out infinite; }
        @keyframes breathe { 0%, 100% { opacity: 0.8; } 50% { opacity: 1; text-shadow: 0 0 24px var(--accent-glow); } }
        @keyframes pulse-slow { 0%, 100% { opacity: 0.3; } 50% { opacity: 0.6; } }
        .pulse-slow { animation: pulse-slow 3s infinite; }
        .prose-custom h1 { color: #fff; font-size: 2.5rem; font-weight: 300; margin-bottom: 2rem; }
        .prose-custom h2 { color: var(--accent); font-weight: 400; font-size: 1.5rem; margin-top: 2rem; }
        .prose-custom p { color: #a3a3a3; font-weight: 300; line-height: 1.8; }
        input:focus textarea:focus { outline: none; }
        .glass-modal { background: rgba(5,5,5,0.8); backdrop-filter: blur(16px); }
        .minimal-input { background: transparent; border: none; border-bottom: 1px solid #333; transition: border-color 0.3s; }
        .minimal-input:focus { border-bottom-color: var(--accent); outline: none; }
        .btn-minimal { border: 1px solid #333; transition: all 0.3s; }
        .btn-minimal:hover { border-color: var(--accent); color: var(--accent); background: rgba(212,175,55,0.05); }
    </style>
</head>
<body class="selection:bg-[var(--accent-glow)] flex flex-col h-screen overflow-hidden">
    <!-- Top Nav -->
    <header class="w-full flex flex-col md:flex-row items-center justify-between px-6 py-4 z-20 bg-gradient-to-b from-black to-transparent">
        <div class="flex items-center gap-4 mb-4 md:mb-0 w-full md:w-auto">
            <svg class="w-6 h-6 text-[#d4af37]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
            <span class="text-sm font-light tracking-[0.3em] uppercase text-white/80">Ares Oracle</span>
        </div>
        
        <div class="flex flex-1 items-center max-w-4xl w-full px-4 gap-4">
            <input id="keyword-input" type="text" class="w-full minimal-input text-2xl font-light text-white placeholder-neutral-700 py-2" placeholder="Define objective...">
            <input id="niche-input" type="text" class="w-48 minimal-input text-sm font-light text-[#d4af37]/70 placeholder-neutral-700 py-2 text-center" placeholder="Sector (e.g. Finance)">
            <button id="generate-btn" class="btn-minimal px-8 py-2 text-xs uppercase tracking-[0.2em] text-white">Execute</button>
        </div>

        <div class="flex items-center gap-4 hidden md:flex">
            <span class="text-[9px] font-bold text-neutral-600 uppercase tracking-[0.2em]">ENV //</span>
            <select id="profile-select" class="bg-black border border-neutral-800 text-neutral-400 text-xs py-1 px-2 cursor-pointer focus:border-[#d4af37] outline-none">
                <option value="default">DEFAULT</option>
            </select>
            <button id="add-workspace-btn" class="text-neutral-500 hover:text-[#d4af37] transition"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 4v16m8-8H4"></path></svg></button>
        </div>
    </header>

    <!-- Progress Pipeline (Ambient) -->
    <div class="flex justify-center items-center py-2 px-6 gap-8 md:gap-24 opacity-80 z-20">
        <div id="agent-research" class="agent-node flex flex-col items-center gap-2">
            <span class="text-[9px] uppercase tracking-[0.3em]">Phase 01</span>
            <span class="text-xs font-light">Research</span>
        </div>
        <div class="h-px w-12 bg-neutral-800 hidden md:block"></div>
        <div id="agent-psychology" class="agent-node flex flex-col items-center gap-2">
            <span class="text-[9px] uppercase tracking-[0.3em]">Phase 02</span>
            <span class="text-xs font-light">Strategy</span>
        </div>
        <div class="h-px w-12 bg-neutral-800 hidden md:block"></div>
        <div id="agent-writer" class="agent-node flex flex-col items-center gap-2">
            <span class="text-[9px] uppercase tracking-[0.3em]">Phase 03</span>
            <span class="text-xs font-light">Synthesis</span>
        </div>
    </div>

    <!-- Main Workspace -->
    <main class="flex-1 flex flex-col md:flex-row overflow-hidden relative z-10 px-4 md:px-12 pb-8 gap-8">
        
        <!-- Background Elements -->
        <div class="absolute inset-0 pointer-events-none flex justify-center items-center opacity-5">
            <div class="w-[800px] h-[800px] rounded-full border border-white pulse-slow"></div>
            <div class="w-[600px] h-[600px] rounded-full border border-[#d4af37] absolute"></div>
        </div>

        <!-- Left Sidebar / Terminal & Settings -->
        <aside class="w-full md:w-64 flex flex-col gap-8 shrink-0 relative z-20 mt-4 h-full">
            <div class="flex-1 flex flex-col border border-neutral-900 bg-black/40 p-4">
                <div class="text-[10px] uppercase tracking-widest text-[#d4af37] mb-4">Telemetry</div>
                <div id="terminal-body" class="mono text-[10px] text-neutral-500 flex-1 overflow-y-auto space-y-2"></div>
            </div>
            
            <div class="flex flex-col gap-4 border border-neutral-900 bg-black/40 p-4 shrink-0">
                <div class="text-[10px] uppercase tracking-widest text-[#d4af37]">Quality Vector</div>
                <div class="flex gap-4 items-center">
                    <svg viewBox="0 0 100 100" class="w-16 h-16 transform -rotate-90">
                        <circle cx="50" cy="50" r="45" fill="none" stroke="#111" stroke-width="4"/>
                        <circle id="score-circle" cx="50" cy="50" r="45" fill="none" stroke="#d4af37" stroke-width="4" stroke-dasharray="283" stroke-dashoffset="283" class="transition-all duration-1000"/>
                    </svg>
                    <span id="score-text" class="mono text-2xl font-light">0%</span>
                </div>
                <div class="space-y-2 mt-2">
                    <div id="audit-length" class="flex justify-between items-center text-[10px] text-neutral-500 uppercase tracking-widest text-left"><span>Capacity</span><div class="audit-dot w-1 h-1 bg-neutral-800 rounded-full"></div></div>
                    <div id="audit-entities" class="flex justify-between items-center text-[10px] text-neutral-500 uppercase tracking-widest text-left"><span>Structure</span><div class="audit-dot w-1 h-1 bg-neutral-800 rounded-full"></div></div>
                    <div id="audit-visuals" class="flex justify-between items-center text-[10px] text-neutral-500 uppercase tracking-widest text-left"><span>Data</span><div class="audit-dot w-1 h-1 bg-neutral-800 rounded-full"></div></div>
                </div>
            </div>
            
            <div class="flex gap-4">
                <button id="open-brain-btn" class="flex-1 btn-minimal py-3 text-[10px] uppercase tracking-[0.2em] text-neutral-400">Memory</button>
                <button id="open-cartographer-btn" class="flex-1 btn-minimal py-3 text-[10px] uppercase tracking-[0.2em] text-neutral-400">Carto</button>
            </div>
        </aside>

        <!-- Right Content Area -->
        <section class="flex-1 flex flex-col md:flex-row gap-8 relative z-20 h-full overflow-hidden">
            <!-- Blueprint -->
            <div class="w-full md:w-80 flex flex-col overflow-hidden border border-neutral-900 bg-black/40 p-6 h-full">
                <div class="text-[10px] uppercase tracking-widest text-[#d4af37] mb-6">Cognitive Architecture</div>
                <div id="blueprint-content" class="flex-1 overflow-y-auto text-sm text-neutral-400 space-y-4 prose-custom"></div>
            </div>

            <!-- Output Display -->
            <div class="flex-1 flex flex-col overflow-hidden relative border border-neutral-900 bg-black/40 p-6 h-full">
                <div class="flex justify-between items-center mb-6">
                    <div class="text-[10px] uppercase tracking-widest text-[#d4af37]">Result Matrix</div>
                    <div class="flex gap-2">
                        <button id="copy-md-btn" class="text-[10px] uppercase tracking-[0.2em] text-neutral-500 hover:text-white transition">Copy MD</button>
                        <button id="copy-html-btn" class="text-[10px] uppercase tracking-[0.2em] text-neutral-500 hover:text-white transition">Copy HTML</button>
                    </div>
                </div>
                
                <div class="flex-1 overflow-y-auto relative p-4">
                    <div id="article-content" class="h-full prose-custom">
                        <div class="h-full flex flex-col justify-center items-center opacity-30">
                            <svg class="w-8 h-8 text-neutral-600 mb-6 pulse-slow" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1" d="M12 4v16m8-8H4"></path></svg>
                            <span class="text-[10px] uppercase tracking-[0.3em]">Awaiting Input Sequence</span>
                        </div>
                    </div>
                    <textarea id="article-editor" class="w-full h-full bg-transparent border-none text-neutral-300 mono text-sm outline-none resize-none hidden" spellcheck="false"></textarea>
                </div>
                
                <div id="approve-container" class="hidden pt-4 mt-auto">
                    <button id="approve-btn" class="w-full btn-minimal bg-[#d4af37]/10 text-[#d4af37] text-xs py-4 uppercase tracking-[0.2em]">Deploy Knowledge & Improve</button>
                </div>
            </div>
        </section>
    </main>

    <!-- Modals -->
    <!-- Clarify Modal -->
    <div id="clarify-modal" class="fixed inset-0 z-[100] hidden flex items-center justify-center p-4">
        <div id="clarify-backdrop" class="absolute inset-0 bg-black/90 backdrop-blur-sm"></div>
        <div id="clarify-panel" class="relative bg-[#050505] border border-neutral-800 p-8 w-full max-w-2xl transform scale-95 opacity-0 transition-all duration-300">
            <h2 class="text-xl font-light text-white mb-6 uppercase tracking-widest"><span class="text-[#d4af37]">01 //</span> Context Required</h2>
            <div id="clarify-loading" class="flex flex-col items-center justify-center py-10 opacity-50 pulse-slow">
                <div class="w-8 h-8 border border-[#d4af37] w-full rounded-full animate-spin"></div>
            </div>
            <div id="clarify-form" class="hidden space-y-6">
                <div id="questions-container" class="space-y-6"></div>
                <div class="flex justify-end gap-4 pt-6 mt-6 border-t border-neutral-900">
                    <button id="clarify-skip-btn" class="text-xs uppercase tracking-[0.2em] text-neutral-500 hover:text-white">Bypass</button>
                    <button id="clarify-submit-btn" class="btn-minimal px-6 py-2 text-xs uppercase tracking-[0.2em] text-[#d4af37]">Provide Input</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Brain Modal -->
    <div id="brain-modal" class="fixed inset-0 z-[100] hidden flex justify-end">
        <div id="brain-backdrop" class="absolute inset-0 bg-black/80 backdrop-blur-sm opacity-0 transition-opacity"></div>
        <div id="brain-panel" class="relative w-full max-w-md bg-[#050505] border-l border-neutral-800 translate-x-full transition-transform duration-500 flex flex-col p-8">
            <div class="flex justify-between items-center mb-8">
                <h2 class="text-lg font-light uppercase tracking-widest"><span class="text-[#d4af37]">02 //</span> Memory Core</h2>
                <button id="close-brain-btn" class="text-neutral-500 hover:text-white"><svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1" d="M6 18L18 6M6 6l12 12"></path></svg></button>
            </div>
            <div class="mb-6 flex gap-2">
                <input id="new-rule-input" class="w-full minimal-input text-sm text-white py-2" placeholder="Force constraint...">
                <button id="add-rule-btn" class="btn-minimal px-4 text-[#d4af37]">+</button>
            </div>
            <div id="rules-container" class="flex-1 overflow-y-auto space-y-4"></div>
        </div>
    </div>

    <!-- Workspace Modal -->
    <div id="workspace-modal-overlay" class="fixed inset-0 z-[110] hidden flex items-center justify-center p-4">
        <div class="absolute inset-0 bg-black/90 backdrop-blur-sm"></div>
        <div id="workspace-modal-panel" class="relative bg-[#050505] border border-neutral-800 p-8 w-full max-w-md transform scale-95 opacity-0 transition-all duration-300">
            <h2 class="text-lg font-light uppercase tracking-widest mb-6"><span class="text-[#d4af37]">03 //</span> Initialize Partition</h2>
            <input id="modal-workspace-input" class="w-full minimal-input text-lg text-white py-3 mb-8 focus:border-[#d4af37] transition-all" placeholder="Partition Identifier...">
            <div class="flex justify-end gap-4">
                <button id="workspace-cancel-btn" class="text-xs uppercase tracking-[0.2em] text-neutral-500 hover:text-white">Abort</button>
                <button id="workspace-create-btn" class="btn-minimal px-6 py-2 text-xs uppercase tracking-[0.2em] text-[#d4af37]">Initialize</button>
            </div>
        </div>
    </div>

    <!-- Cartographer Modal -->
    <div id="cartographer-modal" class="fixed inset-0 z-[120] hidden flex justify-start">
        <div id="cartographer-backdrop" class="absolute inset-0 bg-black/80 backdrop-blur-sm opacity-0 transition-opacity"></div>
        <div id="cartographer-panel" class="relative w-full max-w-2xl bg-[#050505] border-r border-neutral-800 -translate-x-full transition-transform duration-500 flex flex-col p-8 h-full">
            <div class="flex justify-between items-center mb-8">
                <h2 class="text-lg font-light uppercase tracking-widest"><span class="text-[#d4af37]">04 //</span> Cartography Node</h2>
                <button id="close-cartographer-btn" class="text-neutral-500 hover:text-white"><svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1" d="M6 18L18 6M6 6l12 12"></path></svg></button>
            </div>
            <div class="flex gap-4 mb-8">
                <input id="cartographer-topic-input" class="w-full minimal-input text-sm text-white py-2" placeholder="Declare root entity...">
                <button id="cartographer-map-btn" class="btn-minimal px-6 text-[10px] uppercase tracking-widest text-[#d4af37]">Deploy</button>
            </div>
            
            <div id="cartographer-loading" class="hidden flex-1 flex flex-col justify-center items-center opacity-50">
                <div class="text-[#d4af37] text-xs uppercase tracking-widest pulse-slow" id="cartographer-loading-text">Traversing Semantic Topography...</div>
            </div>
            
            <div id="cartographer-results" class="flex-1 overflow-y-auto space-y-6 hidden pr-4"></div>
            
            <div id="cartographer-empty" class="flex-1 flex flex-col justify-center items-center opacity-30">
                <div class="pulse-slow uppercase tracking-widest text-[10px]">Awaiting Coordinate Input</div>
            </div>
        </div>
    </div>

    <script src="/static/js/console.js?v=6.0"></script>
</body>
</html>
"""

with open("ares_console.html", "w") as f:
    f.write(html_content)

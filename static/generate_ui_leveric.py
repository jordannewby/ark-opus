html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ares Engine - Leveric Cyber</title>
    <script src="https://cdn.tailwindcss.com?plugins=typography"></script>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400&display=swap');

        :root {
            --bg-base: #050505;
            --bg-elevated: #0F0F11;
            --text-main: #FFFFFF;
            --text-muted: #8B8B93;
            --accent: #CCFF00; /* Leveric Acid Green */
            --accent-hover: #B3E600;
        }

        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-base);
            color: var(--text-main);
            margin: 0;
            overflow: hidden;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }

        /* Sharp, cyber ambient glow */
        .ambient-glow {
            position: fixed;
            top: -20%; left: -10%;
            width: 70vw; height: 70vh;
            background: radial-gradient(circle, rgba(204, 255, 0, 0.04) 0%, rgba(5, 5, 5, 0) 70%);
            z-index: -1;
            pointer-events: none;
        }
        .ambient-glow-2 {
            position: fixed;
            bottom: -20%; right: -10%;
            width: 60vw; height: 60vh;
            background: radial-gradient(circle, rgba(255, 255, 255, 0.02) 0%, rgba(5, 5, 5, 0) 70%);
            z-index: -1;
            pointer-events: none;
        }

        .agent-node {
            opacity: 0.3;
            transform: scale(0.98);
            transition: all 0.5s ease;
        }
        .agent-node-active {
            opacity: 1 !important;
            transform: scale(1.05) !important;
            color: var(--accent) !important;
            font-weight: 600;
            text-shadow: 0 0 15px rgba(204, 255, 0, 0.3);
        }

        /* Dark mode Prose for generated text */
        .prose-custom h1 { color: #FFFFFF; font-size: 2.25rem; font-weight: 600; margin-bottom: 1.5rem; letter-spacing: -0.02em; }
        .prose-custom h2 { color: #F4F4F5; font-size: 1.5rem; font-weight: 600; margin-top: 2.5rem; margin-bottom: 1rem; letter-spacing: -0.01em; }
        .prose-custom h3 { color: #E4E4E7; font-size: 1.25rem; font-weight: 500; margin-top: 1.5rem; }
        .prose-custom p { color: #A1A1AA; line-height: 1.8; margin-bottom: 1.5rem; font-size: 1.05rem; }
        .prose-custom ul { list-style-type: none; padding-left: 0; margin-bottom: 1.5rem; color: #A1A1AA; }
        .prose-custom li { position: relative; padding-left: 1.25rem; margin-bottom: 0.5rem; }
        .prose-custom li::before { content: '→'; position: absolute; left: 0; color: var(--accent); font-weight: bold; }

        .mono-text { font-family: 'JetBrains Mono', monospace; }

        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.1); border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: rgba(255, 255, 255, 0.2); }

        input:focus, textarea:focus, select:focus, button:focus {
            outline: none !important;
            box-shadow: none !important;
            border-color: transparent;
        }
        
        #keyword-input:focus, #niche-input:focus {
            border-bottom-color: var(--accent) !important;
        }

        .btn-sleek { background-color: var(--accent); color: #000000; border-radius: 9999px; padding: 0.75rem 2rem; transition: all 0.3s; font-weight: 700; letter-spacing: 0.05em; box-shadow: 0 0 15px rgba(204,255,0,0.15); }
        .btn-sleek:hover { background-color: var(--accent-hover); box-shadow: 0 0 25px rgba(204,255,0,0.3); transform: translateY(-1px); }
        
        .btn-outline { border: 1px solid rgba(255,255,255,0.1); color: #8B8B93; border-radius: 9999px; padding: 0.5rem 1.5rem; transition: all 0.3s; font-weight: 500; background: transparent; }
        .btn-outline:hover { background-color: rgba(204,255,0,0.05); border-color: rgba(204,255,0,0.3); color: var(--accent); box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }

        .sidebar-btn { width: 100%; text-align: left; padding: 0.75rem 1rem; border-radius: 0.75rem; color: #8B8B93; font-weight: 500; transition: all 0.2s; }
        .sidebar-btn:hover { background-color: rgba(204, 255, 0, 0.05); color: var(--accent); }

        #score-circle { stroke: var(--accent); }
        .audit-dot { transition: background 0.5s ease; width: 6px; height: 6px; }
        
        ::selection { background: rgba(204, 255, 0, 0.15); color: #FFFFFF; }

        .glass-panel { background-color: var(--bg-elevated); border: 1px solid rgba(255,255,255,0.05); }
    </style>
</head>
<body>
    <div class="ambient-glow"></div>
    <div class="ambient-glow-2"></div>

    <div class="flex flex-col h-full w-full px-6 md:px-12 pt-10 pb-6 relative z-10 box-border overflow-hidden max-w-[1600px] mx-auto">

        <!-- Header / Input Area -->
        <div class="w-full flex flex-col md:flex-row items-end justify-between gap-8 shrink-0 mb-10">
            <div class="flex-1 w-full max-w-4xl relative">
                <input id="keyword-input" type="text" 
                    class="w-full bg-transparent border-0 border-b border-white/10 text-xl md:text-2xl text-white placeholder-slate-600 pb-3 transition-colors focus:border-[#CCFF00]"
                    placeholder="What topic should we write about today?">
            </div>
            
            <div class="flex flex-col md:flex-row items-center gap-6 pb-2 w-full md:w-auto">
                <input id="niche-input" type="text" 
                    class="bg-transparent border-0 border-b border-white/10 text-lg text-[#8B8B93] placeholder-slate-600 pb-2 w-48 text-center transition-colors focus:border-[#CCFF00]"
                    placeholder="Industry or Niche">
                
                <div class="flex items-center gap-3 bg-[#0F0F11] border border-white/5 rounded-full px-4 py-2">
                    <span class="text-xs uppercase tracking-wider text-slate-500 font-medium">Workspace</span>
                    <select id="profile-select" class="bg-transparent border-none text-sm font-medium text-white appearance-none cursor-pointer outline-none max-w-[100px] text-ellipsis">
                        <option value="default" class="bg-[#050505] text-white">Default</option>
                    </select>
                    <button id="add-workspace-btn" class="text-slate-500 hover:text-[#CCFF00] transition-colors">+</button>
                </div>

                <button id="generate-btn" class="btn-sleek shrink-0">
                    Generate Article
                </button>
            </div>
        </div>

        <!-- Ambient Pipeline Nodes -->
        <div class="flex justify-center items-center py-2 px-6 gap-8 md:gap-24 shrink-0 mb-8 max-w-2xl mx-auto w-full">
            <div id="agent-research" class="agent-node text-xs uppercase tracking-widest font-medium text-slate-500">Researching</div>
            <div class="h-px w-8 bg-white/10 md:block hidden"></div>
            <div id="agent-psychology" class="agent-node text-xs uppercase tracking-widest font-medium text-slate-500">Strategizing</div>
            <div class="h-px w-8 bg-white/10 md:block hidden"></div>
            <div id="agent-writer" class="agent-node text-xs uppercase tracking-widest font-medium text-slate-500">Writing</div>
        </div>

        <!-- Main Workspace Area -->
        <div class="flex-1 flex flex-col md:flex-row gap-8 w-full overflow-hidden">
            
            <!-- Left Sidebar -->
            <div class="w-full md:w-64 flex flex-col shrink-0 gap-6 min-h-0">
                
                <!-- Telemetry -->
                <div class="flex flex-col min-h-0 glass-panel rounded-3xl p-6">
                    <div class="text-xs uppercase tracking-wider text-slate-500 mb-4 font-semibold">Activity Log</div>
                    <div id="terminal-body" class="mono-text text-[11px] leading-relaxed text-[#8B8B93] space-y-3 overflow-y-auto"></div>
                </div>

                <!-- Audit -->
                <div class="shrink-0 glass-panel rounded-3xl p-6">
                    <div class="text-xs uppercase tracking-wider text-slate-500 mb-4 font-semibold">Quality Score</div>
                    <div class="flex items-center gap-5">
                        <div class="relative w-14 h-14 shrink-0">
                            <svg viewBox="0 0 100 100" class="w-full h-full transform -rotate-90">
                                <circle cx="50" cy="50" r="46" fill="none" stroke="rgba(255,255,255,0.05)" stroke-width="6" />
                                <circle id="score-circle" cx="50" cy="50" r="46" fill="none" class="transition-all duration-1000" stroke-width="6" stroke-dasharray="289" stroke-dashoffset="289" />
                            </svg>
                            <div class="absolute inset-0 flex items-center justify-center">
                                <span id="score-text" class="mono-text text-sm font-semibold text-white">0%</span>
                            </div>
                        </div>
                        <div class="flex-1 flex flex-col gap-2.5 text-[10px] uppercase font-semibold text-slate-500 tracking-wider">
                            <div id="audit-length" class="flex items-center justify-between"><span>Length</span><span class="audit-dot bg-white/10 rounded-full"></span></div>
                            <div id="audit-entities" class="flex items-center justify-between"><span>Headings</span><span class="audit-dot bg-white/10 rounded-full"></span></div>
                            <div id="audit-visuals" class="flex items-center justify-between"><span>Formatting</span><span class="audit-dot bg-white/10 rounded-full"></span></div>
                        </div>
                    </div>
                </div>

                <!-- Tools Navigation -->
                <div class="flex flex-col gap-1 mt-auto glass-panel rounded-3xl p-3">
                    <button id="open-blueprint-btn" class="sidebar-btn flex items-center justify-between group">
                        <span>View Blueprint</span>
                        <svg class="w-4 h-4 text-[#8B8B93] group-hover:text-[#CCFF00] transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg>
                    </button>
                    <button id="open-brain-btn" class="sidebar-btn flex items-center justify-between group">
                        <span>Style Memory</span>
                        <svg class="w-4 h-4 text-[#8B8B93] group-hover:text-[#CCFF00] transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"></path></svg>
                    </button>
                    <button id="open-cartographer-btn" class="sidebar-btn flex items-center justify-between group">
                        <span>Cartographer</span>
                        <svg class="w-4 h-4 text-[#8B8B93] group-hover:text-[#CCFF00] transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"></path></svg>
                    </button>
                </div>
            </div>

            <!-- Main Editor Canvas -->
            <div class="flex-1 flex flex-col min-h-0 relative glass-panel rounded-3xl overflow-hidden">
                <div class="flex items-center justify-between px-8 py-5 shrink-0 border-b border-white/5 bg-[#0F0F11]/50 backdrop-blur-sm z-10">
                    <div class="text-sm font-semibold text-white">Generated Article</div>
                    <div class="flex gap-3">
                        <button id="copy-md-btn" class="btn-outline text-xs">Copy Text</button>
                        <button id="copy-html-btn" class="btn-outline text-xs">Copy Formatted</button>
                    </div>
                </div>

                <div class="flex-1 overflow-y-auto px-8 md:px-16 py-8 relative">
                    <div id="article-content" class="prose-custom max-w-3xl mx-auto h-full">
                        <div class="h-full flex flex-col items-center justify-center opacity-40">
                            <svg class="w-8 h-8 text-slate-500 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>
                            <span class="text-xs uppercase tracking-widest font-medium text-slate-500">Ready to write</span>
                        </div>
                    </div>
                    <textarea id="article-editor" spellcheck="false" class="w-full h-full min-h-[600px] bg-transparent border-none text-slate-300 text-base leading-relaxed resize-none hidden max-w-3xl mx-auto block p-4 rounded-xl focus:bg-white/5 transition-colors"></textarea>
                </div>

                <div id="approve-container" class="absolute bottom-0 left-0 right-0 p-6 hidden bg-gradient-to-t from-[#0F0F11] via-[#0F0F11] to-transparent">
                    <button id="approve-btn" class="w-full max-w-md mx-auto block btn-sleek text-sm">
                        Save Edits & Improve AI Writing Style
                    </button>
                </div>
            </div>

        </div>
    </div>


    <!-- ==================== MODALS ==================== -->

    <!-- Blueprint Modal -->
    <div id="blueprint-modal" class="fixed inset-0 z-[60] flex hidden">
        <div id="blueprint-backdrop" class="absolute inset-0 bg-black/70 backdrop-blur-md opacity-0 transition-opacity duration-500"></div>
        <div id="blueprint-panel" class="relative w-full md:w-[400px] bg-[#0F0F11] h-full transform -translate-x-full transition-transform duration-500 flex flex-col shadow-2xl border-r border-white/5 p-8">
            <div class="flex items-center justify-between mb-8 pb-6 border-b border-white/5">
                <h2 class="text-xl font-semibold text-white tracking-tight">Article Blueprint</h2>
                <button id="close-blueprint-btn" class="text-slate-500 hover:text-[#CCFF00] bg-white/5 hover:bg-white/10 rounded-full p-2 transition-colors">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                </button>
            </div>
            <div id="blueprint-content" class="flex-1 overflow-y-auto space-y-4 pr-2 text-sm text-[#8B8B93]">
                <div class="flex flex-col items-center justify-center h-40 opacity-40">
                    <p class="text-xs font-medium uppercase tracking-wider text-center">No strategy mapped yet</p>
                </div>
            </div>
        </div>
    </div>

    <!-- Clarify / Quick Questions -->
    <div id="clarify-modal" class="fixed inset-0 z-[70] flex items-center justify-center hidden p-4">
        <div id="clarify-backdrop" class="absolute inset-0 bg-black/70 backdrop-blur-md transition-opacity"></div>
        <div id="clarify-panel" class="relative w-full max-w-2xl bg-[#0F0F11] border border-white/5 rounded-3xl shadow-2xl transform transition-all scale-95 opacity-0 p-10 overflow-hidden">
            
            <h2 class="text-2xl font-semibold text-white mb-2">Quick Questions</h2>
            <p class="text-[#8B8B93] text-sm mb-10">Help the AI focus on what matters to you.</p>
            
            <div id="clarify-loading" class="py-16 flex flex-col items-center">
                <div class="w-8 h-8 rounded-full border-2 border-[#CCFF00] border-t-transparent animate-spin mb-4"></div>
                <div class="text-xs uppercase font-semibold text-slate-500 tracking-wider">Analyzing Topic...</div>
            </div>
            
            <div id="clarify-form" class="hidden flex flex-col gap-8 max-h-[60vh] overflow-y-auto pr-2">
                <div id="questions-container" class="space-y-6"></div>
                <div class="flex flex-col sm:flex-row items-center gap-4 justify-end pt-6 border-t border-white/5 mt-4 sticky bottom-0 bg-[#0F0F11] pb-2">
                    <button id="clarify-skip-btn" class="text-sm font-semibold text-slate-500 hover:text-[#CCFF00] transition-colors px-4">Skip Questions</button>
                    <button id="clarify-submit-btn" class="btn-sleek text-sm px-6 py-2.5 w-full sm:w-auto">Submit Answers</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Style Memory -->
    <div id="brain-modal" class="fixed inset-0 z-[80] flex hidden">
        <div id="brain-backdrop" class="absolute inset-0 bg-black/70 backdrop-blur-md opacity-0 transition-opacity duration-500"></div>
        <div id="brain-panel" class="relative w-full md:w-[500px] ml-auto h-full bg-[#0F0F11] transform translate-x-full transition-transform duration-500 flex flex-col shadow-2xl p-8 md:p-10 border-l border-white/5">
            <div class="flex items-center justify-between mb-2">
                <h2 class="text-2xl font-semibold text-white">Style Memory</h2>
                <button id="close-brain-btn" class="text-slate-500 hover:text-[#CCFF00] bg-white/5 hover:bg-white/10 rounded-full p-2 transition-colors">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                </button>
            </div>
            <p class="text-[#8B8B93] text-sm mb-10 pr-6">The AI learns your writing preferences as you edit generated articles. You can also add rules manually.</p>
            
            <div class="flex items-center gap-3 pb-6 border-b border-white/5 mb-6">
                <input id="new-rule-input" type="text" class="flex-1 bg-black/50 border border-white/10 rounded-xl text-base text-white placeholder-slate-600 py-3 px-4 focus:bg-[#0F0F11] focus:border-[#CCFF00] transition-all font-medium" placeholder="E.g. Use a friendly, conversational tone">
                <button id="add-rule-btn" class="btn-sleek py-3 px-6">Add</button>
            </div>
            
            <div id="rules-container" class="flex-1 overflow-y-auto space-y-4 pr-2"></div>
        </div>
    </div>

    <!-- Workspace Partition -->
    <div id="workspace-modal-overlay" class="fixed inset-0 z-[90] flex items-center justify-center hidden p-4">
        <div class="absolute inset-0 bg-black/70 backdrop-blur-md"></div>
        <div id="workspace-modal-panel" class="relative w-full max-w-md bg-[#0F0F11] border border-white/5 rounded-3xl shadow-2xl transform scale-95 opacity-0 transition-all duration-300 p-10">
            <h2 class="text-2xl font-semibold text-white mb-2 mt-2">New Workspace</h2>
            <p class="text-[#8B8B93] text-sm mb-8">Group your knowledge and style rules into isolated projects.</p>
            
            <input id="modal-workspace-input" type="text" class="w-full bg-black/50 border border-white/10 rounded-xl text-lg text-white py-3 px-5 mb-8 focus:bg-[#0F0F11] focus:border-[#CCFF00] transition-all font-medium" placeholder="E.g. Tech Blog">
            
            <div class="flex items-center justify-end gap-4">
                <button id="workspace-cancel-btn" class="text-sm font-semibold text-slate-500 hover:text-[#CCFF00] transition-colors px-4">Cancel</button>
                <button id="workspace-create-btn" class="btn-sleek text-sm w-full sm:w-auto px-6 py-2.5">Create</button>
            </div>
        </div>
    </div>

    <!-- Cartographer -->
    <div id="cartographer-modal" class="fixed inset-0 z-[60] flex hidden">
        <div id="cartographer-backdrop" class="absolute inset-0 bg-black/70 backdrop-blur-md opacity-0 transition-opacity duration-500"></div>
        <div id="cartographer-panel" class="relative w-full md:w-[800px] h-full bg-[#0F0F11] transform -translate-x-full transition-transform duration-500 flex flex-col shadow-2xl p-8 md:p-12 border-r border-white/5">
            
            <div class="flex items-center justify-between mb-4 shrink-0">
                <h2 class="text-3xl font-semibold text-white">Cartographer</h2>
                <button id="close-cartographer-btn" class="text-slate-500 hover:text-[#CCFF00] bg-white/5 hover:bg-white/10 rounded-full p-2.5 transition-colors">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                </button>
            </div>
            
            <p class="text-[#8B8B93] text-[15px] mb-10 max-w-xl pr-4">Enter a high-level business topic. DeepSeek will autonomously generate a perfectly mapped Pillar & Spoke SEO strategy based on search volume intent.</p>
            
            <div class="flex flex-col md:flex-row items-center gap-4 mb-10 shrink-0 pb-10 border-b border-white/5">
                <input id="cartographer-topic-input" type="text" class="flex-1 w-full bg-black/50 border border-white/10 rounded-xl text-lg text-white placeholder-slate-600 py-4 px-6 focus:bg-[#0F0F11] focus:border-[#CCFF00] transition-all font-medium" placeholder="E.g. Cloud Security">
                <button id="cartographer-map-btn" class="w-full md:w-auto btn-sleek text-base px-8 py-4">Build Strategy Map</button>
            </div>
            
            <div id="cartographer-loading" class="hidden flex-1 flex flex-col items-center justify-center pt-8">
                <div class="w-10 h-10 rounded-full border-[3px] border-[#CCFF00] border-t-transparent animate-spin mb-6"></div>
                <div class="text-sm font-semibold text-slate-500" id="cartographer-loading-text">Analyzing Search Intent...</div>
                <div class="text-xs text-slate-600 mt-2">DeepSeek is traversing the semantic topography. Keep the page open.</div>
            </div>
            
            <div id="cartographer-results" class="flex-1 overflow-y-auto space-y-10 hidden pr-4"></div>
            
            <div id="cartographer-empty" class="flex-1 flex flex-col items-center justify-center opacity-40">
                <svg class="w-16 h-16 text-slate-600 mb-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"></path></svg>
                <div class="text-sm font-semibold text-slate-500 mb-2">Ready to explore</div>
            </div>
        </div>
    </div>

    <script src="/static/js/console.js?v=9.0"></script>
</body>
</html>
"""

with open("ares_console.html", "w") as f:
    f.write(html_content)

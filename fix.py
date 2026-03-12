import re

file_path = r'd:\Ares Engine\static\ares_console.html'
with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Fix the main wrapper paddings
old_wrapper = 'class="flex flex-col h-full w-full px-6 md:px-12 pt-10 pb-6 relative z-10 box-border overflow-hidden max-w-[1600px] mx-auto"'
new_wrapper = 'class="flex flex-col h-full w-full px-4 md:px-12 pt-6 md:pt-10 pb-4 md:pb-6 relative z-10 box-border overflow-hidden max-w-[1600px] mx-auto"'
text = text.replace(old_wrapper, new_wrapper)

# 2. Fix the Header / Input Area completely (replaces the whole block)
header_pattern = re.compile(r'<!-- Header / Input Area -->[\s\S]*?<!-- Ambient Pipeline Nodes -->')
new_header = """<!-- Header / Input Area -->
        <div class="w-full flex flex-col md:flex-row md:items-end justify-between gap-4 md:gap-8 shrink-0 mb-6 md:mb-10">
            <div class="flex-1 w-full md:max-w-4xl input-group">
                <label for="keyword-input">Primary Topic</label>
                <input id="keyword-input" type="text"
                    class="premium-input text-base md:text-lg"
                    placeholder="What topic should we write about today?">
            </div>

            <div class="flex flex-col sm:flex-row md:flex-row sm:items-end gap-4 md:gap-5 w-full md:w-auto mt-2 md:mt-0">
                <div class="flex w-full sm:w-auto gap-4 md:gap-5">
                    <div class="input-group flex-1 sm:w-32 md:w-40">
                        <label for="niche-input">Domain</label>
                        <input id="niche-input" type="text"
                            class="premium-input text-sm"
                            placeholder="Industry / Niche">
                    </div>

                    <div class="input-group flex-1 sm:w-auto">
                        <label>Workspace</label>
                        <div class="flex items-center gap-2 bg-[rgba(0,0,0,0.2)] border border-[rgba(255,255,255,0.08)] rounded-lg px-3 py-2.5 transition-colors h-[42px] min-w-[120px] md:min-w-[140px]">
                            <select id="profile-select"
                                class="bg-transparent border-none text-sm font-medium text-white appearance-none cursor-pointer outline-none w-full text-ellipsis">
                                <option value="default" class="bg-[#18181f] text-white">Default</option>
                            </select>
                            <button id="add-workspace-btn"
                                class="text-slate-500 hover:text-[#6366f1] transition-colors text-lg font-bold leading-none hover:scale-110 active:scale-95">+</button>
                        </div>
                    </div>
                </div>

                <button id="generate-btn" class="btn-sleek shrink-0 h-[42px] w-full sm:w-auto mt-2 sm:mt-[22px]">
                    Generate Article
                </button>
            </div>
        </div>

        <!-- Ambient Pipeline Nodes -->"""
text = header_pattern.sub(new_header, text)

# 3. Add Mobile CSS before </style>
if '@media (max-width: 767px)' not in text:
    mobile_css = """
        @media (max-width: 767px) {
            .sidebar-container {
                position: absolute;
                top: 0;
                left: 0;
                height: 100%;
                z-index: 50;
                background-color: var(--bg-elevated);
                transform: translateX(-110%);
                opacity: 0;
                width: 85%;
                max-width: 320px;
                border-right: 1px solid var(--border-soft);
                box-shadow: 10px 0 40px rgba(0,0,0,0.8);
                pointer-events: none;
                margin-right: 0;
                border-radius: 0 1.5rem 1.5rem 0;
                padding-top: 1rem;
            }
            .sidebar-mobile-active {
                transform: translateX(0);
                opacity: 1;
                pointer-events: auto;
            }
            .sidebar-collapsed {
                width: 85% !important;
                margin-right: 0;
            }
        }
    </style>"""
    text = text.replace('</style>', mobile_css)

# 4. Agent Nodes - Replace with responsive one + toast (if not already replaced)
agent_nodes_pattern = re.compile(r'<div class="flex justify-center items-center py-2 px-6 gap-8 md:gap-24 shrink-0 mb-8 max-w-2xl mx-auto w-full">[\s\S]*?</div>\s*</div>')
new_agent_nodes = """<div id="agent-nodes-container" class="hidden md:flex justify-center items-center py-2 px-6 gap-8 md:gap-24 shrink-0 mb-8 max-w-2xl mx-auto w-full transition-all opacity-100">
            <div id="agent-research" class="agent-node text-xs uppercase tracking-widest font-medium text-slate-500">Researching</div>
            <div class="h-px w-8 bg-[rgba(255,255,255,0.08)]"></div>
            <div id="agent-psychology" class="agent-node text-xs uppercase tracking-widest font-medium text-slate-500">Strategizing</div>
            <div class="h-px w-8 bg-[rgba(255,255,255,0.08)]"></div>
            <div id="agent-writer" class="agent-node text-xs uppercase tracking-widest font-medium text-slate-500">Writing</div>
        </div>

        <!-- Mobile Toast Notification -->
        <div id="mobile-agent-toast" class="md:hidden flex items-center justify-center -mt-2 mb-4 h-6 opacity-0 transition-opacity duration-300 pointer-events-none">
            <div class="bg-[rgba(99,102,241,0.15)] border border-[rgba(99,102,241,0.3)] text-[#a5b4fc] px-4 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest shadow-[0_0_10px_rgba(99,102,241,0.2)] flex items-center gap-2">
                <div class="w-1.5 h-1.5 bg-[#818cf8] rounded-full animate-pulse"></div>
                <span id="mobile-agent-text">Standby</span>
            </div>
        </div>"""
if 'mobile-agent-toast' not in text:
    text = agent_nodes_pattern.sub(new_agent_nodes, text)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(text)
print('Successfully rebuilt UI structure.')

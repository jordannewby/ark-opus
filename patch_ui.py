import sys
import re

file_path = r'd:\\Ares Engine\\static\\ares_console.html'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update CSS Vars
css_vars = """        :root {
            --bg-base: #0e0e12;
            --bg-elevated: #18181f;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent: #6366f1; /* Premium Indigo */
            --accent-hover: #4f46e5;
            --border-soft: rgba(255, 255, 255, 0.08);
            --shadow-soft: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            --shadow-elevated: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
            --focus-ring: 0 0 0 3px rgba(99, 102, 241, 0.2);
        }"""
content = re.sub(r':root\s*\{[^}]+\}', css_vars, content)

# 2. Add Sidebar & Input CSS right before </style>
sidebar_and_input_css = """
        /* Premium Input Styling */
        .input-group label {
            display: block;
            font-size: 0.75rem;
            font-weight: 500;
            color: var(--text-muted);
            margin-bottom: 0.35rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        
        .premium-input {
            width: 100%;
            background-color: rgba(0, 0, 0, 0.2);
            border: 1px solid var(--border-soft);
            color: var(--text-main);
            border-radius: 8px;
            padding: 0.65rem 1rem;
            transition: all 0.2s ease;
            box-shadow: inset 0 1px 2px rgba(0,0,0,0.1);
        }
        
        .premium-input:focus {
            background-color: rgba(0, 0, 0, 0.4);
            border-color: var(--accent);
            box-shadow: var(--focus-ring);
            outline: none;
        }
        
        .premium-input::placeholder {
            color: #52525b;
        }

        .sidebar-container {
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            width: 16rem;
            opacity: 1;
        }
        .sidebar-collapsed {
            width: 0 !important;
            opacity: 0;
            margin-right: -2rem; /* eliminate flex gap visually */
            pointer-events: none;
        }
        
        .glass-panel {
            background-color: var(--bg-elevated);
            border: 1px solid var(--border-soft);
            box-shadow: var(--shadow-soft);
        }
        
        .btn-sleek {
            background: var(--accent);
            color: #ffffff;
            border-radius: 8px;
            padding: 0.65rem 1.5rem;
            transition: all 0.2s ease;
            font-weight: 600;
            font-size: 0.875rem;
            box-shadow: var(--shadow-soft);
            border: 1px solid rgba(255,255,255,0.05);
        }
        
        .btn-sleek:hover {
            background: var(--accent-hover);
            transform: translateY(-1px);
            box-shadow: var(--shadow-elevated);
        }

        .btn-outline {
            border: 1px solid var(--border-soft);
            color: var(--text-muted);
            border-radius: 8px;
            padding: 0.5rem 1rem;
            transition: all 0.2s ease;
            font-weight: 500;
            background: var(--bg-elevated);
            font-size: 0.825rem;
        }

        .btn-outline:hover {
            color: var(--text-main);
            border-color: rgba(255,255,255,0.2);
            background: rgba(255,255,255,0.05);
        }

        .agent-node-active {
            opacity: 1 !important;
            transform: scale(1.02) !important;
            color: var(--accent) !important;
            font-weight: 600;
        }
"""
content = content.replace("</style>", sidebar_and_input_css + "\n    </style>")

# 3. Clean up old conflicting CSS blocks
# Remove .glass-panel from old place
content = re.sub(r'\.glass-panel\s*\{[^}]+\}', '', content, count=1)
# Remove .btn-sleek from old place
content = re.sub(r'\.btn-sleek\s*\{[\s\S]*?\.btn-sleek:hover\s*\{[\s\S]*?\}', '', content)
# Remove .btn-outline from old place
content = re.sub(r'\.btn-outline\s*\{[\s\S]*?\.btn-outline:hover\s*\{[\s\S]*?\}', '', content)
# Remove .agent-node-active from old place
content = re.sub(r'\.agent-node-active\s*\{[^}]+\}', '', content, count=1)
# Remove Old input group floating styles
input_group_old_pattern = r'\.input-group\s*\{[\s\S]*?\.input-group input:focus::placeholder\s*\{\s*opacity:\s*0\.3;\s*\}'
content = re.sub(input_group_old_pattern, '', content)

# 4. Remove Glows from body
content = content.replace('<div class="ambient-glow"></div>', '')
content = content.replace('<div class="ambient-glow-2"></div>', '')

# 5. Header / Inputs Update
old_keyword_input = '''<div class="flex-1 w-full max-w-4xl relative input-group group">
                <input id="keyword-input" type="text"
                    class="w-full bg-transparent border-0 border-b border-white/10 text-lg md:text-xl text-white placeholder-slate-600 py-3 transition-colors focus:border-[#3b82f6]"
                    placeholder="What topic should we write about today?">
                <label for="keyword-input">Primary Topic</label>
                <div
                    class="absolute bottom-0 left-0 w-0 h-0.5 bg-gradient-to-r from-[#3b82f6] to-[#8b5cf6] transition-all duration-300 group-focus-within:w-full">
                </div>
            </div>'''
new_keyword_input = '''<div class="flex-1 w-full max-w-4xl input-group">
                <label for="keyword-input">Primary Topic</label>
                <input id="keyword-input" type="text"
                    class="premium-input text-lg"
                    placeholder="What topic should we write about today?">
            </div>'''
content = content.replace(old_keyword_input, new_keyword_input)

old_niche_input = '''<div class="relative input-group group w-40 text-center">
                    <input id="niche-input" type="text"
                        class="bg-transparent border-0 border-b border-white/10 text-base text-[#8B8B93] placeholder-slate-600 py-2 w-full text-center transition-colors focus:border-[#3b82f6]"
                        placeholder="Industry or Niche">
                    <label for="niche-input" class="!left-[50%] !-translate-x-[50%]">Domain</label>
                    <div
                        class="absolute bottom-0 left-[50%] -translate-x-[50%] w-0 h-0.5 bg-gradient-to-r from-[#3b82f6] to-[#8b5cf6] transition-all duration-300 group-focus-within:w-full">
                    </div>
                </div>'''
new_niche_input = '''<div class="input-group w-40">
                    <label for="niche-input">Domain</label>
                    <input id="niche-input" type="text"
                        class="premium-input text-sm"
                        placeholder="Industry / Niche">
                </div>'''
content = content.replace(old_niche_input, new_niche_input)

old_workspace_sel = '''<div
                    class="flex items-center gap-2 bg-[#0F0F11] border border-white/5 rounded-full px-3 py-1.5 hover:border-white/10 transition-colors">
                    <span class="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Workspace</span>
                    <select id="profile-select"
                        class="bg-transparent border-none text-xs font-medium text-white appearance-none cursor-pointer outline-none max-w-[80px] text-ellipsis">
                        <option value="default" class="bg-[#050505] text-white">Default</option>
                    </select>
                    <button id="add-workspace-btn"
                        class="text-slate-500 hover:text-[#8b5cf6] transition-colors text-sm hover:scale-110 active:scale-95">+</button>
                </div>'''
new_workspace_sel = '''<div class="input-group">
                    <label>Workspace</label>
                    <div class="flex items-center gap-2 bg-[rgba(0,0,0,0.2)] border border-white/10 rounded-lg px-3 py-2.5 hover:border-white/20 transition-colors h-[42px] min-w-[140px]">
                        <select id="profile-select"
                            class="bg-transparent border-none text-sm font-medium text-white appearance-none cursor-pointer outline-none w-full text-ellipsis">
                            <option value="default" class="bg-[#18181f] text-white">Default</option>
                        </select>
                        <button id="add-workspace-btn"
                            class="text-slate-500 hover:text-[#6366f1] transition-colors text-lg font-bold leading-none hover:scale-110 active:scale-95">+</button>
                    </div>
                </div>'''
content = content.replace(old_workspace_sel, new_workspace_sel)

old_generate_btn = '''<button id="generate-btn"
                    class="btn-sleek shrink-0 active:scale-95 active:shadow-none hover:shadow-[0_0_20px_rgba(139,92,246,0.4)]">
                    Generate Article
                </button>'''
new_generate_btn = '''<button id="generate-btn" class="btn-sleek shrink-0 h-[42px] mt-[22px]">
                    Generate Article
                </button>'''
content = content.replace(old_generate_btn, new_generate_btn)

# Make sure the container aligns them all at the bottom
content = content.replace('flex flex-col md:flex-row items-center gap-5 pb-1', 'flex flex-col md:flex-row items-end gap-5')

# 6. Sidebar structure
old_sidebar_wrap = '''<!-- Left Sidebar -->
            <div class="w-full md:w-64 flex flex-col shrink-0 gap-6 min-h-0">'''
new_sidebar_wrap = '''<!-- Left Sidebar -->
            <div id="left-sidebar" class="sidebar-container flex flex-col shrink-0 gap-6 min-h-0">'''
content = content.replace(old_sidebar_wrap, new_sidebar_wrap)

old_editor_header = '''<div
                    class="flex items-center justify-between px-8 py-5 shrink-0 border-b border-white/5 bg-[#0F0F11]/50 backdrop-blur-sm z-10">
                    <div class="text-sm font-semibold text-white">Generated Article</div>'''
new_editor_header = '''<div
                    class="flex items-center justify-between px-8 py-5 shrink-0 border-b border-white/5 bg-transparent z-10">
                    <div class="flex items-center gap-4">
                        <button id="toggle-sidebar-btn" class="text-slate-500 hover:text-[#f8fafc] bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.08)] transition-all flex items-center justify-center p-2 rounded-lg hover:bg-[rgba(255,255,255,0.08)] shadow-sm" title="Toggle Sidebar">
                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h7"></path></svg>
                        </button>
                        <div class="text-sm font-semibold text-white">Generated Article</div>
                    </div>'''
content = content.replace(old_editor_header, new_editor_header)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Patching successful.")

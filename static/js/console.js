// ARES CONSOLE v4.0 - CYBER GLASS EXPERIMENT
let lastGeneratedMarkdown = "";

const els = {
    keywordInput: document.getElementById('keyword-input'),
    generateBtn: document.getElementById('generate-btn'),
    terminal: document.getElementById('terminal-body'),
    blueprintPane: document.getElementById('blueprint-content'),
    articlePane: document.getElementById('article-content'),
    scoreCircle: document.getElementById('score-circle'),
    scoreText: document.getElementById('score-text'),
    agentNodes: {
        research: document.getElementById('agent-research'),
        psychology: document.getElementById('agent-psychology'),
        writer: document.getElementById('agent-writer')
    },
    nicheInput: document.getElementById('niche-input'),
    profileSelect: document.getElementById('profile-select')
};

function terminalLog(agent, message, color = "#22d3ee") {
    const entry = document.createElement('div');
    entry.className = "flex bg-white/5 border border-white/5 rounded-md p-2 mt-2 animate-slideInRight text-slate-300";
    entry.innerHTML = `<span class="mr-2 shrink-0 w-[85px] tracking-wide" style="color: ${color}; font-weight: 600;">[${agent}]</span> <span class="flex-1 opacity-90">${message}</span>`;
    els.terminal.appendChild(entry);
    els.terminal.scrollTop = els.terminal.scrollHeight;
}

function updateAgentUI(activeNode) {
    Object.values(els.agentNodes).forEach(node => node.classList.remove('agent-node-active'));
    if (activeNode && els.agentNodes[activeNode]) {
        els.agentNodes[activeNode].classList.add('agent-node-active');
    }
}

function renderBlueprint(bp) {
    if (!bp) return;
    const audience = bp.target_audience || 'SEO Strategic Plan';
    let html = `<div class="mb-6"><h3 class="text-cyan-400 font-bold text-xs uppercase tracking-widest opacity-80">${audience}</h3></div>`;

    if (bp.outline_structure && Array.isArray(bp.outline_structure)) {
        html += `<div class="space-y-3">`;
        bp.outline_structure.forEach((item, idx) => {
            const heading = typeof item === 'object' ? (item.heading || item.title || "Section") : item;
            html += `<div class="p-4 bg-white/[0.02] border border-white/5 rounded-xl hover:bg-white/[0.04] transition-colors shadow-sm">
                        <div class="flex items-center gap-3">
                            <span class="text-cyan-500/50 mono-text text-[10px] uppercase font-bold tracking-widest">PHASE 0${idx + 1}</span>
                        </div>
                        <h4 class="text-slate-200 text-sm mt-1 font-medium leading-relaxed tracking-tight">${heading}</h4>
                     </div>`;
        });
        html += `</div>`;
    }
    els.blueprintPane.innerHTML = html;
}

let currentPostId = null;

function renderArticle(post) {
    if (!post || !post.content) return;
    lastGeneratedMarkdown = post.content;
    currentPostId = post.id;

    // Hide static viewer, show interactive editor
    els.articlePane.classList.add('hidden');
    const editor = document.getElementById('article-editor');
    const approveBtn = document.getElementById('approve-container');

    editor.value = post.content;
    editor.classList.remove('hidden');
    approveBtn.classList.remove('hidden');
}

// APPROVE & TRAIN EVENT
document.getElementById('approve-btn').addEventListener('click', async () => {
    if (!currentPostId) return;

    const editor = document.getElementById('article-editor');
    const updatedContent = editor.value;
    const btn = document.getElementById('approve-btn');

    btn.disabled = true;
    btn.innerText = "TRAINING MODEL... PLEASE WAIT";
    terminalLog("SYSTEM", "Saving your edits and teaching the AI your writing style...", "#22d3ee");

    try {
        const response = await fetch(`/posts/${currentPostId}/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: updatedContent })
        });

        if (!response.ok) throw new Error(`Server Error: ${response.status}`);

        const result = await response.json();

        // Switch back to rendered view
        editor.classList.add('hidden');
        document.getElementById('approve-container').classList.add('hidden');

        els.articlePane.innerHTML = marked.parse(result.content);
        els.articlePane.classList.remove('hidden');

        terminalLog("SUCCESS", "Success! The AI has learned from your changes.", "#22d3ee");

    } catch (err) {
        terminalLog("ERROR", `Training Failed: ${err.message}`, "#ef4444");
    } finally {
        btn.disabled = false;
        btn.innerHTML = `Save Edits & Improve AI Writing Style <span class="inline-block ml-2 group-hover:translate-x-1 transition-transform">→</span>`;
    }
});

function updateSEOAudit(content) {
    if (!content) return;

    // 1. Calculate Metrics
    const wordCount = content.split(/\s+/).length;
    const h2Count = (content.match(/^## /gm) || []).length;

    // 2. Detect "Data Blocks" (Tables or Lists)
    const hasTable = content.includes('|--') || content.includes('| :--');
    const hasList = (content.match(/^[*-] /gm) || []).length > 3;
    const hasDataBlocks = hasTable || hasList;

    // 3. Visual Scoring
    let score = 0;
    score += Math.min((wordCount / 2000) * 40, 40); // Word count weight
    score += Math.min((h2Count / 5) * 30, 30);      // Heading weight
    if (hasDataBlocks) score += 30;                 // Data block weight

    const finalScore = Math.round(score);
    const offset = 283 - (283 * Math.min(finalScore, 100)) / 100;

    els.scoreCircle.style.strokeDashoffset = offset;
    els.scoreText.innerText = `${Math.min(finalScore, 100)}%`;

    // 4. Update Audit Dots
    const lengthDot = document.querySelector('#audit-length .audit-dot');
    const entityDot = document.querySelector('#audit-entities .audit-dot');
    const visualDot = document.querySelector('#audit-visuals .audit-dot');

    if (lengthDot) lengthDot.style.background = wordCount > 1800 ? "#22d3ee" : "rgba(255,255,255,0.1)";
    if (entityDot) entityDot.style.background = h2Count >= 4 ? "#22d3ee" : "rgba(255,255,255,0.1)";
    if (visualDot) visualDot.style.background = hasDataBlocks ? "#22d3ee" : "rgba(255,255,255,0.1)";
    if (visualDot) visualDot.style.background = hasDataBlocks ? "#22d3ee" : "rgba(255,255,255,0.1)";
}

// -------------------------------------------------------------------------
// MODAL & CLARIFICATION LOGIC
// -------------------------------------------------------------------------
const modalEls = {
    modal: document.getElementById('clarify-modal'),
    panel: document.getElementById('clarify-panel'),
    loading: document.getElementById('clarify-loading'),
    form: document.getElementById('clarify-form'),
    container: document.getElementById('questions-container'),
    skipBtn: document.getElementById('clarify-skip-btn'),
    submitBtn: document.getElementById('clarify-submit-btn'),
    backdrop: document.getElementById('clarify-backdrop')
};

let currentQuestions = [];

function showModal() {
    modalEls.modal.classList.remove('hidden');
    // small delay to allow display block to apply before animating opacity
    setTimeout(() => {
        modalEls.panel.classList.remove('scale-95', 'opacity-0');
        modalEls.panel.classList.add('scale-100', 'opacity-100');
    }, 10);
}

function hideModal() {
    modalEls.panel.classList.remove('scale-100', 'opacity-100');
    modalEls.panel.classList.add('scale-95', 'opacity-0');
    setTimeout(() => {
        modalEls.modal.classList.add('hidden');
    }, 300); // match tailwind transition duration
}

modalEls.backdrop.addEventListener('click', hideModal);

modalEls.skipBtn.addEventListener('click', () => {
    hideModal();
    executeGeneration(""); // Generate with empty context
});

modalEls.submitBtn.addEventListener('click', () => {
    // Gather all answers
    let contextParts = [];
    const textareas = modalEls.container.querySelectorAll('textarea');
    textareas.forEach((ta, idx) => {
        const answer = ta.value.trim();
        if (answer) {
            contextParts.push(`Q: ${currentQuestions[idx]}\nA: ${answer}`);
        }
    });

    const finalContext = contextParts.join('\n\n');
    hideModal();
    executeGeneration(finalContext);
});

// MAIN EXECUTION TRIGGER (Step 1)
els.generateBtn.addEventListener('click', async () => {
    const kw = els.keywordInput.value.trim();
    if (!kw) return;

    els.generateBtn.disabled = true;

    // Reset UI State for new run
    els.terminal.innerHTML = "";
    els.articlePane.innerHTML = "";
    els.blueprintPane.innerHTML = "";
    els.articlePane.classList.add('hidden');
    updateAgentUI(null);

    // Show Modal Loading State
    modalEls.loading.classList.remove('hidden');
    modalEls.form.classList.add('hidden');
    showModal();

    terminalLog("SYSTEM", `Fetching briefing questions for: ${kw}...`, "#22d3ee");

    try {
        const response = await fetch(`/clarify?keyword=${encodeURIComponent(kw)}`);
        if (!response.ok) throw new Error("Failed to fetch questions");

        const data = await response.json();
        currentQuestions = data.questions || [];

        if (currentQuestions.length === 0) {
            // Fallback if AI fails to return questions
            hideModal();
            executeGeneration("");
            return;
        }

        // Render Questions in Modal
        modalEls.container.innerHTML = "";
        currentQuestions.forEach((q, idx) => {
            const block = document.createElement('div');
            block.className = 'bg-black/20 border border-white/5 rounded-xl p-4';
            block.innerHTML = `
                <label class="block text-sm font-medium text-slate-200 mb-2 leading-snug">${idx + 1}. ${q}</label>
                <textarea rows="2" class="w-full bg-white/5 border border-white/10 rounded-lg p-3 text-sm text-white placeholder-slate-600 outline-none focus:border-cyan-500/50 focus:bg-white/10 transition-all resize-none" placeholder="Type your answer here... (Optional)"></textarea>
            `;
            modalEls.container.appendChild(block);
        });

        modalEls.loading.classList.add('hidden');
        modalEls.form.classList.remove('hidden');
        terminalLog("SYSTEM", `Briefing agent ready. Awaiting user input.`, "#22d3ee");

    } catch (err) {
        terminalLog("ERROR", `Briefing Failed: ${err.message}. Skipping to generation...`, "#ef4444");
        hideModal();
        executeGeneration("");
    }
});

// MAIN GENERATION LOOP (Step 2)
async function executeGeneration(userContext) {
    const kw = els.keywordInput.value.trim();
    const rawNiche = els.nicheInput ? els.nicheInput.value.trim() : "";
    const niche = rawNiche ? rawNiche : "default";
    const profile = els.profileSelect ? els.profileSelect.value : "default";

    terminalLog("SYSTEM", `Compiling context and starting generation...`, "#22d3ee");

    try {
        const response = await fetch(`/generate/${encodeURIComponent(kw)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ niche: niche, context: userContext, profile_name: profile })
        });

        if (!response.ok) throw new Error(`Server Error: ${response.status}`);

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let done = false;

        while (!done) {
            const { value, done: readerDone } = await reader.read();
            done = readerDone;
            if (value) {
                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split('\n\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const jsonStr = line.replace('data: ', '').trim();
                        if (!jsonStr) continue;

                        try {
                            const payload = JSON.parse(jsonStr);

                            switch (payload.event) {
                                case 'debug':
                                    terminalLog("SYS-DEBUG", payload.message, "#fbbf24");
                                    break;
                                case 'phase1_start':
                                    updateAgentUI('research');
                                    terminalLog("ENGINE", payload.message, "#d946ef");
                                    break;
                                case 'phase2_start':
                                    updateAgentUI('psychology');
                                    terminalLog("PSYCHOLOGY", payload.message, "#d946ef");
                                    break;
                                case 'phase2_complete':
                                    renderBlueprint(payload.blueprint);
                                    terminalLog("PSYCHOLOGY", "Article strategy mapped.", "#d946ef");
                                    break;
                                case 'phase3_start':
                                    updateAgentUI('writer');
                                    terminalLog("WRITER", payload.message, "#22d3ee");
                                    break;
                                case 'complete':
                                    renderArticle(payload.post);
                                    updateSEOAudit(payload.post.content);
                                    terminalLog("SUCCESS", "Article successfully generated and checked!", "#22d3ee");
                                    break;
                                case 'error':
                                    terminalLog("ERROR", `Generation Failed: ${payload.message}`, "#ef4444");
                                    break;
                            }
                        } catch (e) {
                            console.error("Failed to parse SSE chunk:", jsonStr, e);
                        }
                    }
                }
            }
        }

    } catch (err) {
        terminalLog("ERROR", `Connection Failed: ${err.message}`, "#ef4444");
    } finally {
        els.generateBtn.disabled = false;
        updateAgentUI(null);
    }
}

// CLIPBOARD HANDLERS
document.getElementById('copy-md-btn').addEventListener('click', () => {
    if (!lastGeneratedMarkdown) return;
    navigator.clipboard.writeText(lastGeneratedMarkdown).then(() => {
        const btn = document.getElementById('copy-md-btn');
        btn.innerText = "COPIED!";
        setTimeout(() => btn.innerText = "Copy Markdown", 2000);
    });
});

document.getElementById('copy-html-btn').addEventListener('click', () => {
    const html = els.articlePane.innerHTML;
    if (!html) return;
    navigator.clipboard.writeText(html).then(() => {
        const btn = document.getElementById('copy-html-btn');
        btn.innerText = "COPIED!";
        setTimeout(() => btn.innerText = "Copy Rich Text", 2000);
    });
});

// --- AI BRAIN LOGIC ---
const brainEls = {
    modal: document.getElementById('brain-modal'),
    backdrop: document.getElementById('brain-backdrop'),
    panel: document.getElementById('brain-panel'),
    openBtn: document.getElementById('open-brain-btn'),
    closeBtn: document.getElementById('close-brain-btn'),
    container: document.getElementById('rules-container'),
    input: document.getElementById('new-rule-input'),
    addBtn: document.getElementById('add-rule-btn')
};

function toggleBrain(show) {
    if (show) {
        brainEls.modal.classList.remove('hidden');
        setTimeout(() => {
            brainEls.backdrop.classList.remove('opacity-0');
            brainEls.panel.classList.remove('translate-x-full');
        }, 10);
        loadRules();
    } else {
        brainEls.backdrop.classList.add('opacity-0');
        brainEls.panel.classList.add('translate-x-full');
        setTimeout(() => brainEls.modal.classList.add('hidden'), 500);
    }
}

brainEls.openBtn.addEventListener('click', () => toggleBrain(true));
brainEls.closeBtn.addEventListener('click', () => toggleBrain(false));
brainEls.backdrop.addEventListener('click', () => toggleBrain(false));

async function loadRules() {
    brainEls.container.innerHTML = '<div class="text-slate-500 text-xs text-center mono-text animate-pulse py-10">Accessing memory blocks...</div>';
    try {
        const profile = els.profileSelect ? els.profileSelect.value : "default";
        const res = await fetch('/rules?profile_name=' + profile);
        const rules = await res.json();

        if (rules.length === 0) {
            brainEls.container.innerHTML = `
                <div class="flex flex-col items-center justify-center py-20 opacity-30">
                    <svg class="w-12 h-12 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
                    <p class="text-xs mono-text">Memory Bank Empty</p>
                </div>
            `;
            return;
        }

        brainEls.container.innerHTML = rules.map(r => `
            <div class="group bg-white/[0.03] border border-white/5 rounded-2xl p-4 hover:bg-white/[0.05] hover:border-white/10 transition-all relative">
                <div class="flex gap-4 items-start">
                    <div class="w-1.5 h-1.5 rounded-full bg-cyan-500 mt-2 shrink-0 cyber-glow-cyan shadow-[0_0_8px_rgba(34,211,238,0.5)]"></div>
                    <p class="text-sm text-slate-300 leading-relaxed pr-8 font-medium">${r.rule_description}</p>
                </div>
                <button onclick="deleteRule(${r.id})" class="absolute top-4 right-4 text-slate-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                </button>
            </div>
        `).join('');
    } catch (e) {
        brainEls.container.innerHTML = '<div class="text-red-400/60 text-xs text-center p-10">Error: Failed to connect to Neural Bank.</div>';
    }
}

brainEls.addBtn.addEventListener('click', async () => {
    const text = brainEls.input.value.trim();
    if (!text) return;

    brainEls.addBtn.disabled = true;
    try {
        const profile = els.profileSelect ? els.profileSelect.value : "default";
        const res = await fetch('/rules', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({rule_description: text, profile_name: profile})
        });
        if (res.ok) {
            brainEls.input.value = '';
            loadRules();
        }
    } finally {
        brainEls.addBtn.disabled = false;
    }
});

async function deleteRule(id) {
    try {
        const res = await fetch(`/rules/${id}`, { method: 'DELETE' });
        if (res.ok) loadRules();
    } catch (e) {
        console.error("Failed to delete rule", e);
    }
}

els.profileSelect.addEventListener('change', () => {
    if (!brainEls.modal.classList.contains('hidden')) {
        loadRules();
    }
});

// -------------------------------------------------------------------------
// WORKSPACE CREATION MODAL LOGIC
// -------------------------------------------------------------------------
const wsEls = {
    overlay: document.getElementById('workspace-modal-overlay'),
    panel: document.getElementById('workspace-modal-panel'),
    input: document.getElementById('modal-workspace-input'),
    createBtn: document.getElementById('workspace-create-btn'),
    cancelBtn: document.getElementById('workspace-cancel-btn'),
    openBtn: document.getElementById('add-workspace-btn')
};

function toggleWorkspaceModal(isVisible) {
    if (isVisible) {
        wsEls.overlay.classList.remove('hidden');
        wsEls.input.value = '';
        setTimeout(() => {
            wsEls.panel.classList.remove('scale-95', 'opacity-0');
            wsEls.panel.classList.add('scale-100', 'opacity-100');
            wsEls.input.focus();
        }, 10);
    } else {
        wsEls.panel.classList.remove('scale-100', 'opacity-100');
        wsEls.panel.classList.add('scale-95', 'opacity-0');
        setTimeout(() => wsEls.overlay.classList.add('hidden'), 300);
    }
}

function createWorkspace() {
    const raw = wsEls.input.value.trim();
    if (!raw) return;

    const slug = raw.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
    if (!slug) return;

    // Prevent duplicates
    const existing = Array.from(els.profileSelect.options).find(o => o.value === slug);
    if (existing) {
        els.profileSelect.value = slug;
        els.profileSelect.dispatchEvent(new Event('change'));
        toggleWorkspaceModal(false);
        return;
    }

    const option = document.createElement('option');
    option.value = slug;
    option.textContent = `WORKSPACE: ${raw.toUpperCase()}`;
    option.className = 'bg-[#050505]';

    els.profileSelect.appendChild(option);
    els.profileSelect.value = slug;
    els.profileSelect.dispatchEvent(new Event('change'));

    toggleWorkspaceModal(false);
    terminalLog("SYSTEM", `Workspace "${raw}" created and activated.`, "#d946ef");
}

wsEls.openBtn.addEventListener('click', () => toggleWorkspaceModal(true));
wsEls.cancelBtn.addEventListener('click', () => toggleWorkspaceModal(false));
wsEls.overlay.addEventListener('click', (e) => {
    if (e.target === wsEls.overlay) toggleWorkspaceModal(false);
});
wsEls.createBtn.addEventListener('click', createWorkspace);
wsEls.input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') createWorkspace();
});
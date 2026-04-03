// ARES CONSOLE v4.0 - CYBER GLASS EXPERIMENT
window.addEventListener('error', (e) => {
    console.error("Global Trapped Error:", e.error);
    console.warn("UI Error (non-fatal): " + (e.message || "Unknown error occurred in console.js"));
});
let lastGeneratedMarkdown = "";
let currentAbortController = null;

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
        verify: document.getElementById('agent-verify'),
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
    // Desktop / Static nodes
    Object.values(els.agentNodes).forEach(node => node.classList.remove('agent-node-active'));
    if (activeNode && els.agentNodes[activeNode]) {
        els.agentNodes[activeNode].classList.add('agent-node-active');
    }
    
    // Mobile Toast Node
    const mobileToast = document.getElementById('mobile-agent-toast');
    const mobileText = document.getElementById('mobile-agent-text');
    
    if (mobileToast && mobileText) {
        if (!activeNode) {
            mobileToast.classList.add('opacity-0');
            mobileToast.classList.remove('opacity-100');
            mobileText.textContent = 'Standby';
        } else {
            let label = 'Working...';
            if (activeNode === 'research') label = 'Agent: Researching';
            if (activeNode === 'verify') label = 'Agent: Verifying Facts';
            if (activeNode === 'psychology') label = 'Agent: Strategizing';
            if (activeNode === 'writer') label = 'Agent: Writing Article';
            
            mobileText.textContent = label;
            mobileToast.classList.remove('opacity-0');
            mobileToast.classList.add('opacity-100');
        }
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
        const profile = els.profileSelect ? els.profileSelect.value : "default";
        const response = await fetch(`/posts/${currentPostId}/approve?profile_name=${encodeURIComponent(profile)}`, {
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

    // 1. Calculate Metrics (aligned with backend writer_service.verify_seo_score)
    const wordCount = content.split(/\s+/).length;
    const h1Count = (content.match(/^# (?!#)/gm) || []).length;
    const h2Count = (content.match(/^## (?!#)/gm) || []).length;

    // 2. Count distinct list/table blocks (matches backend writer_service.py state machine)
    const lines = content.split('\n');
    let dataBlockCount = 0;
    let inBlock = false;
    for (const line of lines) {
        const stripped = line.trim();
        const isListOrTable = /^[-*] /.test(stripped) ||
                              /^\d+\. /.test(stripped) ||
                              /^\|.+\|$/.test(stripped);
        if (isListOrTable && !inBlock) {
            dataBlockCount++;
            inBlock = true;
        } else if (!isListOrTable && stripped) {
            inBlock = false;
        }
    }

    // 3. Scoring aligned with backend validation gates
    let score = 0;
    const lengthOk = wordCount >= 1500;
    const h1Ok = h1Count === 1;
    const h2Ok = h2Count >= 5;
    const dataOk = dataBlockCount >= 3;

    // Weight: 25pts length, 25pts h1, 25pts structure, 25pts data blocks
    if (lengthOk) score += 25;
    else score += Math.min((wordCount / 1500) * 25, 24);

    if (h1Ok) score += 25;
    else score += 0;

    if (h2Ok) score += 25;
    else score += Math.min((h2Count / 5) * 25, 24);

    if (dataOk) score += 25;
    else score += Math.min((dataBlockCount / 3) * 25, 24);

    const finalScore = Math.round(score);
    const offset = 283 - (283 * Math.min(finalScore, 100)) / 100;

    els.scoreCircle.style.strokeDashoffset = offset;
    els.scoreText.innerText = `${Math.min(finalScore, 100)}%`;

    // 4. Update Audit Dots
    const lengthDot = document.querySelector('#audit-length .audit-dot');
    const h1Dot = document.querySelector('#audit-h1 .audit-dot');
    const entityDot = document.querySelector('#audit-entities .audit-dot');
    const visualDot = document.querySelector('#audit-visuals .audit-dot');

    if (lengthDot) lengthDot.style.background = lengthOk ? "#22d3ee" : "rgba(255,255,255,0.1)";
    if (h1Dot) h1Dot.style.background = h1Ok ? "#22d3ee" : "rgba(255,255,255,0.1)";
    if (entityDot) entityDot.style.background = h2Ok ? "#22d3ee" : "rgba(255,255,255,0.1)";
    if (visualDot) visualDot.style.background = dataOk ? "#22d3ee" : "rgba(255,255,255,0.1)";

    // 5. Backend-aligned pass/fail verdict
    const allPassed = lengthOk && h1Ok && h2Ok && dataOk;
    const verdictEl = document.querySelector('#seo-verdict');
    if (verdictEl) {
        verdictEl.innerText = allPassed ? 'PASS' : 'FAIL';
        verdictEl.style.color = allPassed ? '#22d3ee' : '#f87171';
    }
}

// -------------------------------------------------------------------------
// MODAL & CLARIFICATION LOGIC
// -------------------------------------------------------------------------

// Blueprint Modal Handlers
const blueprintModal = document.getElementById('blueprint-modal');
const openBlueprintBtn = document.getElementById('open-blueprint-btn');
const closeBlueprintBtn = document.getElementById('close-blueprint-btn');
const blueprintBackdrop = document.getElementById('blueprint-backdrop');
const blueprintPanel = document.getElementById('blueprint-panel');

if (openBlueprintBtn && blueprintModal) {
    openBlueprintBtn.addEventListener('click', () => {
        blueprintModal.classList.remove('hidden');
        setTimeout(() => {
            blueprintBackdrop.classList.remove('opacity-0');
            blueprintPanel.classList.remove('-translate-x-full');
        }, 10);
    });

    const closeBlueprint = () => {
        blueprintBackdrop.classList.add('opacity-0');
        blueprintPanel.classList.add('-translate-x-full');
        setTimeout(() => {
            blueprintModal.classList.add('hidden');
        }, 500);
    };

    closeBlueprintBtn.addEventListener('click', closeBlueprint);
    blueprintBackdrop.addEventListener('click', closeBlueprint);
}

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

    // CRITICAL: Clear ALL global state variables before new generation
    lastGeneratedMarkdown = "";
    currentPostId = null;
    currentQuestions = [];

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
    // CRITICAL: Ensure state is cleared even if user skips modal
    lastGeneratedMarkdown = "";
    currentPostId = null;

    const kw = els.keywordInput.value.trim();
    const rawNiche = els.nicheInput ? els.nicheInput.value.trim() : "";
    const niche = rawNiche ? rawNiche : "default";
    const profile = els.profileSelect ? els.profileSelect.value : "default";

    terminalLog("SYSTEM", `Compiling context and starting generation...`, "#22d3ee");

    // Abort any in-flight generation before starting a new one
    if (currentAbortController) currentAbortController.abort();
    currentAbortController = new AbortController();

    try {
        const response = await fetch(`/generate/${encodeURIComponent(kw)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ niche: niche, context: userContext, profile_name: profile }),
            signal: currentAbortController.signal,
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
                                case 'phase1_5_start':
                                    terminalLog("VERIFY", payload.message, "#a855f7");
                                    break;
                                case 'source_verification':
                                    const score = payload.credibility_score || 0;
                                    const scoreColor = score >= 80 ? "#10b981" : score >= 45 ? "#fbbf24" : "#ef4444";
                                    terminalLog("VERIFY", `${payload.source_title} (${payload.domain}) → ${score}/100 [${payload.progress}]`, scoreColor);
                                    break;
                                case 'phase1_5_complete':
                                    const avgCred = payload.avg_credibility || 0;
                                    const avgColor = avgCred >= 80 ? "#10b981" : avgCred >= 45 ? "#22d3ee" : "#fbbf24";
                                    terminalLog("VERIFY", `Sources verified: ${payload.verified_count} passed, ${payload.rejected_count} rejected (Avg: ${avgCred}/100)`, avgColor);
                                    break;
                                case 'phase1_5_warning':
                                    terminalLog("VERIFY", payload.message, "#facc15");
                                    break;
                                case 'source_backfill_start':
                                    terminalLog("BACKFILL", payload.message, "#f59e0b");
                                    break;
                                case 'source_backfill_complete':
                                    const bfColor = (payload.verified_count || 0) >= 3 ? "#10b981" : "#ef4444";
                                    terminalLog("BACKFILL", payload.message, bfColor);
                                    break;
                                case 'ai_detection':
                                    const aiColor = (payload.ai_probability || 0) >= 0.7 ? "#ef4444" : (payload.ai_probability || 0) >= 0.55 ? "#fbbf24" : "#10b981";
                                    terminalLog("AI-DETECT", payload.message, aiColor);
                                    break;
                                case 'fact_verification_start':
                                    updateAgentUI('verify');
                                    terminalLog("FACT-CHECK", payload.message, "#a855f7");
                                    break;
                                case 'fact_verification_progress':
                                    const fvpColor = payload.status === 'corroborated' ? "#10b981" : payload.status === 'unverifiable' ? "#fbbf24" : "#ef4444";
                                    terminalLog("FACT-CHECK", payload.message, fvpColor);
                                    break;
                                case 'fact_verification_complete':
                                    const fvcColor = (payload.unverifiable || 0) === 0 ? "#10b981" : "#fbbf24";
                                    terminalLog("FACT-CHECK", payload.message, fvcColor);
                                    break;
                                case 'claim_cross_ref':
                                    const cxrColor = (payload.fabricated || 0) === 0 ? "#10b981" : "#ef4444";
                                    terminalLog("CLAIM-VERIFY", payload.message, cxrColor);
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
                                    // CRITICAL: Clear editor for new article (prevents previous content bleed)
                                    els.articlePane.classList.add('hidden');
                                    const editorPrep = document.getElementById('article-editor');
                                    editorPrep.value = "";  // Explicitly clear previous article
                                    editorPrep.classList.remove('hidden');
                                    break;
                                case 'content':
                                    const streamEditor = document.getElementById('article-editor');
                                    if (!streamEditor) break;
                                    streamEditor.value += payload.data;
                                    streamEditor.scrollTop = streamEditor.scrollHeight;
                                    break;
                                case 'control':
                                    if (payload.action === 'retry_clear') {
                                        const clearEditor = document.getElementById('article-editor');
                                        if (clearEditor) {
                                            clearEditor.value = "";
                                            terminalLog("WRITER", "Retrying draft generation...", "#fbbf24");
                                        }
                                    }
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
        if (err.name === 'AbortError') {
            terminalLog("SYSTEM", "Generation aborted — new request started.", "#facc15");
        } else {
            terminalLog("ERROR", `Connection Failed: ${err.message}`, "#ef4444");
        }
    } finally {
        currentAbortController = null;
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

// --- ACTIVITY CONSOLE LOGIC ---
const consoleEls = {
    panel: document.getElementById('docked-console'),
    openBtn: document.getElementById('open-console-btn'),
    closeBtn: document.getElementById('close-docked-console-btn')
};

let isConsoleOpen = false;

function toggleConsole(show) {
    isConsoleOpen = show;
    if (show) {
        // Expand the docked console
        consoleEls.panel.classList.remove('h-0', 'opacity-0', 'mt-0', 'pointer-events-none');
        consoleEls.panel.classList.add('h-48', 'mt-4', 'opacity-100', 'pointer-events-auto');
        
        // Scroll to bottom of terminal when opened
        setTimeout(() => {
            if(els.terminal) els.terminal.scrollTop = els.terminal.scrollHeight;
        }, 300);
    } else {
        // Collapse the docked console
        consoleEls.panel.classList.remove('h-48', 'mt-4', 'opacity-100', 'pointer-events-auto');
        consoleEls.panel.classList.add('h-0', 'opacity-0', 'mt-0', 'pointer-events-none');
    }
}

// Toggle on click of the sidebar menu button
consoleEls.openBtn.addEventListener('click', () => {
    // If on mobile, typing to open the console should properly close the sidebar so it's not cluttered
    if (window.innerWidth < 768) {
        document.getElementById('left-sidebar').classList.remove('sidebar-mobile-active');
        const bd = document.getElementById('sidebar-backdrop');
        if(bd) {
            bd.classList.remove('opacity-100', 'pointer-events-auto');
            bd.classList.add('opacity-0', 'pointer-events-none');
        }
    }
    toggleConsole(!isConsoleOpen);
});

// Close button inside the console
consoleEls.closeBtn.addEventListener('click', () => toggleConsole(false));

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
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rule_description: text, profile_name: profile })
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
        const profile = els.profileSelect ? els.profileSelect.value : "default";
        const res = await fetch(`/rules/${id}?profile_name=${encodeURIComponent(profile)}`, { method: 'DELETE' });
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

async function syncWorkspaces() {
    try {
        const res = await fetch('/workspaces');
        if (!res.ok) throw new Error('Failed to fetch workspaces');
        const workspaces = await res.json();

        const list = document.getElementById('workspace-list');
        const triggerName = document.getElementById('current-workspace-name');
        const currentVal = els.profileSelect.value;
        
        list.innerHTML = '';

        // Add DEFAULT option
        const defaultItem = createWorkspaceItem({ name: 'DEFAULT', slug: 'default' }, currentVal === 'default');
        list.appendChild(defaultItem);

        workspaces.forEach(ws => {
            if (ws.slug === 'default') return;
            const item = createWorkspaceItem(ws, ws.slug === currentVal);
            list.appendChild(item);
        });

        // Update trigger display
        const activeWs = workspaces.find(w => w.slug === currentVal) || { name: 'DEFAULT' };
        triggerName.textContent = activeWs.name.toUpperCase();
        
    } catch (e) {
        console.error("Workspace sync error:", e);
    }
}

function createWorkspaceItem(ws, isActive) {
    const div = document.createElement('div');
    div.className = `workspace-option-item ${isActive ? 'active' : ''}`;
    div.textContent = ws.name.toUpperCase();
    div.dataset.slug = ws.slug;
    
    div.addEventListener('click', (e) => {
        e.stopPropagation();
        selectWorkspace(ws.slug, ws.name);
    });
    
    return div;
}

function selectWorkspace(slug, name) {
    els.profileSelect.value = slug;
    document.getElementById('current-workspace-name').textContent = name.toUpperCase();
    document.getElementById('workspace-options').classList.add('hidden');
    
    // Highlight active in list
    document.querySelectorAll('.workspace-option-item').forEach(item => {
        item.classList.toggle('active', item.dataset.slug === slug);
    });
    
    // Trigger existing change logic
    els.profileSelect.dispatchEvent(new Event('change'));
}

// Dropdown Toggle Logic
document.getElementById('workspace-dropdown-container').addEventListener('click', (e) => {
    // Don't toggle if we clicked the + button
    if (e.target.id === 'add-workspace-btn') return;
    
    const options = document.getElementById('workspace-options');
    const isHidden = options.classList.contains('hidden');
    
    // Close others
    options.classList.toggle('hidden');
});

// Close when clicking outside
document.addEventListener('click', (e) => {
    const container = document.getElementById('workspace-dropdown-container');
    if (!container.contains(e.target)) {
        document.getElementById('workspace-options').classList.add('hidden');
    }
});

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

async function createWorkspace() {
    const raw = wsEls.input.value.trim();
    if (!raw) return;

    const slug = raw.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
    if (!slug) return;

    // Prevent duplicates
    const existing = document.querySelector(`.workspace-option-item[data-slug="${slug}"]`);
    if (existing) {
        els.profileSelect.value = slug;
        els.profileSelect.dispatchEvent(new Event('change'));
        toggleWorkspaceModal(false);
        return;
    }

    try {
        wsEls.createBtn.disabled = true;

        // Persist to Neon DB
        const res = await fetch('/workspaces', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: raw, slug: slug })
        });

        if (!res.ok) throw new Error("Failed to save workspace");
        const ws = await res.json();

        // Update UI
        await syncWorkspaces();
        selectWorkspace(ws.slug, ws.name);

        toggleWorkspaceModal(false);
        terminalLog("SYSTEM", `Workspace "${ws.name}" created and saved to cloud.`, "#d946ef");
    } catch (e) {
        console.error("Workspace creation error:", e);
        terminalLog("SYSTEM", `Error creating workspace "${raw}".`, "#ef4444");
    } finally {
        wsEls.createBtn.disabled = false;
    }
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

// Run Initial Sync
syncWorkspaces();

// -------------------------------------------------------------------------
// CARTOGRAPHER LOGIC
// -------------------------------------------------------------------------

const cartEls = {
    modal: document.getElementById('cartographer-modal'),
    backdrop: document.getElementById('cartographer-backdrop'),
    panel: document.getElementById('cartographer-panel'),
    openBtn: document.getElementById('open-cartographer-btn'),
    closeBtn: document.getElementById('close-cartographer-btn'),
    input: document.getElementById('cartographer-topic-input'),
    nicheInput: document.getElementById('cartographer-niche-input'),
    mapBtn: document.getElementById('cartographer-map-btn'),
    loading: document.getElementById('cartographer-loading'),
    results: document.getElementById('cartographer-results'),
    empty: document.getElementById('cartographer-empty')
};

function toggleCartographer(show) {
    if (show) {
        cartEls.modal.classList.remove('hidden');
        setTimeout(() => {
            cartEls.backdrop.classList.remove('opacity-0');
            cartEls.panel.classList.remove('-translate-x-full');
        }, 10);
        loadCampaigns();
    } else {
        cartEls.backdrop.classList.add('opacity-0');
        cartEls.panel.classList.add('-translate-x-full');
        setTimeout(() => cartEls.modal.classList.add('hidden'), 500);
    }
}

cartEls.openBtn.addEventListener('click', () => toggleCartographer(true));
cartEls.closeBtn.addEventListener('click', () => toggleCartographer(false));
cartEls.backdrop.addEventListener('click', () => toggleCartographer(false));

els.profileSelect.addEventListener('change', () => {
    if (!cartEls.modal.classList.contains('hidden')) {
        loadCampaigns();
    }
});

function renderCampaign(campaign) {
    let html = `
    <div class="bg-black/40 border border-indigo-500/20 rounded-2xl overflow-hidden mb-8 shadow-lg">
        <!-- Pillar -->
        <div class="p-6 bg-indigo-900/10 border-b border-indigo-500/20 flex items-center justify-between">
            <div class="flex items-center gap-4">
                <div class="w-12 h-12 rounded-xl bg-indigo-500/20 flex items-center justify-center border border-indigo-500/40 text-indigo-400">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"></path></svg>
                </div>
                <div>
                    <h3 class="text-xs uppercase tracking-widest text-indigo-400 font-bold mb-1">Pillar Core</h3>
                    <div class="text-xl text-white font-bold">${campaign.pillar.keyword.toUpperCase()}</div>
                </div>
            </div>
            <div class="flex gap-4">
                <div class="text-right">
                    <div class="text-[10px] uppercase text-slate-500 tracking-widest">Diff</div>
                    <div class="text-white font-mono font-bold">${campaign.pillar.kd}</div>
                </div>
                <div class="text-right">
                    <div class="text-[10px] uppercase text-slate-500 tracking-widest">Vol</div>
                    <div class="text-emerald-400 font-mono font-bold">${campaign.pillar.vol.toLocaleString()}</div>
                </div>
            </div>
        </div>
        <!-- Spokes -->
        <div class="p-6 relative space-y-4">
            <div class="absolute left-10 top-0 bottom-6 w-px bg-indigo-500/10 line-tree"></div>`;

    if (campaign.spokes && campaign.spokes.length > 0) {
        campaign.spokes.forEach(spoke => {
            html += `
            <div class="relative pl-12">
                <!-- Connector Line -->
                <div class="absolute left-10 top-1/2 w-4 h-px bg-indigo-500/20 -translate-y-1/2 line-branch"></div>
                
                <div class="bg-white/[0.02] border border-white/5 hover:border-indigo-500/30 transition-colors rounded-xl p-4 flex items-center justify-between group">
                    <div>
                        <div class="flex items-center gap-3 mb-1">
                            <span class="text-sm font-bold text-slate-200 group-hover:text-indigo-300 transition-colors">${spoke.keyword}</span>
                            <span class="text-[10px] px-2 py-0.5 rounded bg-white/5 border border-white/10 uppercase tracking-widest text-slate-400 font-mono">${spoke.intent}</span>
                        </div>
                        <p class="text-xs text-slate-500 leading-snug">${spoke.angle}</p>
                    </div>
                    <div class="flex items-center gap-6">
                        <div class="text-right whitespace-nowrap hidden sm:block">
                            <div class="text-xs font-mono font-bold ${spoke.kd > 45 ? 'text-rose-400' : 'text-emerald-400'}">KD: ${spoke.kd}</div>
                            <div class="text-xs font-mono font-bold text-slate-400">VOL: ${spoke.vol.toLocaleString()}</div>
                        </div>
                        <button class="generate-spoke-btn shrink-0 w-10 h-10 rounded-full bg-indigo-500/10 hover:bg-indigo-500 border border-indigo-500/30 flex items-center justify-center text-indigo-400 hover:text-white transition-all shadow-[0_0_10px_rgba(99,102,241,0.1)] hover:shadow-[0_0_20px_rgba(99,102,241,0.5)]" data-keyword="${spoke.keyword}" title="Generate Article for this Spoke">
                            <svg class="w-4 h-4 ml-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"></path></svg>
                        </button>
                    </div>
                </div>
            </div>`;
        });
    }

    html += `</div></div>`;
    return html;
}

async function loadCampaigns() {
    try {
        const profile = els.profileSelect ? els.profileSelect.value : "default";
        const res = await fetch('/campaigns?profile_name=' + profile);
        if (!res.ok) throw new Error("Failed to load campaigns");
        const campaigns = await res.json();

        if (campaigns.length === 0) {
            cartEls.results.innerHTML = "";
            cartEls.results.classList.add('hidden');
            cartEls.empty.classList.remove('hidden');
            cartEls.loading.classList.add('hidden');
            return;
        }

        cartEls.empty.classList.add('hidden');
        cartEls.loading.classList.add('hidden');
        cartEls.results.classList.remove('hidden');

        let allHtml = "";
        campaigns.forEach(c => allHtml += renderCampaign(c));
        cartEls.results.innerHTML = allHtml;

        attachSpokeListeners();
    } catch (e) {
        console.error("Cartographer Load Error:", e);
    }
}

cartEls.mapBtn.addEventListener('click', async () => {
    const topic = cartEls.input.value.trim();
    if (!topic) return;

    cartEls.mapBtn.disabled = true;
    cartEls.empty.classList.add('hidden');
    cartEls.results.classList.add('hidden');
    cartEls.loading.classList.remove('hidden');

    try {
        const profile = els.profileSelect ? els.profileSelect.value : "default";
        const nicheContext = cartEls.nicheInput ? cartEls.nicheInput.value.trim() : "";
        const res = await fetch('/campaigns/plan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                seed_topic: topic,
                profile_name: profile,
                niche_context: nicheContext
            })
        });

        if (!res.ok) throw new Error("Failed to map campaign");
        const campaign = await res.json();

        // Setup UI for new campaign block on top
        cartEls.input.value = "";
        cartEls.loading.classList.add('hidden');
        cartEls.results.classList.remove('hidden');

        // Re-load all to ensure exact rendering ordering (could also prepend html)
        await loadCampaigns();

    } catch (e) {
        console.error("Cartographer Map Error:", e);
        cartEls.loading.classList.add('hidden');
        cartEls.empty.classList.remove('hidden');
        terminalLog("ERROR", "Failed to map campaign: " + e.message, "#ef4444");
    } finally {
        cartEls.mapBtn.disabled = false;
    }
});

function showConfirmModal(message, onConfirm) {
    const overlay = document.getElementById('confirm-modal-overlay');
    const panel = document.getElementById('confirm-modal-panel');
    const msgEl = document.getElementById('confirm-modal-message');
    const cancelBtn = document.getElementById('confirm-cancel-btn');
    const okBtn = document.getElementById('confirm-ok-btn');

    msgEl.textContent = message;
    overlay.classList.remove('hidden');
    setTimeout(() => { panel.classList.remove('scale-95', 'opacity-0'); panel.classList.add('scale-100', 'opacity-100'); }, 20);

    function close() {
        panel.classList.remove('scale-100', 'opacity-100');
        panel.classList.add('scale-95', 'opacity-0');
        setTimeout(() => overlay.classList.add('hidden'), 300);
        cancelBtn.removeEventListener('click', onCancel);
        okBtn.removeEventListener('click', onOk);
    }
    function onCancel() { close(); }
    function onOk() { close(); onConfirm(); }

    cancelBtn.addEventListener('click', onCancel);
    okBtn.addEventListener('click', onOk);
}

function attachSpokeListeners() {
    const btns = cartEls.results.querySelectorAll('.generate-spoke-btn');
    btns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            const kw = e.currentTarget.getAttribute('data-keyword');
            if (!kw) return;

            showConfirmModal(`Generate article for "${kw}"? This will start a new generation.`, () => {
                toggleCartographer(false);
                els.keywordInput.value = kw;
                els.generateBtn.click();
            });
        });
    });
}

// SIDEBAR TOGGLE LOGIC
const toggleSidebarBtn = document.getElementById('toggle-sidebar-btn');
const leftSidebar = document.getElementById('left-sidebar');
const sidebarBackdrop = document.getElementById('sidebar-backdrop');

function toggleSidebar() {
    if (!leftSidebar) return;
    
    const isMobile = window.innerWidth < 768; // Tailwind md breakpoint
    
    if (isMobile) {
        // Mobile execution: toggle slide-in active class and backdrop
        const isActive = leftSidebar.classList.contains('sidebar-mobile-active');
        if (isActive) {
            leftSidebar.classList.remove('sidebar-mobile-active');
            if (sidebarBackdrop) {
                sidebarBackdrop.classList.remove('opacity-100');
                sidebarBackdrop.classList.add('pointer-events-none');
            }
        } else {
            leftSidebar.classList.add('sidebar-mobile-active');
            if (sidebarBackdrop) {
                sidebarBackdrop.classList.remove('pointer-events-none');
                sidebarBackdrop.classList.add('opacity-100');
            }
        }
    } else {
        // Desktop execution: toggle width collapse
        leftSidebar.classList.toggle('sidebar-collapsed');
        if (leftSidebar.classList.contains('sidebar-collapsed')) {
            if (toggleSidebarBtn) {
                toggleSidebarBtn.classList.add('bg-[rgba(255,255,255,0.08)]');
                toggleSidebarBtn.classList.remove('bg-[rgba(255,255,255,0.03)]');
            }
        } else {
            if (toggleSidebarBtn) {
                toggleSidebarBtn.classList.add('bg-[rgba(255,255,255,0.03)]');
                toggleSidebarBtn.classList.remove('bg-[rgba(255,255,255,0.08)]');
            }
        }
    }
}

if (toggleSidebarBtn) toggleSidebarBtn.addEventListener('click', toggleSidebar);
if (sidebarBackdrop) sidebarBackdrop.addEventListener('click', toggleSidebar);

// Ensure sidebar reset on resize crossing the breakpoint
window.addEventListener('resize', () => {
    if (window.innerWidth >= 768 && leftSidebar && leftSidebar.classList.contains('sidebar-mobile-active')) {
        leftSidebar.classList.remove('sidebar-mobile-active');
        if (sidebarBackdrop) {
            sidebarBackdrop.classList.remove('opacity-100');
            sidebarBackdrop.classList.add('pointer-events-none');
        }
    }
});

// ===========================================================================
// Settings Panel
// ===========================================================================
const settingsEls = {
    modal: document.getElementById('settings-modal'),
    backdrop: document.getElementById('settings-backdrop'),
    panel: document.getElementById('settings-panel'),
    openBtn: document.getElementById('open-settings-btn'),
    closeBtn: document.getElementById('close-settings-btn'),
    container: document.getElementById('settings-container'),
    saveBtn: document.getElementById('save-settings-btn'),
    status: document.getElementById('settings-status'),
};

let settingsCache = {};       // Current merged settings from API
let settingsConfigurable = {}; // Metadata (type, min, max, choices, label, tooltip)
let settingsDirty = {};       // Only changed values

function toggleSettings(show) {
    if (!settingsEls.modal) return;
    if (show) {
        settingsEls.modal.classList.remove('hidden');
        setTimeout(() => {
            settingsEls.backdrop.classList.remove('opacity-0');
            settingsEls.panel.classList.remove('translate-x-full');
        }, 10);
        loadSettings();
    } else {
        settingsEls.backdrop.classList.add('opacity-0');
        settingsEls.panel.classList.add('translate-x-full');
        setTimeout(() => settingsEls.modal.classList.add('hidden'), 500);
    }
}

async function loadSettings() {
    const container = settingsEls.container;
    if (!container) return;
    container.innerHTML = '<div class="text-slate-500 text-xs text-center mono-text animate-pulse py-10">Loading settings...</div>';

    const profile = els.profileSelect ? els.profileSelect.value : 'default';
    try {
        const res = await fetch('/settings?profile_name=' + encodeURIComponent(profile));
        const data = await res.json();
        settingsCache = data.settings || {};
        settingsConfigurable = data.configurable || {};
        settingsDirty = {};
        renderSettings();
    } catch (e) {
        container.innerHTML = '<div class="text-red-400/60 text-xs text-center p-10">Failed to load settings.</div>';
    }
}

function renderSettings() {
    const container = settingsEls.container;
    if (!container) return;
    container.innerHTML = '';

    const keys = Object.keys(settingsConfigurable);
    // Group: booleans first, then sliders, then dropdowns
    const bools = keys.filter(k => settingsConfigurable[k].type === 'bool');
    const sliders = keys.filter(k => settingsConfigurable[k].type !== 'bool' && !settingsConfigurable[k].choices);
    const dropdowns = keys.filter(k => settingsConfigurable[k].choices);

    const ordered = [...bools, ...sliders, ...dropdowns];

    for (const key of ordered) {
        const meta = settingsConfigurable[key];
        const val = settingsDirty.hasOwnProperty(key) ? settingsDirty[key] : settingsCache[key];

        const row = document.createElement('div');
        row.className = 'setting-row';

        const labelGroup = document.createElement('div');
        labelGroup.className = 'setting-label-group';

        const label = document.createElement('span');
        label.className = 'setting-label';
        label.textContent = meta.label || key;
        labelGroup.appendChild(label);

        if (meta.tooltip) {
            const info = document.createElement('span');
            info.className = 'info-tooltip';
            info.setAttribute('data-tooltip', meta.tooltip);
            info.textContent = '\u24D8';
            labelGroup.appendChild(info);
        }

        row.appendChild(labelGroup);

        if (meta.type === 'bool') {
            const toggle = document.createElement('div');
            toggle.className = 'toggle-switch' + (val ? ' active' : '');
            toggle.addEventListener('click', () => {
                const newVal = !toggle.classList.contains('active');
                toggle.classList.toggle('active', newVal);
                settingsDirty[key] = newVal;
                updateSaveState();
            });
            row.appendChild(toggle);
        } else if (meta.choices) {
            const select = document.createElement('select');
            select.className = 'setting-select';
            for (const choice of meta.choices) {
                const opt = document.createElement('option');
                opt.value = choice;
                opt.textContent = choice;
                if (choice == val) opt.selected = true;
                select.appendChild(opt);
            }
            select.addEventListener('change', () => {
                settingsDirty[key] = meta.type === 'int' ? parseInt(select.value) : parseFloat(select.value);
                updateSaveState();
            });
            row.appendChild(select);
        } else {
            // Slider
            const sliderWrap = document.createElement('div');
            sliderWrap.style.display = 'flex';
            sliderWrap.style.alignItems = 'center';
            sliderWrap.style.gap = '8px';

            const slider = document.createElement('input');
            slider.type = 'range';
            slider.className = 'setting-slider';
            slider.min = meta.min;
            slider.max = meta.max;
            slider.step = meta.type === 'float' ? '0.5' : '1';
            slider.value = val;

            const valLabel = document.createElement('span');
            valLabel.className = 'text-xs mono-text text-[#8B8B93]';
            valLabel.style.minWidth = '32px';
            valLabel.style.textAlign = 'right';
            valLabel.textContent = val;

            slider.addEventListener('input', () => {
                const newVal = meta.type === 'float' ? parseFloat(slider.value) : parseInt(slider.value);
                valLabel.textContent = newVal;
                settingsDirty[key] = newVal;
                updateSaveState();
            });

            sliderWrap.appendChild(slider);
            sliderWrap.appendChild(valLabel);
            row.appendChild(sliderWrap);
        }

        container.appendChild(row);
    }
    updateSaveState();
}

function updateSaveState() {
    const hasChanges = Object.keys(settingsDirty).length > 0;
    if (settingsEls.saveBtn) {
        settingsEls.saveBtn.disabled = !hasChanges;
        settingsEls.saveBtn.style.opacity = hasChanges ? '1' : '0.4';
    }
    if (settingsEls.status) {
        settingsEls.status.textContent = hasChanges ? 'Unsaved changes' : '';
    }
}

async function saveSettings() {
    if (Object.keys(settingsDirty).length === 0) return;
    const profile = els.profileSelect ? els.profileSelect.value : 'default';

    if (settingsEls.status) settingsEls.status.textContent = 'Saving...';
    if (settingsEls.saveBtn) settingsEls.saveBtn.disabled = true;

    try {
        const res = await fetch('/settings?profile_name=' + encodeURIComponent(profile), {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settingsDirty),
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Save failed');
        }
        const data = await res.json();
        settingsCache = data.settings || {};
        settingsDirty = {};
        renderSettings();
        if (settingsEls.status) {
            settingsEls.status.textContent = 'Saved';
            setTimeout(() => { if (settingsEls.status) settingsEls.status.textContent = ''; }, 2000);
        }
    } catch (e) {
        if (settingsEls.status) settingsEls.status.textContent = 'Error: ' + e.message;
        if (settingsEls.saveBtn) {
            settingsEls.saveBtn.disabled = false;
            settingsEls.saveBtn.style.opacity = '1';
        }
    }
}

if (settingsEls.openBtn) settingsEls.openBtn.addEventListener('click', () => toggleSettings(true));
if (settingsEls.closeBtn) settingsEls.closeBtn.addEventListener('click', () => toggleSettings(false));
if (settingsEls.backdrop) settingsEls.backdrop.addEventListener('click', () => toggleSettings(false));
if (settingsEls.saveBtn) settingsEls.saveBtn.addEventListener('click', saveSettings);

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
    nicheSelect: document.getElementById('niche-select')
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
}

// MAIN EXECUTION
els.generateBtn.addEventListener('click', async () => {
    const kw = els.keywordInput.value.trim();
    if (!kw) return;

    const niche = els.nicheSelect ? els.nicheSelect.value : "default";

    els.generateBtn.disabled = true;
    els.terminal.innerHTML = "";
    els.articlePane.innerHTML = "";
    els.blueprintPane.innerHTML = "";
    els.articlePane.classList.add('hidden'); // Reset to interactive state if it was rendered

    terminalLog("SYSTEM", `Starting content generation for topic...`, "#22d3ee");

    try {
        const response = await fetch(`/generate/${encodeURIComponent(kw)}?niche=${encodeURIComponent(niche)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
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
});

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
// ARES CONSOLE v3.1.6 - FULL DATA SCAN
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
    }
};

function terminalLog(agent, message, color = "#71717a") {
    const entry = document.createElement('div');
    entry.className = "mb-1 border-l border-slate-800 pl-2 py-1 animate-fadeIn";
    entry.innerHTML = `<span style="color: ${color}; font-weight: bold;">[${agent}]</span> ${message}`;
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
    let html = `<div class="mb-6"><h3 class="text-magenta-400 font-bold text-sm uppercase tracking-widest">${audience}</h3></div>`;

    if (bp.outline_structure && Array.isArray(bp.outline_structure)) {
        html += `<div class="space-y-4">`;
        bp.outline_structure.forEach((item, idx) => {
            const heading = typeof item === 'object' ? (item.heading || item.title || "Section") : item;
            html += `<div class="p-3 bg-white/5 border border-white/5 rounded">
                        <span class="text-magenta-500 font-mono text-[10px] block mb-1">PHASE 0${idx + 1}</span>
                        <span class="text-slate-200 text-xs font-bold">${heading}</span>
                     </div>`;
        });
        html += `</div>`;
    }
    els.blueprintPane.innerHTML = html;
}

function renderArticle(post) {
    if (!post || !post.content) return;
    lastGeneratedMarkdown = post.content;
    if (typeof marked !== 'undefined') {
        els.articlePane.innerHTML = marked.parse(post.content);
    } else {
        els.articlePane.innerText = post.content;
    }
}

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

    // 4. Update Audit Dots (The fix for greyed out sections)
    const lengthDot = document.querySelector('#audit-length .audit-dot') || document.querySelector('#audit-length span');
    const entityDot = document.querySelector('#audit-entities .audit-dot') || document.querySelector('#audit-entities span');
    const visualDot = document.querySelector('#audit-visuals .audit-dot') || document.querySelector('#audit-visuals span');

    if (lengthDot) lengthDot.style.background = wordCount > 1800 ? "#00ff9d" : "#475569";
    if (entityDot) entityDot.style.background = h2Count >= 4 ? "#00ff9d" : "#475569";
    if (visualDot) visualDot.style.background = hasDataBlocks ? "#00ff9d" : "#475569";
}

// MAIN EXECUTION
els.generateBtn.addEventListener('click', async () => {
    const kw = els.keywordInput.value.trim();
    if (!kw) return;

    els.generateBtn.disabled = true;
    els.terminal.innerHTML = "";
    els.articlePane.innerHTML = "";
    els.blueprintPane.innerHTML = "";

    terminalLog("SYSTEM", "Requesting Unified Generation Sequence...", "#22d3ee");
    updateAgentUI('research');

    try {
        const response = await fetch(`/generate/${encodeURIComponent(kw)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (!response.ok) throw new Error(`Server Error: ${response.status}`);

        terminalLog("ENGINE", "Backend processing Research + Psychology + Content...", "#d946ef");

        const data = await response.json();

        updateAgentUI('psychology');
        renderBlueprint(data.blueprint);
        terminalLog("PSYCHOLOGY", "Strategic Blueprint mapped.", "#d946ef");

        updateAgentUI('writer');
        renderArticle(data.post);
        terminalLog("WRITER", "Content rendered.", "#00ff9d");

        updateSEOAudit(data.post.content);
        terminalLog("SUCCESS", "SEO Integrity Verified.", "#00ff9d");

    } catch (err) {
        terminalLog("ERROR", `Sequence Failed: ${err.message}`, "#ef4444");
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
        setTimeout(() => btn.innerText = "COPY MD", 2000);
    });
});

document.getElementById('copy-html-btn').addEventListener('click', () => {
    const html = els.articlePane.innerHTML;
    if (!html) return;
    navigator.clipboard.writeText(html).then(() => {
        const btn = document.getElementById('copy-html-btn');
        btn.innerText = "COPIED!";
        setTimeout(() => btn.innerText = "COPY HTML", 2000);
    });
});
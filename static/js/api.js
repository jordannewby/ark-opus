/* ── Ares Console — API Layer ───────────────────────────────────────── */

/**
 * Ping the backend health-check to verify Brave Search connectivity.
 * @returns {Promise<{status: string, brave_search: boolean}>}
 */
async function verifyMCPServer() {
    const resp = await fetch("/health", {
        method: "GET",
        signal: AbortSignal.timeout(8000),
    });
    if (!resp.ok) throw new Error(`Health check failed: ${resp.status}`);
    return resp.json();
}

/**
 * Trigger the full 3-phase generation pipeline.
 * @param {string} keyword
 * @returns {Promise<{post: object, blueprint: object}>}
 */
async function generateArticle(keyword) {
    const resp = await fetch(`/generate/${encodeURIComponent(keyword)}`, {
        method: "POST",
    });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || `Generation failed: ${resp.status}`);
    }
    return resp.json();
}

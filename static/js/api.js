/* DEPRECATED: This file is not loaded by ares_console.html.
   Health check functionality is handled inline in console.js.
   Retained for reference only. */
/* ── Ares Console — API Layer ───────────────────────────────────────── */

/**
 * Ping the backend health-check to verify DeepSeek + Exa.ai connectivity.
 * @returns {Promise<{status: string, exa_search: boolean, deepseek: boolean}>}
 */
async function verifyMCPServer() {
    const resp = await fetch("/health", {
        method: "GET",
        signal: AbortSignal.timeout(8000),
    });
    if (!resp.ok) throw new Error(`Health check failed: ${resp.status}`);
    return resp.json();
}

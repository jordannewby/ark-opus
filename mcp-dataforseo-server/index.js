#!/usr/bin/env node

/**
 * DataForSEO MCP Server
 *
 * Exposes DataForSEO API endpoints as MCP tools for Ark Opus ResearchAgent.
 * Communicates via stdio (standard input/output) using MCP protocol.
 *
 * Environment:
 *   - DATAFORSEO_LOGIN: DataForSEO API login (passed via env by app/main.py)
 *   - DATAFORSEO_PASSWORD: DataForSEO API password (passed via env by app/main.py)
 *   - Runs in stdio mode for MCP protocol communication
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { DataForSEOClient } from "./dataforseo-client.js";
import { registerTools } from "./tools.js";

// Read credentials from environment variables
const login = process.env.DATAFORSEO_LOGIN;
const password = process.env.DATAFORSEO_PASSWORD;

if (!login || !password) {
  console.error("ERROR: DataForSEO credentials required");
  console.error("Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD environment variables");
  process.exit(1);
}

// Initialize DataForSEO API client
let client;
try {
  client = new DataForSEOClient(login, password);
} catch (error) {
  console.error(`ERROR: Failed to initialize DataForSEO client: ${error.message}`);
  process.exit(1);
}

// Initialize MCP server
const server = new Server(
  {
    name: "dataforseo-mcp-server",
    version: "1.0.0"
  },
  {
    capabilities: {
      tools: {}
    }
  }
);

// Register all DataForSEO tools
registerTools(server, client);

// Error handling for server
server.onerror = (error) => {
  console.error("[MCP Server Error]", error);
};

process.on("SIGINT", async () => {
  await server.close();
  process.exit(0);
});

// Start stdio transport
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);

  // Server is now running and listening on stdio
  // It will process MCP requests from the Python client
}

main().catch((error) => {
  console.error("Fatal error starting MCP server:", error);
  process.exit(1);
});

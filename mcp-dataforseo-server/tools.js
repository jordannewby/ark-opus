/**
 * MCP Tool Definitions and Handlers for DataForSEO API
 *
 * Registers 3 tools used by Ares Engine ResearchAgent:
 * 1. dataforseo_labs_google_keyword_ideas - Keyword research with search volume
 * 2. serp_organic_live_advanced - SERP organic results with PAA, headers
 * 3. dataforseo_labs_content_analysis_summary_live - Content patterns from top 10 results
 */

import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";

/**
 * Register all DataForSEO MCP tools with the server
 * @param {Server} server - MCP Server instance
 * @param {DataForSEOClient} client - DataForSEO API client
 */
export function registerTools(server, client) {
  // Handler for tool execution
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const toolName = request.params.name;
    const args = request.params.arguments || {};

    try {
      let result;

      switch (toolName) {
        case "dataforseo_labs_google_keyword_ideas":
          result = await handleKeywordIdeas(client, args);
          break;

        case "serp_organic_live_advanced":
          result = await handleSerpOrganic(client, args);
          break;

        case "dataforseo_labs_content_analysis_summary_live":
          result = await handleContentAnalysis(client, args);
          break;

        default:
          throw new Error(`Unknown tool: ${toolName}`);
      }

      // Return MCP-formatted response
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result)
          }
        ]
      };
    } catch (error) {
      // Return error in MCP format
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify({
              error: error.message,
              tool: toolName,
              success: false
            })
          }
        ],
        isError: true
      };
    }
  });

  // Handler for listing available tools
  server.setRequestHandler(ListToolsRequestSchema, async () => {
    return {
      tools: [
        {
          name: "dataforseo_labs_google_keyword_ideas",
          description: "Get keyword ideas with search volume, competition, and related keywords from DataForSEO Labs",
          inputSchema: {
            type: "object",
            properties: {
              keywords: {
                type: "array",
                items: { type: "string" },
                description: "List of seed keywords to get ideas for"
              },
              location_code: {
                type: "integer",
                default: 2840,
                description: "Location code (2840 = United States)"
              },
              language_code: {
                type: "string",
                default: "en",
                description: "Language code"
              }
            },
            required: ["keywords"]
          }
        },
        {
          name: "serp_organic_live_advanced",
          description: "Get live SERP organic results including PAA, titles, snippets, and rankings from Google",
          inputSchema: {
            type: "object",
            properties: {
              keyword: {
                type: "string",
                description: "Target keyword to get SERP results for"
              },
              location_code: {
                type: "integer",
                default: 2840,
                description: "Location code (2840 = United States)"
              },
              language_code: {
                type: "string",
                default: "en",
                description: "Language code"
              },
              depth: {
                type: "integer",
                default: 10,
                description: "Number of SERP results to return (max 100)"
              }
            },
            required: ["keyword"]
          }
        },
        {
          name: "dataforseo_labs_content_analysis_summary_live",
          description: "Analyze content patterns from top SERP results: word count, heading structure, content types",
          inputSchema: {
            type: "object",
            properties: {
              keyword: {
                type: "string",
                description: "Target keyword to analyze content patterns for"
              },
              location_name: {
                type: "string",
                default: "United States",
                description: "Location name for SERP analysis"
              },
              language_code: {
                type: "string",
                default: "en",
                description: "Language code"
              },
              depth: {
                type: "integer",
                default: 10,
                description: "Number of top SERP results to analyze (max 100)"
              }
            },
            required: ["keyword"]
          }
        }
      ]
    };
  });
}

/**
 * Tool 1: Get keyword ideas with search volume and competition data
 */
async function handleKeywordIdeas(client, args) {
  const { keywords, location_code = 2840, language_code = "en" } = args;

  if (!keywords || !Array.isArray(keywords) || keywords.length === 0) {
    throw new Error("keywords parameter must be a non-empty array");
  }

  const result = await client.post("/dataforseo_labs/google/keyword_ideas/live", {
    keywords,
    location_code,
    language_code
  });

  return result;
}

/**
 * Tool 2: Get SERP organic results with People Also Ask, titles, snippets
 */
async function handleSerpOrganic(client, args) {
  const { keyword, location_code = 2840, language_code = "en", depth = 10 } = args;

  if (!keyword || typeof keyword !== "string") {
    throw new Error("keyword parameter must be a non-empty string");
  }

  const result = await client.post("/serp/google/organic/live/advanced", {
    keyword,
    location_code,
    language_code,
    depth: Math.min(depth, 100) // Cap at 100 max
  });

  return result;
}

/**
 * Tool 3: Analyze content patterns from top SERP results
 */
async function handleContentAnalysis(client, args) {
  const { keyword, location_name = "United States", language_code = "en", depth = 10 } = args;

  if (!keyword || typeof keyword !== "string") {
    throw new Error("keyword parameter must be a non-empty string");
  }

  const result = await client.post("/dataforseo_labs/google/content_analysis/summary/live", {
    keyword,
    location_name,
    language_code,
    depth: Math.min(depth, 100) // Cap at 100 max
  });

  return result;
}

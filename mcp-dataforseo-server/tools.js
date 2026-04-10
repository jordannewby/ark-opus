/**
 * MCP Tool Definitions and Handlers for DataForSEO API
 *
 * Registers 4 tools used by Ark Opus ResearchAgent:
 * 1. dataforseo_labs_google_keyword_ideas - Keyword research with search volume
 * 2. serp_organic_live_advanced - SERP organic results with PAA, headers
 * 3. dataforseo_labs_content_analysis_summary_live - Content patterns from top 10 results
 * 4. backlinks_summary - Domain authority (rank 0-1000) and spam score for credibility
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

        case "domain_rank_overview":
          result = await handleDomainRankOverview(client, args);
          break;

        case "dataforseo_onpage_instant_pages":
          result = await handleOnPageInstantPages(client, args);
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
        },
        {
          name: "domain_rank_overview",
          description: "Get domain authority metrics: keyword rankings (top 1/3/10 positions), estimated traffic value. Use for source credibility assessment.",
          inputSchema: {
            type: "object",
            properties: {
              targets: {
                type: "array",
                items: { type: "string" },
                description: "List of domains to check (e.g., ['nist.gov', 'example.com']). Max 10 per request."
              }
            },
            required: ["targets"]
          }
        },
        {
          name: "dataforseo_onpage_instant_pages",
          description: "Analyze competitor pages for SEO metrics: readability, content quality, performance, on-page score. Returns comprehensive competitor intelligence.",
          inputSchema: {
            type: "object",
            properties: {
              urls: {
                type: "array",
                items: { type: "string" },
                description: "List of competitor URLs to analyze (max 20 per request)"
              },
              enable_javascript: {
                type: "boolean",
                default: false,
                description: "Execute JavaScript (10x cost multiplier)"
              },
              store_raw_html: {
                type: "boolean",
                default: true,
                description: "Store HTML for later retrieval (free, enables H2 extraction)"
              }
            },
            required: ["urls"]
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

/**
 * Tool 4: Get domain rank overview via DataForSEO Labs (authority metrics)
 * Used by Phase 1.5 source verification for real domain authority signals.
 * Returns: top keyword positions, estimated traffic value, total ranked keywords.
 * Cost: ~$0.0001 per domain (DataForSEO Labs pricing)
 */
async function handleDomainRankOverview(client, args) {
  const { targets } = args;

  if (!targets || !Array.isArray(targets) || targets.length === 0) {
    throw new Error("targets parameter must be a non-empty array of domain strings");
  }

  // Cap at 10 domains per request to control costs
  const limitedTargets = targets.slice(0, 10);

  // Query each domain individually (DataForSEO Labs accepts one target per task)
  const tasks = limitedTargets.map(target => ({
    target,
    location_code: 2840,  // United States
    language_code: "en",
  }));

  const result = await client.post("/dataforseo_labs/google/domain_rank_overview/live", tasks[0]);

  // For batch: make parallel calls for remaining domains
  const summaries = [];

  // Process first domain from the initial call
  const firstTask = (result.tasks || [])[0];
  summaries.push(extractDomainMetrics(firstTask, limitedTargets[0]));

  // Process remaining domains
  for (let i = 1; i < limitedTargets.length; i++) {
    try {
      const r = await client.post("/dataforseo_labs/google/domain_rank_overview/live", tasks[i]);
      const task = (r.tasks || [])[0];
      summaries.push(extractDomainMetrics(task, limitedTargets[i]));
    } catch (e) {
      summaries.push({
        target: limitedTargets[i],
        top10_keywords: 0,
        etv: 0,
        total_keywords: 0,
        error: e.message,
      });
    }
  }

  return { summaries };
}

/**
 * Extract key authority metrics from DataForSEO Labs domain rank result
 */
function extractDomainMetrics(task, fallbackTarget) {
  if (!task || task.status_code !== 20000 || !task.result || !task.result[0]?.items?.[0]) {
    return {
      target: task?.data?.target || fallbackTarget,
      top10_keywords: 0,
      etv: 0,
      total_keywords: 0,
    };
  }

  const metrics = task.result[0].items[0].metrics?.organic || {};
  const pos1 = metrics.pos_1 || 0;
  const pos2_3 = metrics.pos_2_3 || 0;
  const pos4_10 = metrics.pos_4_10 || 0;

  return {
    target: task.data?.target || fallbackTarget,
    top10_keywords: pos1 + pos2_3 + pos4_10,
    top3_keywords: pos1 + pos2_3,
    etv: Math.round(metrics.etv || 0),
    total_keywords: metrics.count || 0,
  };
}

/**
 * Tool 5: Analyze competitor pages with On-Page Instant Pages API
 * Returns: readability scores, content quality, performance metrics, on-page score
 * Cost: $0.000125/page base (+ multipliers for JavaScript/browser rendering)
 */
async function handleOnPageInstantPages(client, args) {
  const { urls, enable_javascript = false, store_raw_html = true } = args;

  if (!urls || !Array.isArray(urls) || urls.length === 0) {
    throw new Error("urls parameter must be a non-empty array");
  }

  // Limit to 20 URLs (DataForSEO max per request)
  const limitedUrls = urls.slice(0, 20);

  // Build tasks array (one task per URL)
  const tasks = limitedUrls.map(url => ({
    url,
    enable_javascript,
    store_raw_html,
    custom_user_agent: "Mozilla/5.0 (compatible; ArkOpus/1.0; +https://example.com/bot)"
  }));

  const result = await client.post("/v3/on_page/instant_pages", tasks);

  // Extract key metrics from response
  const summaries = [];
  const responseTasks = result.tasks || [];

  for (let task of responseTasks) {
    if (!task.result || !task.result[0]) {
      summaries.push({
        url: task.data?.url || "unknown",
        error: task.status_message || "No result returned"
      });
      continue;
    }

    const pageData = task.result[0];
    summaries.push({
      url: pageData.url,
      onpage_score: pageData.onpage_score || 0,
      word_count: pageData.meta?.content?.plain_text_word_count || 0,
      readability: {
        flesch_kincaid: pageData.meta?.content?.automated_readability_index || null,
        ari: pageData.meta?.content?.automated_readability_index || null
      },
      content_quality: {
        title_consistency: pageData.meta?.content?.title_to_content_consistency || 0,
        description_consistency: pageData.meta?.content?.description_to_content_consistency || 0
      },
      performance: {
        lcp: pageData.page_timing?.largest_contentful_paint || null,
        fid: pageData.page_timing?.first_input_delay || null,
        cls: pageData.page_timing?.cumulative_layout_shift || null
      },
      technical_seo: {
        broken_links: pageData.checks?.broken_links || false,
        duplicate_meta: (pageData.meta?.duplicate_meta_tags || []).length > 0
      }
    });
  }

  return { competitors: summaries, total_analyzed: summaries.length };
}

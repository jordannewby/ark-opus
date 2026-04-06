from datetime import datetime

from pydantic import BaseModel, Field


class PostCreate(BaseModel):
    title: str = Field(max_length=500)
    content: str = Field(max_length=200000)


class PostUpdate(BaseModel):
    title: str | None = None
    content: str | None = None


class PostResponse(BaseModel):
    id: int
    title: str
    content: str
    original_ai_content: str | None = None
    human_edited_content: str | None = None
    readability_score: dict | None = None
    profile_name: str = "default"
    niche: str | None = None
    research_run_id: int | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class CompetitorHeader(BaseModel):
    source: str
    h2: str
    h3s: list[str]


class ResearchResponse(BaseModel):
    keyword: str
    information_gap: str | None = None
    competitor_headers: list[CompetitorHeader]
    people_also_ask: list[str]
    semantic_entities: list[str]
    on_page_metrics: dict | None = None
    backlink_authority: dict | None = None
    elite_competitors: list[dict] | None = None


class OutlineItem(BaseModel):
    heading: str
    psychological_goal: str
    information_gain_trigger: str

class BlueprintResponse(BaseModel):
    hook_strategy: str
    target_identity: str
    problem_statement: str
    agitation_points: list[str]
    identity_hooks: list[str]
    semantic_entity_map: list[dict] | dict
    outline_structure: list[OutlineItem]
    # Enriched fields
    entities: list[str] = []
    semantic_keywords: list[str] = []


class GenerateFullResponse(BaseModel):
    post: PostResponse
    blueprint: BlueprintResponse

# --- NEW: Payload for the Clarification / Generation Loop ---
class GeneratePayload(BaseModel):
    niche: str = Field(default="default", max_length=100)
    context: str = Field(default="", max_length=5000)
    profile_name: str = Field(default="default", max_length=50)


class StyleRuleCreate(BaseModel):
    rule_description: str = Field(max_length=2000)
    profile_name: str = Field(default="default", max_length=50)


class StyleRuleResponse(BaseModel):
    id: int
    rule_description: str
    profile_name: str = "default"

    model_config = {"from_attributes": True}

class ResearchRunCapture(BaseModel):
    keyword: str
    niche: str = "default"
    profile_name: str = "default"
    tool_sequence: list[str]
    iteration_count: int
    exa_queries: list[str] = []
    kd_values: list[dict] = []
    max_kd_used: int | None = None
    avg_kd: int | None = None
    entity_cluster: list[str] = []
    info_gap_text: str | None = None
    competitor_count: int = 0


class NichePlaybookResponse(BaseModel):
    niche: str
    playbook: dict
    runs_distilled: int
    version: int

    model_config = {"from_attributes": True}


class WorkspaceCreate(BaseModel):
    name: str = Field(max_length=50)
    slug: str = Field(max_length=50)

class WorkspaceResponse(BaseModel):
    id: int
    name: str
    slug: str
    
    model_config = {"from_attributes": True}


class CampaignCreateRequest(BaseModel):
    seed_topic: str
    profile_name: str = "default"
    niche_context: str = ""

class SpokeKeyword(BaseModel):
    keyword: str
    kd: int
    vol: int
    intent: str
    angle: str

class PillarKeyword(BaseModel):
    keyword: str
    kd: int
    vol: int

class CampaignResponse(BaseModel):
    id: int
    profile_name: str
    seed_topic: str
    pillar: PillarKeyword
    spokes: list[SpokeKeyword]
    created_at: datetime

    model_config = {"from_attributes": True}


class VerifiedSourceResponse(BaseModel):
    id: int
    research_run_id: int
    profile_name: str
    url: str
    title: str
    domain: str
    credibility_score: float
    domain_authority: int | None = None
    publish_date: datetime | None = None
    freshness_score: float | None = None
    internal_citations_count: int
    has_credible_citations: bool
    citation_urls_json: str | None = None
    is_academic: bool
    is_authoritative_domain: bool
    content_snippet: str | None = None
    verification_passed: bool
    rejection_reason: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProfileSettingsUpdate(BaseModel):
    claim_gate_hard_block: bool | None = None
    verify_qualitative_claims: bool | None = None
    dataforseo_content_analysis_enabled: bool | None = None
    debug_mode: bool | None = None
    source_credibility_threshold: float | None = None
    exa_num_results: int | None = None
    max_agentic_iterations: int | None = None
    cache_ttl_hours: int | None = None
    writer_max_tokens: int | None = None
    max_writer_attempts: int | None = None


class ProfileSettingsResponse(BaseModel):
    profile_name: str
    settings: dict
    configurable: dict  # CONFIGURABLE_SETTINGS metadata for frontend rendering

    model_config = {"from_attributes": True}


class FactCitationResponse(BaseModel):
    id: int
    verified_source_id: int
    research_run_id: int
    fact_text: str
    fact_type: str
    source_url: str
    source_title: str
    citation_anchor: str
    confidence_score: float
    created_at: datetime

    model_config = {"from_attributes": True}


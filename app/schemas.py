from datetime import datetime

from pydantic import BaseModel


class PostCreate(BaseModel):
    title: str
    content: str


class PostUpdate(BaseModel):
    title: str | None = None
    content: str | None = None


class PostResponse(BaseModel):
    id: int
    title: str
    content: str
    original_ai_content: str | None = None
    human_edited_content: str | None = None
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
    niche: str = "default"
    context: str = ""
    profile_name: str = "default"


class StyleRuleCreate(BaseModel):
    rule_description: str
    profile_name: str = "default"


class StyleRuleResponse(BaseModel):
    id: int
    rule_description: str
    
    model_config = {"from_attributes": True}

class WorkspaceCreate(BaseModel):
    name: str
    slug: str

class WorkspaceResponse(BaseModel):
    id: int
    name: str
    slug: str
    
    model_config = {"from_attributes": True}

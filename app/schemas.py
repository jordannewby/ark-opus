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
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class CompetitorHeader(BaseModel):
    source: str
    h2: str
    h3s: list[str]


class ResearchResponse(BaseModel):
    keyword: str
    competitor_headers: list[CompetitorHeader]
    people_also_ask: list[str]
    semantic_entities: list[str]


class OutlineItem(BaseModel):
    heading: str
    psychological_goal: str

class BlueprintResponse(BaseModel):
    hook_strategy: str
    problem_statement: str
    agitation_points: list[str]
    solution: str | None = None
    identity_hooks: list[str]
    outline_structure: list[OutlineItem]
    entities: list[str] = []
    semantic_keywords: list[str] = []


class GenerateFullResponse(BaseModel):
    post: PostResponse
    blueprint: BlueprintResponse

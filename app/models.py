from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_name: Mapped[str] = mapped_column(String(50), default="default", server_default="default")
    research_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    original_ai_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_edited_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())


class UserStyleRule(Base):
    __tablename__ = "user_style_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_name: Mapped[str] = mapped_column(String(50), default="default", server_default="default")
    rule_description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())


class ResearchCache(Base):
    __tablename__ = "research_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    keyword: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    result_json: Mapped[str] = mapped_column(Text)
    cache_ttl_hours: Mapped[int] = mapped_column(Integer, default=24)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())

class ResearchRun(Base):
    __tablename__ = "research_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    keyword: Mapped[str] = mapped_column(String(200), index=True)
    niche: Mapped[str] = mapped_column(String(100), index=True, default="default", server_default="default")
    profile_name: Mapped[str] = mapped_column(String(50), default="default", server_default="default")

    tool_sequence_json: Mapped[str] = mapped_column(Text)
    iteration_count: Mapped[int] = mapped_column(Integer, default=1)
    exa_queries_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    kd_values_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_kd_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_kd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    entity_cluster_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    info_gap_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    competitor_count: Mapped[int] = mapped_column(Integer, default=0)

    post_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(nullable=True)
    is_distilled: Mapped[bool] = mapped_column(default=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class NichePlaybook(Base):
    __tablename__ = "niche_playbooks"
    __table_args__ = (UniqueConstraint("profile_name", "niche", name="uix_profile_niche"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_name: Mapped[str] = mapped_column(String(50), index=True, default="default", server_default="default")
    niche: Mapped[str] = mapped_column(String(100), index=True)
    playbook_json: Mapped[str] = mapped_column(Text)
    runs_distilled: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())


class ContentCampaign(Base):
    __tablename__ = "content_campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_name: Mapped[str] = mapped_column(String(50), index=True, default="default", server_default="default")
    seed_topic: Mapped[str] = mapped_column(String(200))
    pillar_keyword: Mapped[str] = mapped_column(String(200))
    spoke_keywords_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)

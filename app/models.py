from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_name: Mapped[str] = mapped_column(String(50), index=True, default="default", server_default="default")
    niche: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    research_run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("research_runs.id", ondelete="SET NULL"), index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    original_ai_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_edited_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    readability_score: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Stores {"ari": 7.2, "fk": 8.1, "cli": 7.8}
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())


class UserStyleRule(Base):
    __tablename__ = "user_style_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_name: Mapped[str] = mapped_column(String(50), default="default", server_default="default")
    rule_description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())


class UserStyleRuleArchive(Base):
    __tablename__ = "user_style_rule_archives"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_name: Mapped[str] = mapped_column(String(50), index=True, default="default", server_default="default")
    rule_descriptions_json: Mapped[str] = mapped_column(Text)
    pruned_to_count: Mapped[int] = mapped_column(Integer)
    archived_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ResearchCache(Base):
    __tablename__ = "research_cache"
    __table_args__ = (UniqueConstraint("keyword", "profile_name", "niche", name="uix_cache_composite"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    keyword: Mapped[str] = mapped_column(String(200), index=True)
    profile_name: Mapped[str] = mapped_column(String(50), default="default", server_default="default")
    niche: Mapped[str] = mapped_column(String(100), default="default", server_default="default")
    result_json: Mapped[str] = mapped_column(Text)
    cache_ttl_hours: Mapped[int] = mapped_column(Integer, default=24)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())

class ResearchRun(Base):
    __tablename__ = "research_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    keyword: Mapped[str] = mapped_column(String(200), index=True)
    niche: Mapped[str] = mapped_column(String(100), index=True, default="default", server_default="default")
    profile_name: Mapped[str] = mapped_column(String(50), index=True, default="default", server_default="default")

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
    active: Mapped[bool] = mapped_column(default=True, server_default="true")  # Option 2: version rollback capability
    approved_for_use: Mapped[bool] = mapped_column(default=False, server_default="false")  # Option 3: human review gate
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())


class WriterRun(Base):
    __tablename__ = "writer_runs"
    __table_args__ = (UniqueConstraint("profile_name", "niche", "post_id", name="uix_writer_run"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_name: Mapped[str] = mapped_column(String(50), index=True, default="default", server_default="default")
    niche: Mapped[str] = mapped_column(String(100))
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)

    # Readability metrics at generation time (from Post.readability_score)
    ari_score: Mapped[float] = mapped_column(nullable=False)
    flesch_kincaid_score: Mapped[float] = mapped_column(nullable=False)
    coleman_liau_score: Mapped[float] = mapped_column(nullable=False)
    avg_sentence_length: Mapped[float] = mapped_column(nullable=False)

    # Quality signal - computed on /approve
    # Formula: (10.0 - ari_score) / 10.0 → Higher = closer to target
    # Example: ARI 7.2 → efficiency = 0.28 (28% below 10th grade)
    readability_efficiency: Mapped[float | None] = mapped_column(nullable=True)

    # Approval tracking
    human_approved: Mapped[bool] = mapped_column(default=False, server_default="false")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Claim verification telemetry
    claims_verified: Mapped[int | None] = mapped_column(Integer, nullable=True)
    claims_fabricated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    claims_uncited: Mapped[int | None] = mapped_column(Integer, nullable=True)
    claims_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    claim_gate_passed: Mapped[bool | None] = mapped_column(nullable=True)

    # Distillation state
    is_distilled: Mapped[bool] = mapped_column(default=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class WriterPlaybook(Base):
    __tablename__ = "writer_playbooks"
    __table_args__ = (UniqueConstraint("profile_name", "niche", name="uix_writer_playbook"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_name: Mapped[str] = mapped_column(String(50), index=True, default="default", server_default="default")
    niche: Mapped[str] = mapped_column(String(100), index=True)
    playbook_json: Mapped[str] = mapped_column(Text)
    runs_distilled: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(default=True, server_default="true")  # Option 2: version rollback capability
    approved_for_use: Mapped[bool] = mapped_column(default=False, server_default="false")  # Option 3: human review gate
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


class VerifiedSource(Base):
    __tablename__ = "verified_sources"
    __table_args__ = (UniqueConstraint("research_run_id", "url", name="uix_source_run"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    research_run_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    profile_name: Mapped[str] = mapped_column(String(50), default="default", server_default="default")

    # Source metadata
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    domain: Mapped[str] = mapped_column(String(200), nullable=False, index=True)

    # Credibility scoring
    credibility_score: Mapped[float] = mapped_column(nullable=False)  # 0.0-100.0
    domain_authority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publish_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    freshness_score: Mapped[float | None] = mapped_column(nullable=True)  # 0.0-1.0

    # Backlink verification
    internal_citations_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    has_credible_citations: Mapped[bool] = mapped_column(default=False, server_default="false")
    citation_urls_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # List of URLs cited

    # Content quality signals
    is_academic: Mapped[bool] = mapped_column(default=False, server_default="false")
    is_authoritative_domain: Mapped[bool] = mapped_column(default=False, server_default="false")  # .gov, .edu, research journals
    content_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)  # 500 chars for reference

    # Verification status
    verification_passed: Mapped[bool] = mapped_column(default=True, server_default="true")
    rejection_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FactCitation(Base):
    __tablename__ = "fact_citations"

    id: Mapped[int] = mapped_column(primary_key=True)
    verified_source_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    research_run_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Extracted fact
    fact_text: Mapped[str] = mapped_column(Text, nullable=False)  # "67% of SMBs report..."
    fact_type: Mapped[str] = mapped_column(String(50), nullable=False)  # stat, benchmark, case_study, expert_quote

    # Attribution
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    source_title: Mapped[str] = mapped_column(String(500), nullable=False)
    citation_anchor: Mapped[str] = mapped_column(String(200), nullable=False)  # "According to Gartner 2024"

    # Validation
    confidence_score: Mapped[float] = mapped_column(nullable=False)  # 0.0-1.0 (DeepSeek's confidence)
    source_credibility: Mapped[float | None] = mapped_column(nullable=True)  # Parent source score (60-100 scale)
    composite_score: Mapped[float | None] = mapped_column(nullable=True)  # Combined: (confidence*100 + source_cred)/2

    # Cross-source consensus (how many independent sources corroborate this fact)
    consensus_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    # Claim verification fields
    is_grounded: Mapped[bool] = mapped_column(default=True, server_default="true")
    grounding_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_verified: Mapped[bool] = mapped_column(default=True, server_default="true")
    verification_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Values: "corroborated", "corrected", "unverifiable", "trusted", "not_checked", "suspect", "ungrounded"
    corroboration_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ProfileSettings(Base):
    __tablename__ = "profile_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    settings_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=None, onupdate=func.now())


class DomainCredibilityCache(Base):
    """
    Domain-level credibility cache to reduce redundant DeepSeek API calls.

    Caches quality/integrity scores per domain-niche combination for 90 days.
    Cache hit = skip 2 DeepSeek Reasoner calls per source (~$0.0001 saved).
    Expected hit rate: ~40% in same niche.
    """
    __tablename__ = "domain_credibility_cache"
    __table_args__ = (UniqueConstraint("domain", "niche", name="uix_domain_niche"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    domain: Mapped[str] = mapped_column(String(200), index=True)
    niche: Mapped[str] = mapped_column(String(100), index=True)

    # Cached scoring results from DeepSeek Reasoner
    tier_level: Mapped[int] = mapped_column(Integer)  # From domain_tiers.py
    base_score: Mapped[float] = mapped_column()  # Domain + tier score
    integrity_score: Mapped[float | None] = mapped_column(nullable=True)  # Avg from past checks
    quality_score: Mapped[float | None] = mapped_column(nullable=True)  # Avg from past checks

    # Metadata
    check_count: Mapped[int] = mapped_column(Integer, default=1)  # How many times verified
    last_checked: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

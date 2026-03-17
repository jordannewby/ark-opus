import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from dotenv import load_dotenv

load_dotenv()

# We removed os.getenv to prevent rogue local environment variables from hijacking the connection.
# This strictly forces SQLAlchemy to use the Neon PostgreSQL cluster.
SQLALCHEMY_DATABASE_URL = "postgresql://neondb_owner:npg_A1WgoOpGKC5h@ep-red-grass-aiy3x0x0-pooler.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require"

# Added `pool_pre_ping=True` and `pool_recycle=300` to prevent drop connections with Serverless Postgres
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True, 
    pool_recycle=300,
    connect_args={"keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10, "keepalives_count": 5}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def migrate_research_cache():
    """One-time migration: Add profile_name and niche to research_cache."""
    from sqlalchemy import text, inspect
    inspector = inspect(engine)

    # Check if migration already applied
    if 'research_cache' not in inspector.get_table_names():
        return  # Table doesn't exist yet, will be created with correct schema

    columns = [col['name'] for col in inspector.get_columns('research_cache')]
    if 'profile_name' in columns:
        return  # Migration already applied

    with engine.begin() as conn:
        # Add new columns with default values
        conn.execute(text("ALTER TABLE research_cache ADD COLUMN profile_name VARCHAR(50) DEFAULT 'default'"))
        conn.execute(text("ALTER TABLE research_cache ADD COLUMN niche VARCHAR(100) DEFAULT 'default'"))
        # Drop old unique constraint
        conn.execute(text("ALTER TABLE research_cache DROP CONSTRAINT IF EXISTS research_cache_keyword_key"))
        # Add composite unique constraint
        conn.execute(text("ALTER TABLE research_cache ADD CONSTRAINT uix_cache_composite UNIQUE (keyword, profile_name, niche)"))

def migrate_posts_readability():
    """One-time migration: Add readability_score JSON column to posts."""
    from sqlalchemy import text, inspect

    inspector = inspect(engine)

    # Check if posts table exists
    if 'posts' not in inspector.get_table_names():
        return  # Table doesn't exist yet, will be created with column

    # Check if column already exists
    columns = [col['name'] for col in inspector.get_columns('posts')]
    if 'readability_score' in columns:
        return  # Already migrated

    # Add the column
    with engine.begin() as conn:
        conn.execute(text("""
            ALTER TABLE posts
            ADD COLUMN readability_score JSONB DEFAULT NULL
        """))
        print("[OK] Added readability_score column to posts table")

def migrate_writer_learning():
    """One-time migration: Add writer_runs and writer_playbooks tables, and niche column to posts."""
    from sqlalchemy import text, inspect

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    # Check if posts.niche column exists
    if 'posts' in existing_tables:
        columns = [col['name'] for col in inspector.get_columns('posts')]
        if 'niche' not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE posts ADD COLUMN niche VARCHAR(100) DEFAULT NULL"))
                print("[OK] Added niche column to posts table")

    # Check if already migrated
    if 'writer_runs' in existing_tables and 'writer_playbooks' in existing_tables:
        return

    with engine.begin() as conn:
        if 'writer_runs' not in existing_tables:
            conn.execute(text("""
                CREATE TABLE writer_runs (
                    id SERIAL PRIMARY KEY,
                    profile_name VARCHAR(50) NOT NULL DEFAULT 'default',
                    niche VARCHAR(100) NOT NULL,
                    post_id INTEGER NOT NULL,
                    ari_score FLOAT NOT NULL,
                    flesch_kincaid_score FLOAT NOT NULL,
                    coleman_liau_score FLOAT NOT NULL,
                    avg_sentence_length FLOAT NOT NULL,
                    readability_efficiency FLOAT,
                    human_approved BOOLEAN DEFAULT FALSE,
                    approved_at TIMESTAMP,
                    is_distilled BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT uix_writer_run UNIQUE (profile_name, niche, post_id)
                )
            """))
            print("[OK] Created writer_runs table")

        if 'writer_playbooks' not in existing_tables:
            conn.execute(text("""
                CREATE TABLE writer_playbooks (
                    id SERIAL PRIMARY KEY,
                    profile_name VARCHAR(50) NOT NULL DEFAULT 'default',
                    niche VARCHAR(100) NOT NULL,
                    playbook_json TEXT NOT NULL,
                    runs_distilled INTEGER DEFAULT 0,
                    version INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP,
                    CONSTRAINT uix_writer_playbook UNIQUE (profile_name, niche)
                )
            """))
            print("[OK] Created writer_playbooks table")

def migrate_source_verification():
    """One-time migration: Add source verification tables (verified_sources, fact_citations)."""
    from sqlalchemy import text, inspect

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    # Check if already migrated
    if 'verified_sources' in existing_tables and 'fact_citations' in existing_tables:
        return

    with engine.begin() as conn:
        if 'verified_sources' not in existing_tables:
            conn.execute(text("""
                CREATE TABLE verified_sources (
                    id SERIAL PRIMARY KEY,
                    research_run_id INTEGER NOT NULL,
                    profile_name VARCHAR(50) NOT NULL DEFAULT 'default',
                    url VARCHAR(500) NOT NULL,
                    title VARCHAR(500) NOT NULL,
                    domain VARCHAR(200) NOT NULL,
                    credibility_score FLOAT NOT NULL,
                    domain_authority INTEGER,
                    publish_date TIMESTAMP,
                    freshness_score FLOAT,
                    internal_citations_count INTEGER DEFAULT 0,
                    has_credible_citations BOOLEAN DEFAULT FALSE,
                    citation_urls_json TEXT,
                    is_academic BOOLEAN DEFAULT FALSE,
                    is_authoritative_domain BOOLEAN DEFAULT FALSE,
                    content_snippet TEXT,
                    verification_passed BOOLEAN DEFAULT TRUE,
                    rejection_reason VARCHAR(200),
                    created_at TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT uix_source_run UNIQUE (research_run_id, url)
                )
            """))
            conn.execute(text("CREATE INDEX idx_verified_sources_research_run_id ON verified_sources(research_run_id)"))
            conn.execute(text("CREATE INDEX idx_verified_sources_domain ON verified_sources(domain)"))
            print("[OK] Created verified_sources table")

        if 'fact_citations' not in existing_tables:
            conn.execute(text("""
                CREATE TABLE fact_citations (
                    id SERIAL PRIMARY KEY,
                    verified_source_id INTEGER NOT NULL,
                    research_run_id INTEGER NOT NULL,
                    fact_text TEXT NOT NULL,
                    fact_type VARCHAR(50) NOT NULL,
                    source_url VARCHAR(500) NOT NULL,
                    source_title VARCHAR(500) NOT NULL,
                    citation_anchor VARCHAR(200) NOT NULL,
                    confidence_score FLOAT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            conn.execute(text("CREATE INDEX idx_fact_citations_verified_source_id ON fact_citations(verified_source_id)"))
            conn.execute(text("CREATE INDEX idx_fact_citations_research_run_id ON fact_citations(research_run_id)"))
            print("[OK] Created fact_citations table")


def migrate_composite_scoring():
    """One-time migration: Add composite scoring columns to fact_citations."""
    from sqlalchemy import text, inspect

    inspector = inspect(engine)

    # Check if fact_citations table exists
    if 'fact_citations' not in inspector.get_table_names():
        return  # Table doesn't exist yet

    # Check if columns already exist
    columns = [col['name'] for col in inspector.get_columns('fact_citations')]
    if 'source_credibility' in columns and 'composite_score' in columns:
        return  # Already migrated

    with engine.begin() as conn:
        # Add source_credibility column if missing
        if 'source_credibility' not in columns:
            conn.execute(text("""
                ALTER TABLE fact_citations
                ADD COLUMN source_credibility FLOAT DEFAULT NULL
            """))
            print("[OK] Added source_credibility column to fact_citations")

        # Add composite_score column if missing
        if 'composite_score' not in columns:
            conn.execute(text("""
                ALTER TABLE fact_citations
                ADD COLUMN composite_score FLOAT DEFAULT NULL
            """))
            print("[OK] Added composite_score column to fact_citations")

        # Backfill existing citations with composite scores
        conn.execute(text("""
            UPDATE fact_citations fc
            SET source_credibility = vs.credibility_score,
                composite_score = (fc.confidence_score * 100 + vs.credibility_score) / 2
            FROM verified_sources vs
            WHERE fc.verified_source_id = vs.id
            AND fc.composite_score IS NULL
        """))
        print("[OK] Backfilled composite scores for existing fact_citations")

def migrate_fact_consensus():
    """One-time migration: Add consensus_count column to fact_citations."""
    from sqlalchemy import text, inspect

    inspector = inspect(engine)

    if 'fact_citations' not in inspector.get_table_names():
        return  # Table doesn't exist yet

    columns = [col['name'] for col in inspector.get_columns('fact_citations')]
    if 'consensus_count' in columns:
        return  # Already migrated

    with engine.begin() as conn:
        conn.execute(text("""
            ALTER TABLE fact_citations
            ADD COLUMN consensus_count INTEGER DEFAULT 1
        """))
        print("[OK] Added consensus_count column to fact_citations")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

import logging
import os
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")
if not SQLALCHEMY_DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required. Set it in .env")

# Added `pool_pre_ping=True` and `pool_recycle` to prevent drop connections with Serverless Postgres
from .settings import DB_POOL_RECYCLE

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=DB_POOL_RECYCLE,
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
        logger.info("[OK] Added readability_score column to posts table")

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
                logger.info("[OK] Added niche column to posts table")

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
            logger.info("[OK] Created writer_runs table")

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
            logger.info("[OK] Created writer_playbooks table")

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
            logger.info("[OK] Created verified_sources table")

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
            logger.info("[OK] Created fact_citations table")


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
            logger.info("[OK] Added source_credibility column to fact_citations")

        # Add composite_score column if missing
        if 'composite_score' not in columns:
            conn.execute(text("""
                ALTER TABLE fact_citations
                ADD COLUMN composite_score FLOAT DEFAULT NULL
            """))
            logger.info("[OK] Added composite_score column to fact_citations")

        # Backfill existing citations with composite scores
        conn.execute(text("""
            UPDATE fact_citations fc
            SET source_credibility = vs.credibility_score,
                composite_score = (fc.confidence_score * 100 + vs.credibility_score) / 2
            FROM verified_sources vs
            WHERE fc.verified_source_id = vs.id
            AND fc.composite_score IS NULL
        """))
        logger.info("[OK] Backfilled composite scores for existing fact_citations")

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
        logger.info("[OK] Added consensus_count column to fact_citations")


def migrate_domain_credibility_cache():
    """One-time migration: Create domain_credibility_cache table for cost optimization."""
    from sqlalchemy import text, inspect

    inspector = inspect(engine)

    if 'domain_credibility_cache' in inspector.get_table_names():
        return  # Already exists

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE domain_credibility_cache (
                id SERIAL PRIMARY KEY,
                domain VARCHAR(200) NOT NULL,
                niche VARCHAR(100) NOT NULL,
                tier_level INTEGER NOT NULL,
                base_score FLOAT NOT NULL,
                integrity_score FLOAT,
                quality_score FLOAT,
                check_count INTEGER DEFAULT 1,
                last_checked TIMESTAMP DEFAULT NOW(),
                created_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT uix_domain_niche UNIQUE (domain, niche)
            )
        """))
        conn.execute(text("""
            CREATE INDEX idx_domain_credibility_domain ON domain_credibility_cache(domain)
        """))
        conn.execute(text("""
            CREATE INDEX idx_domain_credibility_niche ON domain_credibility_cache(niche)
        """))
        logger.info("[OK] Created domain_credibility_cache table with indexes")


def migrate_fact_verification():
    """One-time migration: Add claim verification columns to fact_citations."""
    from sqlalchemy import text, inspect

    inspector = inspect(engine)

    if 'fact_citations' not in inspector.get_table_names():
        return  # Table doesn't exist yet

    columns = [col['name'] for col in inspector.get_columns('fact_citations')]

    new_columns = {
        'is_grounded': "BOOLEAN DEFAULT TRUE",
        'grounding_method': "VARCHAR(50) DEFAULT NULL",
        'is_verified': "BOOLEAN DEFAULT TRUE",
        'verification_status': "VARCHAR(50) DEFAULT NULL",
        'corroboration_url': "VARCHAR(500) DEFAULT NULL",
    }

    added = []
    with engine.begin() as conn:
        for col_name, col_def in new_columns.items():
            if col_name not in columns:
                conn.execute(text(f"ALTER TABLE fact_citations ADD COLUMN {col_name} {col_def}"))
                added.append(col_name)

    if added:
        logger.info(f"[OK] Added claim verification columns to fact_citations: {', '.join(added)}")


def migrate_style_rule_archive():
    """One-time migration: Add user_style_rule_archives table."""
    from sqlalchemy import text, inspect

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    if 'user_style_rule_archives' in existing_tables:
        return

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE user_style_rule_archives (
                id SERIAL PRIMARY KEY,
                profile_name VARCHAR(50) NOT NULL DEFAULT 'default',
                rule_descriptions_json TEXT NOT NULL,
                pruned_to_count INTEGER NOT NULL,
                archived_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text("CREATE INDEX idx_style_archive_profile ON user_style_rule_archives(profile_name)"))
        logger.info("[OK] Created user_style_rule_archives table")


def migrate_writer_verification_telemetry():
    """One-time migration: Add claim verification telemetry columns to writer_runs."""
    from sqlalchemy import text, inspect

    inspector = inspect(engine)

    if 'writer_runs' not in inspector.get_table_names():
        return  # Table doesn't exist yet

    columns = [col['name'] for col in inspector.get_columns('writer_runs')]

    new_columns = {
        'claims_verified': "INTEGER DEFAULT NULL",
        'claims_fabricated': "INTEGER DEFAULT NULL",
        'claims_uncited': "INTEGER DEFAULT NULL",
        'claims_total': "INTEGER DEFAULT NULL",
        'claim_gate_passed': "BOOLEAN DEFAULT NULL",
    }

    added = []
    with engine.begin() as conn:
        for col_name, col_def in new_columns.items():
            if col_name not in columns:
                conn.execute(text(f"ALTER TABLE writer_runs ADD COLUMN {col_name} {col_def}"))
                added.append(col_name)

    if added:
        logger.info(f"[OK] Added verification telemetry columns to writer_runs: {', '.join(added)}")


def migrate_profile_settings():
    """One-time migration: Create profile_settings table for runtime configuration."""
    from sqlalchemy import text, inspect

    inspector = inspect(engine)

    if 'profile_settings' in inspector.get_table_names():
        return  # Already exists

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE profile_settings (
                id SERIAL PRIMARY KEY,
                profile_name VARCHAR(50) NOT NULL UNIQUE,
                settings_json TEXT NOT NULL DEFAULT '{}',
                updated_at TIMESTAMP DEFAULT NULL
            )
        """))
        conn.execute(text("CREATE UNIQUE INDEX idx_profile_settings_name ON profile_settings(profile_name)"))
        logger.info("[OK] Created profile_settings table")


def migrate_fk_constraints():
    """Add foreign key constraints to posts.research_run_id and writer_runs.post_id."""
    with engine.connect() as conn:
        # Check if FK already exists to avoid duplicate
        result = conn.execute(text("""
            SELECT 1 FROM information_schema.table_constraints
            WHERE constraint_name = 'fk_posts_research_run_id'
            AND table_name = 'posts'
        """))
        if result.fetchone():
            return  # Already exists

        # Clean up orphaned references before adding FK
        conn.execute(text("""
            UPDATE posts SET research_run_id = NULL
            WHERE research_run_id IS NOT NULL
            AND research_run_id NOT IN (SELECT id FROM research_runs)
        """))
        conn.execute(text("""
            DELETE FROM writer_runs
            WHERE post_id NOT IN (SELECT id FROM posts)
        """))
        conn.commit()

        try:
            conn.execute(text("""
                ALTER TABLE posts
                ADD CONSTRAINT fk_posts_research_run_id
                FOREIGN KEY (research_run_id) REFERENCES research_runs(id) ON DELETE SET NULL
            """))
            conn.commit()
            logger.info("[OK] Added FK constraint: posts.research_run_id -> research_runs.id")
        except Exception as e:
            logger.warning(f"[SKIP] posts FK constraint: {e}")
            conn.rollback()

        try:
            conn.execute(text("""
                ALTER TABLE writer_runs
                ADD CONSTRAINT fk_writer_runs_post_id
                FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
            """))
            conn.commit()
            logger.info("[OK] Added FK constraint: writer_runs.post_id -> posts.id")
        except Exception as e:
            logger.warning(f"[SKIP] writer_runs FK constraint: {e}")
            conn.rollback()


def migrate_version_tracking():
    """Create migration_history table to track applied migrations."""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'migration_history'
            )
        """))
        if result.scalar():
            return

        conn.execute(text("""
            CREATE TABLE migration_history (
                id SERIAL PRIMARY KEY,
                migration_name VARCHAR(200) NOT NULL UNIQUE,
                applied_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.commit()
        logger.info("[OK] Created migration_history table")


def _record_migration(name: str):
    """Record a migration as applied in migration_history. Idempotent (ON CONFLICT DO NOTHING)."""
    try:
        with engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO migration_history (migration_name) VALUES (:name) ON CONFLICT DO NOTHING"
            ), {"name": name})
            conn.commit()
    except Exception:
        pass  # Table may not exist yet on first run


def record_all_migrations():
    """Seed migration_history with all known migrations. Called after migrate_version_tracking()."""
    migrations = [
        "migrate_research_cache",
        "migrate_posts_readability",
        "migrate_writer_learning",
        "migrate_source_verification",
        "migrate_composite_scoring",
        "migrate_fact_consensus",
        "migrate_domain_credibility_cache",
        "migrate_fact_verification",
        "migrate_style_rule_archive",
        "migrate_writer_verification_telemetry",
        "migrate_profile_settings",
        "migrate_version_tracking",
        "migrate_fk_constraints",
    ]
    for name in migrations:
        _record_migration(name)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_db_alive(db):
    """Ping the connection; if Neon killed it during a long async gap, return a fresh session."""
    try:
        db.execute(text("SELECT 1"))
        return db
    except OperationalError:
        logger.warning("[DB-REFRESH] Stale connection detected, creating fresh session")
        try:
            db.rollback()
        except Exception:
            pass
        db.close()
        return SessionLocal()

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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

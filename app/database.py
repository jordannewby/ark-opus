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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

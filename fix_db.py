from app.database import engine
from sqlalchemy import text

with engine.begin() as conn:
    try:
        conn.execute(text("ALTER TABLE posts ADD COLUMN updated_at TIMESTAMP;"))
        print("Successfully added updated_at to posts.")
    except Exception as e:
        print(f"Error adding updated_at: {e}")

"""Database verification and initialization script."""
import sys
import logging
from sqlalchemy import text
from app.core.database import init_db, engine
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("init_db")

def main():
    print(f"Connecting to: {settings.DATABASE_URL}")
    init_db()
    
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;"
        )).fetchall()
        tables = [row[0] for row in result]
        print(f"Successfully verified {len(tables)} tables in PostgreSQL:")
        for t in tables:
            print(f"  - {t}")

if __name__ == "__main__":
    main()

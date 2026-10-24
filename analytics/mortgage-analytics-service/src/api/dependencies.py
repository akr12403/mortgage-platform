import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

DB_USER = os.getenv("POSTGRES_USER", "mortgage_app")
# REQUIRED (DP-GAP-2, M6 Task 6.6): no default. validate_db_settings() stops startup when it is missing.
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "mortgage_intel")

# URL.create escapes special characters in the password (an f-string URL breaks on "@", ":" or "/").
DATABASE_URL = URL.create("postgresql+psycopg2", username=DB_USER, password=DB_PASSWORD or None,
                          host=DB_HOST, port=int(DB_PORT), database=DB_NAME)


def validate_db_settings() -> None:
    """Called at startup (lifespan) so a missing DB secret fails fast with a clear message."""
    if not os.getenv("POSTGRES_PASSWORD"):
        raise RuntimeError("POSTGRES_PASSWORD must be set (local: in .env; AWS: Secrets Manager)")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
logger.info("PostgreSQL engine configured for %s:%s/%s", DB_HOST, DB_PORT, DB_NAME)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        db.connection()
        yield db
    except Exception:
        logger.exception("Failed to connect to PostgreSQL database")
        raise
    finally:
        db.close()
import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

DB_USER = os.getenv("POSTGRES_USER", "mortgage_app")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "change-me")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "mortgage_intel")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

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
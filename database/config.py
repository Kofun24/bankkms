"""
database/config.py

Database engine and session setup for BankKMS. Reads DATABASE_URL from .env.
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not found in environment. Add it to your .env file.")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db_session():
    """Yields a database session, closing it automatically afterward."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
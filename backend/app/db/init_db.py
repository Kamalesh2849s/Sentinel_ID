"""
Database initialization and seeding with prototype/mock data.
IMPORTANT: All data here is fabricated prototype data, NOT real government records.
"""
import logging
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session

from app.db.database import Base, engine, SessionLocal
from app.models.models import (
    User, ValidDocument, Watchlist, Blacklist, ScreeningStatus
)
from app.core.security import hash_password

logger = logging.getLogger(__name__)


def init_db():
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)
    # Ensure newly added columns exist in sqlite tables
    from sqlalchemy import text
    with engine.connect() as conn:
        for col, col_type in [
            ("risk_status", "VARCHAR(50) DEFAULT 'pending'"),
            ("risk_level", "VARCHAR(50)"),
            ("failure_reason", "VARCHAR(500)"),
            ("calculated_at", "DATETIME"),
        ]:
            try:
                conn.execute(text(f"ALTER TABLE risk_results ADD COLUMN {col} {col_type}"))
                conn.commit()
            except Exception:
                pass

        for table, col, col_type in [
            ("mrz_results", "raw_mrz_lines", "JSON"),
            ("mrz_results", "normalized_mrz", "TEXT"),
            ("mrz_results", "normalized_mrz_lines", "JSON"),
            ("mrz_results", "mrz_status", "VARCHAR(50)"),
            ("mrz_results", "check_digits", "JSON"),
            ("mrz_results", "mrz_parsed_fields", "JSON"),
            ("mrz_results", "nationality_code", "VARCHAR(10)"),
            ("mrz_results", "issuing_country_code", "VARCHAR(10)"),
            ("extracted_documents", "nationality_code", "VARCHAR(10)"),
            ("extracted_documents", "issuing_country_code", "VARCHAR(10)"),
            ("extracted_documents", "date_of_issue", "VARCHAR(20)"),
            ("extracted_documents", "date_of_issue_source", "VARCHAR(50)"),
            ("extracted_documents", "name_ocr", "VARCHAR(200)"),
            ("extracted_documents", "name_mrz", "VARCHAR(200)"),
            ("extracted_documents", "name_source", "VARCHAR(50)"),
            ("extracted_documents", "name_consistency", "VARCHAR(50)"),
            ("extracted_documents", "name_confidence", "FLOAT"),
        ]:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                conn.commit()
            except Exception:
                pass
    logger.info("Database tables created")


def seed_db():
    """Seed prototype data into the database."""
    db = SessionLocal()
    try:
        _seed_users(db)
        _seed_valid_documents(db)
        _seed_watchlist(db)
        _seed_blacklist(db)
        logger.info("Database seeded with prototype data")
    finally:
        db.close()


def _seed_users(db: Session):
    """Create default officer accounts."""
    if db.query(User).count() > 0:
        return

    users = [
        {
            "username": "officer1",
            "password": "password123",
            "full_name": "Officer James Carter",
            "role": "officer",
            "badge_number": "BCO-001",
        },
        {
            "username": "admin",
            "password": "admin123",
            "full_name": "Admin Sarah Mitchell",
            "role": "admin",
            "badge_number": "BCO-ADM-001",
        },
        {
            "username": "supervisor",
            "password": "super123",
            "full_name": "Supervisor David Chen",
            "role": "supervisor",
            "badge_number": "BCO-SUP-001",
        },
    ]

    for user_data in users:
        password = user_data.pop("password")
        user = User(
            **user_data,
            password_hash=hash_password(password),
        )
        db.add(user)

    db.commit()
    logger.info("Seeded default user accounts")


def _seed_valid_documents(db: Session):
    """Seed prototype valid document registry."""
    if db.query(ValidDocument).count() > 0:
        return

    # All data below is entirely fictional/prototype
    documents = [
        {
            "document_number": "AB123456",
            "full_name": "JOHN WILLIAM SMITH",
            "date_of_birth": "850315",
            "nationality": "USA",
            "issuing_country": "USA",
            "expiry_date": "280315",
            "document_type": "passport",
            "status": "VALID",
        },
        {
            "document_number": "CD789012",
            "full_name": "MARIA ELENA GARCIA",
            "date_of_birth": "920712",
            "nationality": "MEX",
            "issuing_country": "MEX",
            "expiry_date": "270712",
            "document_type": "passport",
            "status": "VALID",
        },
        {
            "document_number": "EF345678",
            "full_name": "JAMES THOMAS BROWN",
            "date_of_birth": "780501",
            "nationality": "GBR",
            "issuing_country": "GBR",
            "expiry_date": "260501",
            "document_type": "passport",
            "status": "EXPIRED",
        },
        {
            "document_number": "GH901234",
            "full_name": "LING XIAOHONG",
            "date_of_birth": "001220",
            "nationality": "CHN",
            "issuing_country": "CHN",
            "expiry_date": "301220",
            "document_type": "passport",
            "status": "VALID",
        },
        {
            "document_number": "IJ567890",
            "full_name": "AKIRA TANAKA",
            "date_of_birth": "880930",
            "nationality": "JPN",
            "issuing_country": "JPN",
            "expiry_date": "290930",
            "document_type": "passport",
            "status": "VALID",
        },
        {
            "document_number": "KL234567",
            "full_name": "AMINA OKAFOR",
            "date_of_birth": "950415",
            "nationality": "NGA",
            "issuing_country": "NGA",
            "expiry_date": "260415",
            "document_type": "passport",
            "status": "CANCELLED",
        },
    ]

    for doc_data in documents:
        doc = ValidDocument(**doc_data, is_prototype_data=True)
        db.add(doc)

    db.commit()
    logger.info("Seeded %d prototype valid documents", len(documents))


def _seed_watchlist(db: Session):
    """Seed prototype watchlist entries."""
    if db.query(Watchlist).count() > 0:
        return

    entries = [
        {
            "document_number": "WL000001",
            "name": "PROTOTYPE WATCHLIST PERSON A",
            "reason": "Travel restriction — prototype data",
            "severity": "MEDIUM",
            "status": "ACTIVE",
        },
        {
            "document_number": "WL000002",
            "name": "PROTOTYPE WATCHLIST PERSON B",
            "reason": "Immigration violation — prototype data",
            "severity": "HIGH",
            "status": "ACTIVE",
        },
    ]

    for entry_data in entries:
        entry = Watchlist(**entry_data, is_prototype_data=True)
        db.add(entry)

    db.commit()
    logger.info("Seeded prototype watchlist")


def _seed_blacklist(db: Session):
    """Seed prototype blacklist entries."""
    if db.query(Blacklist).count() > 0:
        return

    entries = [
        {
            "document_number": "BL000001",
            "name": "PROTOTYPE BLACKLIST PERSON A",
            "reason": "Document fraud — prototype data",
            "status": "ACTIVE",
        },
    ]

    for entry_data in entries:
        entry = Blacklist(**entry_data, is_prototype_data=True)
        db.add(entry)

    db.commit()
    logger.info("Seeded prototype blacklist")

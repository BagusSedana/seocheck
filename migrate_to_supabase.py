import os
import sqlite3
from sqlalchemy import create_engine, MetaData, Table, select
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import models # Pastikan models terimport
from database import Base, engine as pg_engine

# Load env from .env file
load_dotenv()

SQLITE_DB = "seo_scanner.db"
# Ambil DATABASE_URL yang baru (Supabase)
PG_URL = os.getenv("DATABASE_URL")

if not PG_URL or PG_URL.startswith("sqlite"):
    print("Error: DATABASE_URL harus berupa PostgreSQL URL (Supabase)")
    exit(1)

if PG_URL.startswith("postgres://"):
    PG_URL = PG_URL.replace("postgres://", "postgresql://", 1)

print(f"Migrating from {SQLITE_DB} to Supabase...")

# 1. Create tables in Supabase
Base.metadata.create_all(bind=pg_engine)

# 2. Connect to SQLite
sqlite_conn = sqlite3.connect(SQLITE_DB)
sqlite_conn.row_factory = sqlite3.Row
cursor = sqlite_conn.cursor()

# 3. Tables to migrate (sesuai urutan dependency)
tables = ["users", "projects", "scan_results", "competitor_scans", "transactions", "lead_captures"]

PgSession = sessionmaker(bind=pg_engine)
session = PgSession()

try:
    for table_name in tables:
        print(f"Migrating table: {table_name}...")
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        
        if not rows:
            print(f"  Table {table_name} is empty, skipping.")
            continue
            
        # Get table object
        table_obj = Base.metadata.tables.get(table_name)
        if table_obj is None:
            print(f"  Warning: Table {table_name} not found in models, skipping.")
            continue
            
        count = 0
        for row in rows:
            data = dict(row)
            # Insert into PG
            session.execute(table_obj.insert().values(**data))
            count += 1
        
        session.commit()
        print(f"  Successfully migrated {count} rows for {table_name}.")

    print("\nMigration completed successfully!")
except Exception as e:
    session.rollback()
    print(f"\nError during migration: {e}")
finally:
    session.close()
    sqlite_conn.close()

import database
import models
from sqlalchemy import text

engine = database.engine

# Create new tables
models.Base.metadata.create_all(bind=engine)

with engine.connect() as conn:
    print("--- Adding project_id to scan_results ---")
    try:
        conn.execute(text("ALTER TABLE scan_results ADD COLUMN project_id INTEGER REFERENCES projects(id)"))
        conn.commit()
        print("Column added successfully.")
    except Exception as e:
        print(f"Note: {e} (Maybe column already exists)")

    print("Migration finished!")

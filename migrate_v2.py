import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "seo_scanner_db")

def migrate():
    connection = pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
    )

    try:
        with connection.cursor() as cursor:
            print("Adding topup_scans and last_reset_date columns...")
            
            # Add topup_scans if not exists
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN topup_scans INT DEFAULT 0")
                print("Added topup_scans")
            except Exception as e:
                print(f"Column topup_scans might already exist: {e}")

            # Add last_reset_date if not exists
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN last_reset_date DATETIME")
                print("Added last_reset_date")
                # Initialize last_reset_date with created_at or now
                cursor.execute("UPDATE users SET last_reset_date = created_at WHERE last_reset_date IS NULL")
                cursor.execute("UPDATE users SET last_reset_date = NOW() WHERE last_reset_date IS NULL")
                print("Initialized last_reset_date")
            except Exception as e:
                print(f"Column last_reset_date might already exist: {e}")

            # Remove old columns (Optional, safer to keep for a bit)
            # cursor.execute("ALTER TABLE users DROP COLUMN scan_month")
            # cursor.execute("ALTER TABLE users DROP COLUMN scan_year")

            connection.commit()
            print("Migration successful!")

    finally:
        connection.close()

if __name__ == "__main__":
    migrate()

from database import engine
from sqlalchemy import text, inspect

def fix_schema():
    with engine.connect() as conn:
        insp = inspect(engine)
        columns = [c['name'] for c in insp.get_columns('users')]
        
        if 'subscription_end' not in columns:
            print("Adding subscription_end to users table...")
            conn.execute(text("ALTER TABLE users ADD COLUMN subscription_end DATETIME NULL AFTER scan_year"))
        
        print("Ensuring transactions table exists...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT,
                order_id VARCHAR(100) UNIQUE,
                amount INT,
                plan_tier ENUM('free', 'pro', 'agency'),
                billing_cycle ENUM('monthly', 'yearly'),
                status VARCHAR(50) DEFAULT 'pending',
                payment_type VARCHAR(50),
                snap_token VARCHAR(255),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """))
        conn.commit()
        print("Schema fix complete!")

if __name__ == "__main__":
    fix_schema()

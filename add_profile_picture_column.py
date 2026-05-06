"""
Quick script to add profile_picture_url column to users table.
Run this if migrations have issues: python add_profile_picture_column.py
"""
from app.db.session import SessionLocal
from sqlalchemy import text

def add_profile_picture_column():
    db = SessionLocal()
    try:
        # Check if column exists
        result = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users' 
            AND column_name = 'profile_picture_url'
        """))
        
        if result.fetchone():
            print("SUCCESS: Column profile_picture_url already exists")
            return
        
        # Add the column
        db.execute(text("""
            ALTER TABLE users 
            ADD COLUMN profile_picture_url VARCHAR(500) NULL
        """))
        db.commit()
        print("SUCCESS: Successfully added profile_picture_url column to users table")
        
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    add_profile_picture_column()

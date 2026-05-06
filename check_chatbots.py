from app.db.session import engine
from sqlalchemy import text

with engine.connect() as conn:
    rows = conn.execute(text("SELECT slug, name, is_active FROM chatbots ORDER BY created_at")).fetchall()
    for r in rows:
        print(f"slug={r[0]}, name={r[1]}, is_active={r[2]}")
    print(f"Total: {len(rows)}")

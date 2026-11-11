from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text

db = SQLAlchemy()

def init_db(app):
    """Initialize the database with the Flask app."""
    db.init_app(app)
    with app.app_context():
        db.create_all()
        try:
            insp = inspect(db.engine)
            if 'users' in insp.get_table_names():
                cols = [c['name'] for c in insp.get_columns('users')]
                if 'monthly_budget' not in cols:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN monthly_budget FLOAT DEFAULT 1000.0"))
                    db.session.commit()
            if 'expenses' in insp.get_table_names():
                cols = [c['name'] for c in insp.get_columns('expenses')]
                if 'status' not in cols:
                    db.session.execute(text("ALTER TABLE expenses ADD COLUMN status VARCHAR(20) DEFAULT 'paid'"))
                    db.session.execute(text("UPDATE expenses SET status = 'paid' WHERE status IS NULL"))
                    db.session.commit()
        except Exception:
            db.session.rollback()

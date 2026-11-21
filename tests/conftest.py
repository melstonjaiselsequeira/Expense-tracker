import os
import sys

# Ensure test suite runs strictly on in-memory SQLite, never touching production/local PostgreSQL
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
os.environ['TESTING'] = 'True'

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pytest
from app import app, db, limiter

# Ignore scratch and standalone diagnostic scripts during test collection
collect_ignore = ["scratch", "test_smtp.py"]

from models import User, Expense

@pytest.fixture
def client():
    # Use a temporary in-memory SQLite database for tests
    app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-secret",
    })
    # Ensure extensions are reinitialized with the new app config
    with app.app_context():
        db.drop_all()
        db.create_all()
        try:
            limiter.reset()
        except Exception:
            pass
    with app.test_client() as client:
        yield client
    # Cleanup
    with app.app_context():
        db.session.remove()
        db.drop_all()

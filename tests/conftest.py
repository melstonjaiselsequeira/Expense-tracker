import os
import pytest
import sys, os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from app import app, db

# Ignore the scratch directory during test collection to avoid name collisions
collect_ignore = ["scratch"]

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
    with app.test_client() as client:
        yield client
    # Cleanup
    with app.app_context():
        db.session.remove()
        db.drop_all()

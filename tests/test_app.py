import json
import pytest
from unittest.mock import patch
from app import app, db, generate_confirmation_token
from models import User, Expense

@pytest.fixture
def verified_user(client):
    # Register a user via API
    resp = client.post('/register', json={
        'full_name': 'Verified User',
        'email': 'verified@example.com',
        'password': 'Secret123!'
    })
    assert resp.status_code == 201
    # Generate verification token manually (since email not sent)
    token = generate_confirmation_token('verified@example.com')
    # Verify the email
    verify_resp = client.get(f'/confirm/{token}')
    assert verify_resp.status_code == 200
    return 'verified@example.com'

@pytest.fixture
def unverified_user(client):
    resp = client.post('/register', json={
        'full_name': 'Unverified User',
        'email': 'unverified@example.com',
        'password': 'Secret123!'
    })
    assert resp.status_code == 201
    return 'unverified@example.com'

def login(client, email, password):
    return client.post('/login', json={'email': email, 'password': password})

def test_login_requires_verification(client, verified_user, unverified_user):
    # Unverified should fail
    resp = login(client, unverified_user, 'Secret123!')
    assert resp.status_code == 403
    # Verified should succeed
    resp = login(client, verified_user, 'Secret123!')
    assert resp.status_code == 200

def test_expense_crud_isolation(client, verified_user):
    # Login as first user
    login_resp = login(client, verified_user, 'Secret123!')
    assert login_resp.status_code == 200
    # Create an expense
    exp_data = {'amount': 10.0, 'category': 'Food', 'description': 'Lunch', 'date': '2023-01-01'}
    create_resp = client.post('/api/expenses', json=exp_data)
    assert create_resp.status_code == 201
    expense_id = create_resp.get_json().get('id')
    # Register second user and verify
    resp = client.post('/register', json={
        'full_name': 'Second User',
        'email': 'second@example.com',
        'password': 'Pass123!'
    })
    assert resp.status_code == 201
    token = generate_confirmation_token('second@example.com')
    client.get(f'/confirm/{token}')
    # Login as second user
    login_resp = login(client, 'second@example.com', 'Pass123!')
    assert login_resp.status_code == 200
    # Second user attempts to fetch first user's expense list
    list_resp = client.get('/api/expenses')
    assert list_resp.status_code == 200
    expenses = list_resp.get_json()
    # Should be empty list for second user
    assert expenses == []
    # Attempt to delete first user's expense (should return 404 or 403)
    del_resp = client.delete(f'/api/expenses/{expense_id}')
    assert del_resp.status_code in (403, 404)

@patch('app.send_email')
def test_password_reset_rate_limit(mock_send_email, client, verified_user):
    # Ensure email sending is mocked to avoid actual SMTP calls
    for i in range(5):
        resp = client.post('/reset-password-request', json={'email': verified_user})
        assert resp.status_code == 200
    # Sixth request should be rate limited
    resp = client.post('/reset-password-request', json={'email': verified_user})
    assert resp.status_code == 429

@patch('app.send_email')
def test_csv_and_pdf_exports(mock_send_email, client, verified_user):
    # Login
    login_resp = login(client, verified_user, 'Secret123!')
    assert login_resp.status_code == 200
    # Create two expenses
    for i in range(2):
        exp = {'amount': i + 1.5, 'category': 'Test', 'description': f'Item {i}', 'date': '2023-02-01'}
        resp = client.post('/api/expenses', json=exp)
        assert resp.status_code == 201
    # CSV export
    csv_resp = client.get('/api/export')
    assert csv_resp.status_code == 200
    assert csv_resp.mimetype == 'text/csv'
    csv_content = csv_resp.data.decode()
    # Header should contain amount, category, description, date
    assert 'amount' in csv_content.lower()
    # PDF report for February 2023
    pdf_resp = client.get('/api/report/2023/02')
    assert pdf_resp.status_code == 200
    assert pdf_resp.mimetype == 'application/pdf'
    # Ensure some bytes are returned
    assert len(pdf_resp.data) > 1000

def test_login_success_feedback(client, verified_user):
    # Scenario 1: Registered email + correct password
    resp = login(client, verified_user, 'Secret123!')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get('message') == 'Login successful! Welcome back.'
    # Ensure user can now access dashboard / home page
    home_resp = client.get('/')
    assert home_resp.status_code == 200

def test_login_unregistered_email(client):
    # Scenario 2: Unregistered email
    resp = login(client, 'nonexistent@example.com', 'AnyPassword123!')
    assert resp.status_code == 404
    data = resp.get_json()
    assert data.get('error') == 'Account not found. Please sign up to continue.'
    assert data.get('code') == 'USER_NOT_FOUND'

def test_login_incorrect_password(client, verified_user):
    # Scenario 4: Registered email + incorrect password
    resp = login(client, verified_user, 'IncorrectPassword!')
    assert resp.status_code == 401
    data = resp.get_json()
    assert data.get('error') == 'Incorrect password. Please try again.'
    assert data.get('code') == 'INVALID_PASSWORD'

def test_registration_success_feedback(client):
    # Scenario 5: Successful registration
    resp = client.post('/register', json={
        'full_name': 'New Register User',
        'email': 'newuser@example.com',
        'password': 'Password123!'
    })
    assert resp.status_code == 201
    data = resp.get_json()
    assert data.get('message') == 'Registration successful! Please log in to continue.'

def test_session_remains_authenticated_on_refresh(client, verified_user):
    # Scenario 7: Refreshing the page after successful login
    resp = login(client, verified_user, 'Secret123!')
    assert resp.status_code == 200
    # First visit to home
    home1 = client.get('/')
    assert home1.status_code == 200
    # Refresh (subsequent request in same session)
    home2 = client.get('/')
    assert home2.status_code == 200
    # API stats access in same session
    stats_resp = client.get('/api/stats')
    assert stats_resp.status_code == 200

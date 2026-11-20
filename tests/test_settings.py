import io
import os
import pytest
from app import app, db, generate_confirmation_token
from models import User, Expense, SupportTicket, ReportHistory
from datetime import date, datetime

def create_user(client, email, password='Password123!', full_name='Test User', is_admin=False):
    """Helper to create and verify a user."""
    client.post('/register', json={
        'full_name': full_name,
        'email': email,
        'password': password
    })
    token = generate_confirmation_token(email)
    client.get(f'/confirm/{token}')
    if is_admin:
        with app.app_context():
            u = User.query.filter_by(email=email.lower()).first()
            if u:
                u.is_admin = True
                db.session.commit()
    return email

def login_client(client, email, password='Password123!'):
    """Helper to log in."""
    return client.post('/login', json={'email': email, 'password': password})


def test_normal_user_sees_settings_nav_and_view(client):
    """Verify normal users see the Settings sidebar item and view in dashboard."""
    email = create_user(client, 'user_settings@example.com', full_name='Settings User')
    login_client(client, email)

    resp = client.get('/dashboard?view=settings')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Normal user should see Settings in sidebar
    assert 'id="nav-settings"' in html
    assert 'Settings</span>' in html

    # Normal user should see the Settings section and cards
    assert 'id="view-settings"' in html
    assert 'Profile Information' in html
    assert 'Account Security' in html
    assert 'Account Management' in html
    assert 'id="delete-account-modal-overlay"' in html


def test_admin_user_cannot_see_or_access_settings(client):
    """Verify administrators do not see Settings nav item and are redirected away."""
    admin_email = create_user(client, 'admin_settings@example.com', full_name='Admin User', is_admin=True)
    login_client(client, admin_email)

    # 1. Check sidebar does NOT render nav-settings
    resp_dash = client.get('/dashboard', follow_redirects=True)
    assert resp_dash.status_code == 200
    html = resp_dash.get_data(as_text=True)
    assert 'id="nav-settings"' not in html
    assert 'id="view-settings"' not in html

    # 2. Direct attempt to open ?view=settings redirects to admin-dashboard
    resp_redirect = client.get('/dashboard?view=settings')
    assert resp_redirect.status_code in (301, 302)
    assert 'view=admin-dashboard' in resp_redirect.location

    # 3. Backend APIs return 403 Forbidden for admin
    resp_api = client.get('/api/user/profile')
    assert resp_api.status_code == 403
    assert resp_api.get_json().get('code') == 'FORBIDDEN'


def test_get_user_profile(client):
    """Verify user can fetch their personal profile details."""
    email = create_user(client, 'profile_fetch@example.com', full_name='Alice Profile')
    login_client(client, email)

    resp = client.get('/api/user/profile')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'user' in data
    u = data['user']
    assert u['email'] == 'profile_fetch@example.com'
    assert u['username'] == 'Alice Profile'
    assert u['is_admin'] is False


def test_update_username_success_and_validations(client):
    """Test updating username with valid and invalid values."""
    email1 = create_user(client, 'user1_name@example.com', full_name='User_One')
    email2 = create_user(client, 'user2_name@example.com', full_name='User_Two')

    login_client(client, email1)

    # 1. Empty username rejected
    resp = client.put('/api/user/username', json={'username': '   '})
    assert resp.status_code == 400
    assert resp.get_json().get('code') == 'VALIDATION_ERROR'

    # 2. Too short (< 3 chars)
    resp = client.put('/api/user/username', json={'username': 'ab'})
    assert resp.status_code == 400
    assert resp.get_json().get('code') == 'VALIDATION_ERROR'

    # 3. Invalid characters
    resp = client.put('/api/user/username', json={'username': 'invalid user!'})
    assert resp.status_code == 400
    assert resp.get_json().get('code') == 'VALIDATION_ERROR'

    # 4. Duplicate username taken by user2
    resp = client.put('/api/user/username', json={'username': 'User_Two'})
    assert resp.status_code == 400
    assert resp.get_json().get('code') == 'USERNAME_TAKEN'

    # 5. Successful valid update
    resp = client.put('/api/user/username', json={'username': 'alex_flow_99'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['username'] == 'alex_flow_99'

    # Verify persisted in database
    with app.app_context():
        u = User.query.filter_by(email=email1).first()
        assert u.username == 'alex_flow_99'
        assert u.display_name == 'alex_flow_99'


def test_profile_picture_upload_and_delete(client):
    """Test uploading an avatar image and removing it."""
    email = create_user(client, 'avatar_test@example.com', full_name='Avatar User')
    login_client(client, email)

    # 1. Invalid file format
    txt_data = (io.BytesIO(b"dummy text file content"), 'avatar.txt')
    resp = client.post('/api/user/profile-picture', data={'file': txt_data}, content_type='multipart/form-data')
    assert resp.status_code == 400
    assert resp.get_json().get('code') == 'INVALID_FORMAT'

    # 2. File too large (> 5 MB)
    large_data = (io.BytesIO(b"0" * (5 * 1024 * 1024 + 100)), 'large_avatar.png')
    resp = client.post('/api/user/profile-picture', data={'file': large_data}, content_type='multipart/form-data')
    assert resp.status_code == 400
    assert resp.get_json().get('code') == 'FILE_TOO_LARGE'

    # 3. Valid PNG upload
    valid_png = (io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"), 'test_avatar.png')
    resp = client.post('/api/user/profile-picture', data={'file': valid_png}, content_type='multipart/form-data')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'profile_picture' in data
    assert data['profile_picture'].startswith('avatar_')
    saved_filename = data['profile_picture']

    # Verify database and file system
    with app.app_context():
        u = User.query.filter_by(email=email).first()
        assert u.profile_picture == saved_filename
        assert u.avatar_url == f"/static/uploads/profile_pictures/{saved_filename}"

    # 4. Remove profile picture
    resp_del = client.delete('/api/user/profile-picture')
    assert resp_del.status_code == 200
    with app.app_context():
        u = User.query.filter_by(email=email).first()
        assert u.profile_picture is None
        assert u.avatar_url is None


def test_password_change_security_validations(client):
    """Test password update security constraints and success."""
    email = create_user(client, 'password_test@example.com', password='OldPassword123!', full_name='Security User')
    login_client(client, email, password='OldPassword123!')

    # 1. Missing fields
    resp = client.put('/api/user/password', json={'current_password': '', 'new_password': 'NewPassword123!', 'confirm_password': 'NewPassword123!'})
    assert resp.status_code == 400

    # 2. Incorrect current password
    resp = client.put('/api/user/password', json={'current_password': 'WrongPassword123!', 'new_password': 'NewPassword123!', 'confirm_password': 'NewPassword123!'})
    assert resp.status_code == 400
    assert resp.get_json().get('code') == 'INVALID_CURRENT_PASSWORD'

    # 3. Confirmation mismatch
    resp = client.put('/api/user/password', json={'current_password': 'OldPassword123!', 'new_password': 'NewPassword123!', 'confirm_password': 'Different123!'})
    assert resp.status_code == 400
    assert resp.get_json().get('code') == 'PASSWORD_MISMATCH'

    # 4. Password reused
    resp = client.put('/api/user/password', json={'current_password': 'OldPassword123!', 'new_password': 'OldPassword123!', 'confirm_password': 'OldPassword123!'})
    assert resp.status_code == 400
    assert resp.get_json().get('code') == 'PASSWORD_REUSED'

    # 5. Weak passwords
    # Missing symbol
    resp = client.put('/api/user/password', json={'current_password': 'OldPassword123!', 'new_password': 'NewPassword123', 'confirm_password': 'NewPassword123'})
    assert resp.status_code == 400
    assert resp.get_json().get('code') == 'WEAK_PASSWORD'

    # 6. Successful password update
    resp = client.put('/api/user/password', json={'current_password': 'OldPassword123!', 'new_password': 'SecureNewPass99!', 'confirm_password': 'SecureNewPass99!'})
    assert resp.status_code == 200

    # 7. Verify new password works on login
    client.get('/logout')
    login_resp = login_client(client, email, password='SecureNewPass99!')
    assert login_resp.status_code == 200


def test_delete_user_account_cascades_and_redirects(client):
    """Test permanently deleting an account with cascading deletion of related data."""
    email = create_user(client, 'delete_me@example.com', password='Password123!', full_name='Delete User')
    login_client(client, email, password='Password123!')

    # Seed related records: expense and ticket
    with app.app_context():
        u = User.query.filter_by(email=email).first()
        exp = Expense(amount=55.0, category='Food', description='Dinner test', date=date.today(), status='paid', user_id=u.id)
        tkt = SupportTicket(ticket_id='TKT-DEL-01', user_id=u.id, category='General Query', subject='Test query', description='Test')
        db.session.add(exp)
        db.session.add(tkt)
        db.session.commit()
        u_id = u.id

    # 1. Invalid confirmation phrase
    resp = client.post('/api/user/delete-account', json={'current_password': 'Password123!', 'confirm_phrase': 'NO'})
    assert resp.status_code == 400
    assert resp.get_json().get('code') == 'INVALID_CONFIRMATION'

    # 2. Incorrect current password
    resp = client.post('/api/user/delete-account', json={'current_password': 'WrongPassword!', 'confirm_phrase': 'DELETE'})
    assert resp.status_code == 400
    assert resp.get_json().get('code') == 'INVALID_PASSWORD'

    # 3. Successful account deletion
    resp = client.post('/api/user/delete-account', json={'current_password': 'Password123!', 'confirm_phrase': 'DELETE'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get('redirect_url') == '/login'

    # 4. Verify user and cascading records are gone from database
    with app.app_context():
        assert db.session.get(User, u_id) is None
        assert Expense.query.filter_by(user_id=u_id).count() == 0
        assert SupportTicket.query.filter_by(user_id=u_id).count() == 0

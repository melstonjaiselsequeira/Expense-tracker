import io
import os
import pytest
from app import app, db, generate_confirmation_token
from models import User, SupportTicket

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


def test_support_ticket_submission_success(client):
    """Test standard valid support ticket submission."""
    user_email = create_user(client, 'supportuser@example.com', full_name='Support User')
    login_client(client, user_email)

    # Submit ticket
    resp = client.post('/api/support/tickets', data={
        'category': 'General Query',
        'subject': 'How do I export PDF for previous year?',
        'description': 'I need assistance downloading my financial reports for 2025.'
    })
    assert resp.status_code == 201
    data = resp.get_json()
    assert 'ticket' in data
    ticket = data['ticket']
    assert ticket['ticket_id'].startswith('TKT-')
    assert ticket['category'] == 'General Query'
    assert ticket['subject'] == 'How do I export PDF for previous year?'
    assert ticket['status'] == 'Open'
    assert ticket['has_attachment'] is False


def test_support_ticket_validation_failures(client):
    """Test validation errors for invalid fields, categories, and lengths."""
    user_email = create_user(client, 'validationuser@example.com')
    login_client(client, user_email)

    # Invalid category
    resp = client.post('/api/support/tickets', data={
        'category': 'InvalidCategory',
        'subject': 'Valid Subject Here',
        'description': 'This is a long enough message to pass length test.'
    })
    assert resp.status_code == 400
    assert 'Invalid category' in resp.get_json().get('error', '')

    # Subject too short
    resp = client.post('/api/support/tickets', data={
        'category': 'Report a Problem',
        'subject': 'No',
        'description': 'This is a long enough message to pass length test.'
    })
    assert resp.status_code == 400
    assert 'Subject must be between' in resp.get_json().get('error', '')

    # Description too short
    resp = client.post('/api/support/tickets', data={
        'category': 'Report a Problem',
        'subject': 'Valid Subject Here',
        'description': 'Short'
    })
    assert resp.status_code == 400
    assert 'Message must be between' in resp.get_json().get('error', '')


def test_support_ticket_attachment_validation(client):
    """Test attachment upload rules (approved image types vs disallowed files)."""
    user_email = create_user(client, 'attachmentuser@example.com')
    login_client(client, user_email)

    # Approved image format (PNG)
    png_data = (io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRtestimagecontent"), 'screenshot.png')
    resp = client.post('/api/support/tickets', data={
        'category': 'Report a Problem',
        'subject': 'UI overlap bug with screenshot',
        'description': 'Attached is a screenshot demonstrating the glitch.',
        'attachment': png_data
    }, content_type='multipart/form-data')
    assert resp.status_code == 201
    data = resp.get_json()
    assert data['ticket']['has_attachment'] is True
    assert data['ticket']['attachment_filename'].endswith('.png')

    # Disallowed format (e.g. .exe or .txt)
    disallowed_file = (io.BytesIO(b"executable content"), 'malware.exe')
    resp_bad = client.post('/api/support/tickets', data={
        'category': 'Report a Problem',
        'subject': 'Executable file attachment',
        'description': 'Testing rejection of non-image file attachment.',
        'attachment': disallowed_file
    }, content_type='multipart/form-data')
    assert resp_bad.status_code == 400
    assert 'approved image format' in resp_bad.get_json().get('error', '')


def test_user_ticket_isolation(client):
    """Verify that users can only view their own tickets and never another user's."""
    user1 = create_user(client, 'user1@example.com', full_name='User One')
    user2 = create_user(client, 'user2@example.com', full_name='User Two')

    # User 1 submits a ticket
    login_client(client, user1)
    resp1 = client.post('/api/support/tickets', data={
        'category': 'Feature Request',
        'subject': 'Add dark emerald accent color',
        'description': 'I would love to have custom accent color picker in settings.'
    })
    assert resp1.status_code == 201
    t1_id = resp1.get_json()['ticket']['id']

    # User 2 submits a ticket
    login_client(client, user2)
    resp2 = client.post('/api/support/tickets', data={
        'category': 'General Query',
        'subject': 'Question about recurring expenses',
        'description': 'Can expenses be configured to repeat every Monday?'
    })
    assert resp2.status_code == 201
    t2_id = resp2.get_json()['ticket']['id']

    # User 2 lists tickets -> only sees t2, not t1
    list_resp = client.get('/api/support/tickets')
    assert list_resp.status_code == 200
    user2_tickets = list_resp.get_json()['tickets']
    assert len(user2_tickets) == 1
    assert user2_tickets[0]['id'] == t2_id

    # User 2 attempts to view User 1's ticket directly by ID -> 403 Forbidden
    detail_forbidden = client.get(f'/api/support/tickets/{t1_id}')
    assert detail_forbidden.status_code == 403
    assert detail_forbidden.get_json()['code'] == 'FORBIDDEN'


def test_admin_support_authorization_and_management(client):
    """Verify admin-only support interface and ticket status update workflows."""
    regular_user = create_user(client, 'regular@example.com', full_name='Regular User')
    admin_user = create_user(client, 'admin@example.com', full_name='Admin Boss', is_admin=True)

    # Regular user creates a ticket
    login_client(client, regular_user)
    ticket_resp = client.post('/api/support/tickets', data={
        'category': 'Report a Problem',
        'subject': 'Expense total discrepancy',
        'description': 'My total spent did not update after deleting an entry.'
    })
    assert ticket_resp.status_code == 201
    ticket_id = ticket_resp.get_json()['ticket']['id']

    # Regular user attempts to access admin endpoint -> 403 Forbidden
    admin_forbidden = client.get('/api/admin/support/tickets')
    assert admin_forbidden.status_code == 403
    assert admin_forbidden.get_json()['code'] == 'FORBIDDEN'

    # Admin logs in
    login_client(client, admin_user)

    # Admin accesses all tickets -> 200 OK
    admin_list = client.get('/api/admin/support/tickets')
    assert admin_list.status_code == 200
    all_tickets = admin_list.get_json()['tickets']
    assert len(all_tickets) >= 1
    assert any(t['id'] == ticket_id for t in all_tickets)

    # Admin filters by status
    open_tickets = client.get('/api/admin/support/tickets?status=Open')
    assert open_tickets.status_code == 200
    assert all(t['status'] == 'Open' for t in open_tickets.get_json()['tickets'])

    # Admin updates ticket status and adds notes
    update_resp = client.patch(f'/api/admin/support/tickets/{ticket_id}', json={
        'status': 'In Progress',
        'admin_notes': 'Investigating calculation cache for your account.'
    })
    assert update_resp.status_code == 200
    updated_data = update_resp.get_json()['ticket']
    assert updated_data['status'] == 'In Progress'
    assert updated_data['admin_notes'] == 'Investigating calculation cache for your account.'

    # Regular user checks their ticket -> sees In Progress status and admin notes
    login_client(client, regular_user)
    user_detail = client.get(f'/api/support/tickets/{ticket_id}')
    assert user_detail.status_code == 200
    u_ticket = user_detail.get_json()['ticket']
    assert u_ticket['status'] == 'In Progress'
    assert u_ticket['admin_notes'] == 'Investigating calculation cache for your account.'


def test_attachment_access_authorization(client):
    """Verify that attachments are strictly protected by user ownership or admin rights."""
    user1 = create_user(client, 'attachuser1@example.com', full_name='Attach User 1')
    user2 = create_user(client, 'attachuser2@example.com', full_name='Attach User 2')
    admin = create_user(client, 'adminattach@example.com', full_name='Admin Attach', is_admin=True)

    login_client(client, user1)
    png_data = (io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRtestattachmentauth"), 'evidence.png')
    resp = client.post('/api/support/tickets', data={
        'category': 'Report a Problem',
        'subject': 'Sensitive billing screenshot',
        'description': 'Screenshot showing billing issue details.',
        'attachment': png_data
    }, content_type='multipart/form-data')
    assert resp.status_code == 201
    filename = resp.get_json()['ticket']['attachment_filename']
    assert filename is not None

    # User 1 (owner) can download attachment -> 200
    owner_get = client.get(f'/api/support/attachments/{filename}')
    assert owner_get.status_code == 200

    # User 2 (not owner, not admin) attempts to download User 1's attachment -> 403 Forbidden
    login_client(client, user2)
    unauthorized_get = client.get(f'/api/support/attachments/{filename}')
    assert unauthorized_get.status_code == 403
    assert unauthorized_get.get_json()['code'] == 'FORBIDDEN'

    # Admin user can download any attachment -> 200
    login_client(client, admin)
    admin_get = client.get(f'/api/support/attachments/{filename}')
    assert admin_get.status_code == 200

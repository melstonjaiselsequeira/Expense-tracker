import os
import pytest
from unittest.mock import patch
from app import app, db, generate_confirmation_token
from models import User, SupportTicket, TicketMessage


def test_security_support_page_publicly_accessible(client):
    """Verify the Security Support page is publicly accessible without login and does not redirect."""
    # 1. Unauthenticated GET request to /support/security/password-changed
    resp = client.get('/support/security/password-changed')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')

    # 2. Check title, description, and form elements
    assert 'Report an Unauthorized Password Change' in html
    assert 'If you believe someone changed your ExpenseFlow account password without your permission' in html
    assert 'Registered Email Address' in html
    assert 'Unauthorized Password Change' in html
    assert 'I did not change my password' in html
    assert 'Submit Security Report' in html
    # Ensure it did NOT redirect to login
    assert resp.request.path == '/support/security/password-changed'

    # 3. Test prefill email query param
    resp_prefill = client.get('/support/security/password-changed?email=victim%40example.com')
    assert resp_prefill.status_code == 200
    html_prefill = resp_prefill.data.decode('utf-8')
    assert 'value="victim@example.com"' in html_prefill


def test_password_change_email_contains_security_support_link(client):
    """Verify changing password sends an email containing the security support link with correct app URL."""
    email = 'passchange_user@example.com'
    client.post('/register', json={
        'full_name': 'Pass Change User',
        'email': email,
        'password': 'InitialPassword123!',
        'consent_terms_privacy': True
    })
    token = generate_confirmation_token(email)
    client.get(f'/confirm/{token}')
    client.post('/login', json={'email': email, 'password': 'InitialPassword123!'})

    with patch('app.send_email') as mock_send_email:
        resp = client.put('/api/user/password', json={
            'current_password': 'InitialPassword123!',
            'new_password': 'UpdatedPassword123!',
            'confirm_password': 'UpdatedPassword123!'
        })
        assert resp.status_code == 200
        assert mock_send_email.called

        # Extract arguments from the email dispatch call
        call_args = mock_send_email.call_args[0]
        recipient = call_args[0]
        subject = call_args[1]
        text_body = call_args[2]
        html_body = mock_send_email.call_args[1].get('html_body') or ''

        assert recipient == email
        assert 'Your ExpenseFlow Password Has Been Changed' in subject
        assert 'If you did not make this password change, contact Help & Support immediately' in text_body
        assert '/support/security/password-changed' in text_body
        assert 'Report Unauthorized Password Change' in text_body

        # HTML body checks
        assert 'Report Unauthorized Password Change' in html_body
        assert '/support/security/password-changed?email=' in html_body


def test_security_report_validation_and_submission(client):
    """Verify security report input validation and successful creation of high-priority security ticket."""
    # 1. Invalid email validation
    resp_bad_email = client.post('/api/support/security/password-changed', json={
        'email': 'not-an-email',
        'subject': 'I did not change my password',
        'description': 'Someone took over my account and changed the password.'
    })
    assert resp_bad_email.status_code == 400
    assert resp_bad_email.get_json()['code'] == 'INVALID_EMAIL'

    # 2. Too short description validation
    resp_short = client.post('/api/support/security/password-changed', json={
        'email': 'victim@example.com',
        'subject': 'I did not change my password',
        'description': 'short'
    })
    assert resp_short.status_code == 400
    assert resp_short.get_json()['code'] == 'INVALID_DESCRIPTION'

    # 3. Create registered user to verify matching
    registered_email = 'account_victim@example.com'
    client.post('/register', json={
        'full_name': 'Security Victim',
        'email': registered_email,
        'password': 'StrongPassword123!',
        'consent_terms_privacy': True
    })

    # 4. Successful report submission
    with patch('app.send_email') as mock_send_email:
        resp_success = client.post('/api/support/security/password-changed', json={
            'email': registered_email,
            'subject': 'I did not change my password',
            'description': 'I received a password-change notification, but I did not make this change. I believe my account may have been compromised.'
        })
        assert resp_success.status_code == 201
        data = resp_success.get_json()
        assert 'ticket_id' in data
        ticket_id = data['ticket_id']
        assert ticket_id.startswith('SEC-')

        # Check database record
        with app.app_context():
            ticket = SupportTicket.query.filter_by(ticket_id=ticket_id).first()
            assert ticket is not None
            assert ticket.category == 'Security'
            assert 'URGENT SECURITY' in ticket.subject
            assert 'HIGH / URGENT' in ticket.description
            assert 'HIGH / URGENT' in ticket.admin_notes
            assert ticket.status == 'Open'
            # Verified that user was linked
            assert ticket.user is not None
            assert ticket.user.email == registered_email

        # 5. Anti-duplicate test: rapid repeated submission returns existing ticket
        resp_dup = client.post('/api/support/security/password-changed', json={
            'email': registered_email,
            'subject': 'I did not change my password',
            'description': 'I received a password-change notification, but I did not make this change. I believe my account may have been compromised.'
        })
        assert resp_dup.status_code == 200
        assert resp_dup.get_json()['ticket_id'] == ticket_id
        assert resp_dup.get_json().get('is_duplicate') is True


def test_security_ticket_appears_in_admin_dashboard(client):
    """Verify security report appears in existing Admin Support system and admins can manage/respond."""
    # 1. Register an admin user
    admin_email = 'sec_admin@example.com'
    with patch.dict(os.environ, {'ADMIN_EMAILS': admin_email}):
        client.post('/register', json={
            'full_name': 'Security Admin',
            'email': admin_email,
            'password': 'AdminPassword123!',
            'consent_terms_privacy': True
        })
        token = generate_confirmation_token(admin_email)
        client.get(f'/confirm/{token}')

        # 2. Submit a security ticket
        resp_sec = client.post('/api/support/security/password-changed', json={
            'email': 'target_user@example.com',
            'subject': 'Unauthorized password reset detected',
            'description': 'My account was breached and password changed without my consent.'
        })
        assert resp_sec.status_code == 201
        sec_ticket_id = resp_sec.get_json()['ticket_id']

        # 3. Log in as admin
        login_resp = client.post('/login', json={'email': admin_email, 'password': 'AdminPassword123!'})
        assert login_resp.status_code == 200

        # 4. Fetch admin support tickets list
        tickets_resp = client.get('/api/admin/support/tickets')
        assert tickets_resp.status_code == 200
        tickets = tickets_resp.get_json()['tickets']
        ticket_ids = [t['ticket_id'] for t in tickets]
        assert sec_ticket_id in ticket_ids

        # 5. Check ticket details in list
        sec_ticket = next(t for t in tickets if t['ticket_id'] == sec_ticket_id)
        assert sec_ticket['category'] == 'Security'
        assert 'URGENT SECURITY' in sec_ticket['subject']

        # 6. Admin can post a reply using existing support workflow
        reply_resp = client.post(f'/api/admin/support/tickets/{sec_ticket["id"]}/reply', json={
            'message': 'We have locked your account and sent a secure reset link to your verified email.',
            'status': 'In Progress'
        })
        assert reply_resp.status_code == 201


def test_public_cannot_access_ticket_endpoints(client):
    """Verify public visitors cannot access existing support tickets or user details."""
    # Create a ticket
    with app.app_context():
        ticket = SupportTicket(
            ticket_id='SEC-TEST-001',
            category='Security',
            subject='Secret Ticket',
            description='Private security details',
            status='Open'
        )
        db.session.add(ticket)
        db.session.commit()
        t_id = ticket.id

    # Public attempts to access admin ticket list -> redirected to login (302) or 401
    resp_list = client.get('/api/admin/support/tickets')
    assert resp_list.status_code in (302, 401)
    if resp_list.status_code == 302:
        assert '/login' in resp_list.location

    # Public attempts to access conversation -> redirected to login (302) or 401
    resp_convo = client.get(f'/api/admin/support/tickets/{t_id}/conversation')
    assert resp_convo.status_code in (302, 401)

    # Public attempts to reply -> redirected to login (302) or 401
    resp_reply = client.post(f'/api/admin/support/tickets/{t_id}/reply', json={'message': 'Hacker'})
    assert resp_reply.status_code in (302, 401)

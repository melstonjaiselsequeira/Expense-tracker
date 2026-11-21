import os
import io
import pytest
from unittest.mock import patch
from app import (
    app, db,
    generate_confirmation_token, confirm_token,
    generate_password_reset_token, confirm_password_reset_token,
    validate_password_strength, send_monthly_reports,
    SUPPORT_ATTACHMENT_DIR
)
from models import User, UserConsent, SupportTicket, Expense


def test_privacy_and_terms_pages_render(client):
    """Verify dedicated Privacy Policy and Terms & Conditions pages render 200 with DPDP notices."""
    # 1. Privacy Policy
    resp_privacy = client.get('/privacy')
    assert resp_privacy.status_code == 200
    html_p = resp_privacy.data.decode('utf-8')
    assert 'Privacy Policy' in html_p
    assert 'Digital Personal Data Protection (DPDP) Act, 2023' in html_p
    assert 'Data Fiduciary' in html_p
    assert 'Grievance' in html_p
    assert 'grievance@expenseflow.com' in html_p
    # Footer verification
    assert 'footer-wrapper' in html_p
    assert 'footer-grid' in html_p
    assert 'footer-brand-col' in html_p
    assert 'system-status-indicator' in html_p
    assert 'All Systems Operational' in html_p
    assert 'footer-bottom-bar' in html_p
    assert 'Designed for personal wealth clarity' in html_p

    # 2. Terms and Conditions
    resp_terms = client.get('/terms')
    assert resp_terms.status_code == 200
    html_t = resp_terms.data.decode('utf-8')
    assert 'Terms and Conditions' in html_t
    assert 'Acceptance of Terms' in html_t
    assert 'Acceptable Use' in html_t
    assert 'Disclaimer' in html_t
    assert 'Governing Law' in html_t
    # Footer verification
    assert 'footer-wrapper' in html_t
    assert 'footer-grid' in html_t
    assert 'footer-brand-col' in html_t
    assert 'system-status-indicator' in html_t
    assert 'All Systems Operational' in html_t
    assert 'footer-bottom-bar' in html_t
    assert 'Designed for personal wealth clarity' in html_t


def test_registration_consent_validation(client):
    """Verify registration requires consent and stores consent audit record in DB."""
    # Explicitly declining consent -> 400
    resp_fail = client.post('/register', json={
        'full_name': 'No Consent User',
        'email': 'noconsent@example.com',
        'password': 'SecurePassword123!',
        'consent_terms_privacy': False
    })
    assert resp_fail.status_code == 400
    fail_data = resp_fail.get_json()
    assert fail_data.get('code') == 'CONSENT_REQUIRED'

    # Providing consent -> 201
    resp_success = client.post('/register', json={
        'full_name': 'Consent Granted User',
        'email': 'consented@example.com',
        'password': 'SecurePassword123!',
        'consent_terms_privacy': True
    })
    assert resp_success.status_code == 201

    # Check database state
    with app.app_context():
        user = User.query.filter_by(email='consented@example.com').first()
        assert user is not None
        assert user.has_consented_terms_privacy is True
        assert user.consent_version == '1.0'
        assert user.consent_timestamp is not None

        # Verify UserConsent audit entry
        consent_record = UserConsent.query.filter_by(user_id=user.id, consent_type='terms_and_privacy').first()
        assert consent_record is not None
        assert consent_record.has_consented is True
        assert consent_record.policy_version == '1.0'


def test_password_strength_validation(client):
    """Verify backend enforces strong password policy on registration."""
    weak_passwords = [
        'short1!',           # < 8 chars
        'alllowercase123!',  # missing uppercase
        'ALLUPPERCASE123!',  # missing lowercase
        'NoNumbersHere!!',   # missing digit
        'NoSpecialSymbol1',  # missing special character
    ]
    for weak_pwd in weak_passwords:
        resp = client.post('/register', json={
            'full_name': 'Weak Password User',
            'email': f'weak_{len(weak_pwd)}@example.com',
            'password': weak_pwd,
            'consent_terms_privacy': True
        })
        assert resp.status_code == 400
        assert resp.get_json().get('code') == 'WEAK_PASSWORD'


def test_token_isolation_and_single_use(client):
    """Verify cryptographic separation between confirmation and password reset tokens."""
    # Create and verify a test user
    client.post('/register', json={
        'full_name': 'Token Test User',
        'email': 'tokenuser@example.com',
        'password': 'InitialPassword123!',
        'consent_terms_privacy': True
    })
    confirm_tok = generate_confirmation_token('tokenuser@example.com')
    client.get(f'/confirm/{confirm_tok}')

    with app.app_context():
        user = User.query.filter_by(email='tokenuser@example.com').first()
        reset_tok = generate_password_reset_token(user)

    # 1. Email confirmation token CANNOT be used as password reset token
    with app.app_context():
        assert confirm_password_reset_token(confirm_tok) is None

    # 2. Password reset token CANNOT be used to confirm email
    with app.app_context():
        assert confirm_token(reset_tok) is None

    # 3. Successful password reset with strong password
    resp = client.post(f'/reset-password/{reset_tok}', json={
        'password': 'NewStrongPassword123!'
    })
    assert resp.status_code == 200

    # 4. Single-use guarantee: the same reset token is now invalidated
    with app.app_context():
        assert confirm_password_reset_token(reset_tok) is None

    resp_reuse = client.post(f'/reset-password/{reset_tok}', json={
        'password': 'AnotherPassword123!'
    })
    assert resp_reuse.status_code == 400
    assert resp_reuse.get_json().get('code') == 'INVALID_TOKEN'


def test_account_deletion_cleans_up_support_attachments(client):
    """Verify account deletion cascades and deletes uploaded support attachments from disk."""
    # 1. Register & verify user
    email = 'delete_files@example.com'
    client.post('/register', json={
        'full_name': 'Delete File User',
        'email': email,
        'password': 'DeleteMe123!',
        'consent_terms_privacy': True
    })
    tok = generate_confirmation_token(email)
    client.get(f'/confirm/{tok}')

    # 2. Log in
    client.post('/login', json={'email': email, 'password': 'DeleteMe123!'})

    # 3. Create dummy file attachment on disk
    os.makedirs(SUPPORT_ATTACHMENT_DIR, exist_ok=True)
    fake_filename = f"tkt_test_cleanup_{os.getpid()}.png"
    fake_filepath = os.path.join(SUPPORT_ATTACHMENT_DIR, fake_filename)
    with open(fake_filepath, 'wb') as f:
        f.write(b"\x89PNG\r\n\x1a\nFakeAttachmentContent")
    assert os.path.exists(fake_filepath)

    # Link to a support ticket
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        ticket = SupportTicket(
            ticket_id='TKT-CLEANUP-001',
            user_id=user.id,
            category='General Query',
            subject='Attachment cleanup test',
            description='Test ticket description',
            attachment_path=fake_filename,
            status='Open'
        )
        db.session.add(ticket)
        db.session.commit()

    # 4. Delete user account
    del_resp = client.post('/api/user/delete-account', json={
        'current_password': 'DeleteMe123!',
        'confirm_phrase': 'DELETE'
    })
    assert del_resp.status_code == 200

    # 5. Verify file has been deleted from disk
    assert not os.path.exists(fake_filepath)


def test_user_preferences_monthly_report_opt_out(client):
    """Verify users can opt out of monthly expense reports and the scheduler honors it."""
    email = 'optout@example.com'
    client.post('/register', json={
        'full_name': 'Opt Out User',
        'email': email,
        'password': 'OptOutPassword123!',
        'consent_terms_privacy': True
    })
    tok = generate_confirmation_token(email)
    client.get(f'/confirm/{tok}')
    client.post('/login', json={'email': email, 'password': 'OptOutPassword123!'})

    # 1. Fetch preferences -> default True
    get_resp = client.get('/api/user/preferences')
    assert get_resp.status_code == 200
    assert get_resp.get_json()['email_reports_enabled'] is True

    # 2. Toggle to False
    put_resp = client.put('/api/user/preferences', json={'email_reports_enabled': False})
    assert put_resp.status_code == 200
    assert put_resp.get_json()['email_reports_enabled'] is False

    # Verify DB update
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        assert user.email_reports_enabled is False

    # 3. Run send_monthly_reports and verify no email is dispatched for opted-out user
    with patch('app.send_email_with_attachment') as mock_email:
        send_monthly_reports()
        for call in mock_email.call_args_list:
            recipient = call[0][0]
            assert recipient != email


def test_public_contact_and_grievance_api(client):
    """Verify landing page contact and grievance form records tickets safely."""
    # Missing required fields
    resp_bad = client.post('/api/contact', json={'name': 'Inquirer'})
    assert resp_bad.status_code == 400

    # Valid inquiry
    resp = client.post('/api/contact', json={
        'name': 'Grievance Inquirer',
        'email': 'inquirer@example.com',
        'subject': 'Privacy Rights Request',
        'message': 'I would like to inquire about my data rights under DPDP.'
    })
    assert resp.status_code == 201
    data = resp.get_json()
    assert 'ticket_id' in data
    assert data['ticket_id'].startswith('CNT-')

    # Verify ticket stored in DB
    with app.app_context():
        tkt = SupportTicket.query.filter_by(ticket_id=data['ticket_id']).first()
        assert tkt is not None
        assert 'Privacy Rights Request' in tkt.subject
        assert 'Grievance Inquirer' in tkt.description

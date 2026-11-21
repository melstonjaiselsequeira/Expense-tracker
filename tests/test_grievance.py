import os
import io
import pytest
from unittest.mock import patch
from app import app, db, generate_confirmation_token, GRIEVANCE_ATTACHMENT_DIR
from models import User, Grievance


def test_grievance_portal_page_renders_without_login(client):
    """Requirement 1, 2, 13: Dedicated internal page renders without login and shows DPDP statutory info."""
    resp = client.get('/grievance')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')

    # Must be dedicated page
    assert 'Grievance Redressal Portal' in html
    assert 'DPDP Act, 2023' in html
    assert 'Section 13' in html
    assert 'Submit Grievance' in html
    assert 'Track Grievance Status' in html

    # Requirement 13: Unconfigured notice shown when env vars not set
    assert 'Notice: Internal Grievance Routing Active' in html


def test_grievance_officer_configured_display(client, monkeypatch):
    """Requirement 2, 13: Configured Grievance Officer details are displayed accurately when set."""
    monkeypatch.setenv('GRIEVANCE_OFFICER_NAME', 'Advocate Rajesh Sharma')
    monkeypatch.setenv('GRIEVANCE_OFFICER_EMAIL', 'dpo@expenseflow.com')
    monkeypatch.setenv('GRIEVANCE_OFFICER_PHONE', '+91 98765 43210')
    monkeypatch.setenv('GRIEVANCE_OFFICER_ADDRESS', '42 MG Road, Cyber City, Bengaluru, India')

    resp = client.get('/grievance')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')

    assert 'Advocate Rajesh Sharma' in html
    assert 'dpo@expenseflow.com' in html
    assert '+91 98765 43210' in html
    assert '42 MG Road, Cyber City, Bengaluru, India' in html


def test_grievance_submission_validation(client):
    """Requirement 3: Grievance submission input validation."""
    # 1. Invalid email
    resp_bad_email = client.post('/api/grievance/submit', data={
        'contact_email': 'invalid-email',
        'category': 'Right to Erasure / Account & Data Deletion',
        'subject': 'Request account erasure',
        'description': 'Please delete all my personal data from your database.'
    })
    assert resp_bad_email.status_code == 400
    assert resp_bad_email.get_json()['code'] == 'INVALID_EMAIL'

    # 2. Missing category
    resp_no_cat = client.post('/api/grievance/submit', data={
        'contact_email': 'user@example.com',
        'category': '',
        'subject': 'Request account erasure',
        'description': 'Please delete all my personal data from your database.'
    })
    assert resp_no_cat.status_code == 400
    assert resp_no_cat.get_json()['code'] == 'CATEGORY_REQUIRED'

    # 3. Short subject (< 5 chars)
    resp_short_subj = client.post('/api/grievance/submit', data={
        'contact_email': 'user@example.com',
        'category': 'Right to Erasure / Account & Data Deletion',
        'subject': 'Del',
        'description': 'Please delete all my personal data from your database.'
    })
    assert resp_short_subj.status_code == 400
    assert resp_short_subj.get_json()['code'] == 'INVALID_SUBJECT'

    # 4. Short description (< 15 chars)
    resp_short_desc = client.post('/api/grievance/submit', data={
        'contact_email': 'user@example.com',
        'category': 'Right to Erasure / Account & Data Deletion',
        'subject': 'Request account erasure',
        'description': 'Too short'
    })
    assert resp_short_desc.status_code == 400
    assert resp_short_desc.get_json()['code'] == 'INVALID_DESCRIPTION'


def test_grievance_submission_flow_and_emails(client):
    """Requirements 4, 5, 6, 7, 10: Successful submission, unique reference ID, DB save, and email notifications."""
    complainant_email = 'dpdp_complainant@example.com'

    with patch('app.send_email') as mock_send_email:
        resp = client.post('/api/grievance/submit', data={
            'contact_email': complainant_email,
            'category': 'Right to Access / Data Summary Request',
            'subject': 'Request copy of all processed financial data',
            'description': 'Under Section 11 of DPDP Act 2023, I request an export of all my personal and expense records.'
        })

        assert resp.status_code == 201
        data = resp.get_json()
        assert 'reference_id' in data
        ref_id = data['reference_id']
        assert ref_id.startswith('GRV-')
        assert data['status'] == 'Submitted'

        # Verify DB persistence
        with app.app_context():
            g = Grievance.query.filter_by(reference_id=ref_id).first()
            assert g is not None
            assert g.contact_email == complainant_email.lower()
            assert g.category == 'Right to Access / Data Summary Request'
            assert g.subject == 'Request copy of all processed financial data'
            assert g.status == 'Submitted'
            assert g.attachment_path is None

        # Verify email notifications dispatched (Complainant confirmation + Officer alert)
        assert mock_send_email.call_count >= 2

        # Check complainant email
        complainant_call = [c for c in mock_send_email.call_args_list if c[0][0] == complainant_email][0]
        assert ref_id in complainant_call[0][1]
        assert 'Privacy Grievance Received' in complainant_call[0][1]


def test_grievance_with_attachment(client):
    """Requirement 3: Optional attachment handling and validation."""
    complainant_email = 'attachment_user@example.com'

    # Disallowed file type (.exe)
    resp_bad_ext = client.post('/api/grievance/submit', data={
        'contact_email': complainant_email,
        'category': 'Data Security / Incident or Breach Concern',
        'subject': 'Security incident report',
        'description': 'Attached is a log file containing proof of data exposure.',
        'attachment': (io.BytesIO(b'malicious content'), 'exploit.exe')
    })
    assert resp_bad_ext.status_code == 400
    assert resp_bad_ext.get_json()['code'] == 'INVALID_FILE_TYPE'

    # Valid PDF attachment
    with patch('app.send_email'):
        resp_valid = client.post('/api/grievance/submit', data={
            'contact_email': complainant_email,
            'category': 'Data Security / Incident or Breach Concern',
            'subject': 'Security incident report with evidence',
            'description': 'Attached is a legitimate evidence PDF explaining the concern.',
            'attachment': (io.BytesIO(b'%PDF-1.4 test content'), 'evidence.pdf')
        })
        assert resp_valid.status_code == 201
        ref_id = resp_valid.get_json()['reference_id']

        with app.app_context():
            g = Grievance.query.filter_by(reference_id=ref_id).first()
            assert g is not None
            assert g.attachment_path is not None
            assert 'evidence.pdf' in g.attachment_path


def test_grievance_tracking_privacy_isolation(client):
    """Requirement 11: Users can view their own grievance, but NEVER another user's grievance."""
    email_a = 'alice@example.com'
    email_b = 'bob@example.com'

    with patch('app.send_email'):
        # Alice submits grievance A
        resp_a = client.post('/api/grievance/submit', data={
            'contact_email': email_a,
            'category': 'Right to Correction / Updating Personal Data',
            'subject': 'Correction of registered phone number',
            'description': 'Please correct my contact records according to latest identification.'
        })
        ref_a = resp_a.get_json()['reference_id']

    # 1. Alice tracks her grievance with matching email -> 200 SUCCESS
    resp_track_ok = client.get(f'/api/grievance/status?reference_id={ref_a}&email={email_a}')
    assert resp_track_ok.status_code == 200
    track_data = resp_track_ok.get_json()
    assert track_data['grievance']['reference_id'] == ref_a
    assert track_data['grievance']['contact_email'] == email_a

    # 2. Bob tries to track Alice's grievance using her reference ID but his email -> 404 BLOCKED
    resp_track_mismatch = client.get(f'/api/grievance/status?reference_id={ref_a}&email={email_b}')
    assert resp_track_mismatch.status_code == 404

    # 3. Nonexistent reference ID -> 404
    resp_track_fake = client.get(f'/api/grievance/status?reference_id=GRV-99999999-FAKE99&email={email_a}')
    assert resp_track_fake.status_code == 404


def test_authenticated_user_grievances_endpoint(client):
    """Requirement 11: Authenticated user can retrieve their filed grievances."""
    # Unauthenticated call to /api/user/grievances is blocked
    resp_anon = client.get('/api/user/grievances')
    assert resp_anon.status_code in (302, 401)

    user_email = 'auth_grv_user@example.com'
    client.post('/register', json={
        'full_name': 'Auth User',
        'email': user_email,
        'password': 'StrongPassword123!',
        'consent_terms_privacy': True
    })
    token = generate_confirmation_token(user_email)
    client.get(f'/confirm/{token}')
    client.post('/login', json={'email': user_email, 'password': 'StrongPassword123!'})

    # Log in and file grievance while authenticated
    client.post('/login', json={'email': user_email, 'password': 'StrongPassword123!'})
    with patch('app.send_email'):
        client.post('/api/grievance/submit', data={
            'contact_email': user_email,
            'category': 'Right to Nominate / Representative Authorization',
            'subject': 'Nomination of legal representative',
            'description': 'I wish to authorize my nominated legal representative in case of incapacity.'
        })

    resp_my = client.get('/api/user/grievances')
    assert resp_my.status_code == 200
    data = resp_my.get_json()
    assert len(data['grievances']) >= 1
    assert data['grievances'][0]['category'] == 'Right to Nominate / Representative Authorization'


def test_admin_grievance_review_and_respond_flow(client):
    """Requirements 8, 9, 10: Admin dashboard viewing, status progression, and official response."""
    admin_email = 'nmj.kompany@gmail.com'
    client.post('/register', json={
        'full_name': 'System Admin',
        'email': admin_email,
        'password': 'AdminPassword123!',
        'consent_terms_privacy': True
    })
    tok = generate_confirmation_token(admin_email)
    client.get(f'/confirm/{tok}')

    # Submit a grievance to test against
    complainant = 'complainant_user@example.com'
    with patch('app.send_email'):
        resp_submit = client.post('/api/grievance/submit', data={
            'contact_email': complainant,
            'category': 'Withdrawal of Consent / Preference Concern',
            'subject': 'Withdraw consent for monthly digest',
            'description': 'I no longer wish to receive monthly summary analysis emails.'
        })
        ref_id = resp_submit.get_json()['reference_id']

    with app.app_context():
        g_record = Grievance.query.filter_by(reference_id=ref_id).first()
        g_id = g_record.id

    # Normal user cannot access admin grievance endpoints
    normal_email = 'regular_user@example.com'
    client.post('/register', json={
        'full_name': 'Regular User',
        'email': normal_email,
        'password': 'RegularUser123!',
        'consent_terms_privacy': True
    })
    client.get(f'/confirm/{generate_confirmation_token(normal_email)}')
    client.post('/login', json={'email': normal_email, 'password': 'RegularUser123!'})

    assert client.get('/api/admin/grievances').status_code == 403
    assert client.patch(f'/api/admin/grievances/{g_id}', json={'status': 'Under Review'}).status_code == 403

    # Log in as admin
    client.post('/logout')
    client.post('/login', json={'email': admin_email, 'password': 'AdminPassword123!'})

    # 1. Admin lists grievances
    resp_list = client.get('/api/admin/grievances')
    assert resp_list.status_code == 200
    list_data = resp_list.get_json()
    assert list_data['total'] >= 1
    refs = [item['reference_id'] for item in list_data['grievances']]
    assert ref_id in refs

    # 2. Admin retrieves single grievance detail
    resp_detail = client.get(f'/api/admin/grievances/{g_id}')
    assert resp_detail.status_code == 200
    assert resp_detail.get_json()['grievance']['reference_id'] == ref_id

    # 3. Admin updates status to 'Under Review' with internal notes
    resp_status_update = client.patch(f'/api/admin/grievances/{g_id}', json={
        'status': 'Under Review',
        'admin_notes': 'Verification in progress with records database.'
    })
    assert resp_status_update.status_code == 200
    assert resp_status_update.get_json()['grievance']['status'] == 'Under Review'

    # 4. Admin submits official response and marks 'Resolved'
    with patch('app.send_email') as mock_resp_email:
        resp_respond = client.post(f'/api/admin/grievances/{g_id}/respond', json={
            'response': 'Your consent withdrawal for monthly digest emails has been processed and applied to your account.',
            'status': 'Resolved',
            'admin_notes': 'Confirmed with automated mailer exclusion list.'
        })
        assert resp_respond.status_code == 200
        grv_final = resp_respond.get_json()['grievance']
        assert grv_final['status'] == 'Resolved'
        assert 'Your consent withdrawal' in grv_final['admin_response']

        # Verify email dispatched to complainant
        assert mock_resp_email.called
        call_recipient = mock_resp_email.call_args[0][0]
        assert call_recipient == complainant
        assert ref_id in mock_resp_email.call_args[0][1]


def test_contact_grievance_officer_links_to_internal_page_not_mailto(client):
    """Requirements 1, 12: Contact Grievance Officer links to internal /grievance route, not mailto."""
    # 1. Privacy Policy page
    resp_p = client.get('/privacy')
    assert resp_p.status_code == 200
    html_p = resp_p.data.decode('utf-8')
    assert 'href="/grievance"' in html_p

    # 2. Terms page
    resp_t = client.get('/terms')
    assert resp_t.status_code == 200
    html_t = resp_t.data.decode('utf-8')
    assert 'href="/grievance"' in html_t

    # 3. Dashboard page (when logged in)
    user_email = 'link_check_user@example.com'
    client.post('/register', json={
        'full_name': 'Link User',
        'email': user_email,
        'password': 'StrongPassword123!',
        'consent_terms_privacy': True
    })
    tok = generate_confirmation_token(user_email)
    client.get(f'/confirm/{tok}')
    client.post('/login', json={'email': user_email, 'password': 'StrongPassword123!'})

    resp_d = client.get('/dashboard')
    assert resp_d.status_code == 200
    html_d = resp_d.data.decode('utf-8')
    assert 'Contact Grievance Officer' in html_d
    assert '<a href="/grievance"' in html_d
    assert 'href="mailto:nmj.kompany@gmail.com"' not in html_d

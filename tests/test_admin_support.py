import pytest
from app import app, db
from models import User, SupportTicket, TicketMessage, FAQ
from datetime import datetime

@pytest.fixture
def admin_client(client):
    """Fixture that creates and logs in an admin user."""
    with app.app_context():
        # Ensure an admin user exists
        admin = User.query.filter_by(email='admin_tester@expenseflow.com').first()
        if not admin:
            admin = User(
                full_name='Admin Tester',
                email='admin_tester@expenseflow.com',
                is_admin=True,
                is_verified=True
            )
            admin.set_password('AdminSecret123!')
            db.session.add(admin)
            db.session.commit()
        else:
            admin.is_admin = True
            admin.is_verified = True
            admin.set_password('AdminSecret123!')
            db.session.commit()

        # Regular user
        reg_user = User.query.filter_by(email='regular_user@example.com').first()
        if not reg_user:
            reg_user = User(
                full_name='Regular User',
                email='regular_user@example.com',
                is_admin=False,
                is_verified=True
            )
            reg_user.set_password('UserSecret123!')
            db.session.add(reg_user)
            db.session.commit()

        # Seed sample tickets if needed
        t1 = SupportTicket.query.filter_by(ticket_id='TKT-TEST-0001').first()
        if not t1:
            t1 = SupportTicket(
                ticket_id='TKT-TEST-0001',
                user_id=reg_user.id,
                category='General Query',
                subject='How do I change category colors?',
                description='I want to change the color of food category.',
                status='Open'
            )
            db.session.add(t1)
        
        t2 = SupportTicket.query.filter_by(ticket_id='TKT-TEST-0002').first()
        if not t2:
            t2 = SupportTicket(
                ticket_id='TKT-TEST-0002',
                user_id=reg_user.id,
                category='Report a Problem',
                subject='Export CSV date format issue',
                description='Dates in CSV export are formatted strangely.',
                status='In Progress'
            )
            db.session.add(t2)

        t3 = SupportTicket.query.filter_by(ticket_id='TKT-TEST-0003').first()
        if not t3:
            t3 = SupportTicket(
                ticket_id='TKT-TEST-0003',
                user_id=reg_user.id,
                category='Feature Request',
                subject='Add recurring monthly subscriptions',
                description='Please add recurring subscriptions feature.',
                status='Resolved'
            )
            db.session.add(t3)
        db.session.commit()

    return client


def test_admin_authorization_enforced(admin_client):
    """Verify regular users cannot access admin endpoints."""
    # 1. Unauthenticated request
    res = admin_client.get('/api/admin/support/dashboard')
    assert res.status_code == 302  # redirects to login

    # 2. Login as regular user
    login_res = admin_client.post('/login', json={
        'email': 'regular_user@example.com',
        'password': 'UserSecret123!'
    })
    assert login_res.status_code == 200
    assert login_res.get_json()['is_admin'] is False

    # Attempt admin endpoint as regular user -> 403 Forbidden
    res = admin_client.get('/api/admin/support/dashboard')
    assert res.status_code == 403
    assert res.get_json()['code'] == 'FORBIDDEN'


def test_admin_login_redirect_and_sections(admin_client):
    """Verify admin login redirects to admin-dashboard and all 8 support endpoints work."""
    # 1. Admin login
    login_res = admin_client.post('/login', json={
        'email': 'admin_tester@expenseflow.com',
        'password': 'AdminSecret123!'
    })
    assert login_res.status_code == 200
    data = login_res.get_json()
    assert data['is_admin'] is True
    assert 'admin-dashboard' in data['redirect_url']

    # 2. Section 1: Support Dashboard Stats
    dash_res = admin_client.get('/api/admin/support/dashboard')
    assert dash_res.status_code == 200
    dash_data = dash_res.get_json()
    assert 'stats' in dash_data
    assert dash_data['stats']['total_tickets'] >= 3
    assert 'by_category' in dash_data['stats']
    assert len(dash_data['recent_tickets']) > 0

    # 3. Section 2: All Support Tickets (with search, filter, and sorting)
    all_res = admin_client.get('/api/admin/support/tickets?sort=date_desc')
    assert all_res.status_code == 200
    tickets = all_res.get_json()['tickets']
    assert len(tickets) >= 3

    # Test Search
    search_res = admin_client.get('/api/admin/support/tickets?search=recurring')
    assert search_res.status_code == 200
    assert any('recurring' in t['subject'].lower() for t in search_res.get_json()['tickets'])

    # 4. Section 3: General Queries
    gq_res = admin_client.get('/api/admin/support/tickets?category=General+Query')
    assert gq_res.status_code == 200
    for t in gq_res.get_json()['tickets']:
        assert t['category'] == 'General Query'

    # 5. Section 4: Reported Problems
    prob_res = admin_client.get('/api/admin/support/tickets?category=Report+a+Problem')
    assert prob_res.status_code == 200
    for t in prob_res.get_json()['tickets']:
        assert t['category'] == 'Report a Problem'

    # 6. Section 5: Feature Requests
    feat_res = admin_client.get('/api/admin/support/tickets?category=Feature+Request')
    assert feat_res.status_code == 200
    for t in feat_res.get_json()['tickets']:
        assert t['category'] == 'Feature Request'

    # 7. Section 6: Ticket Conversations & Admin Reply
    test_ticket = tickets[0]
    convo_res = admin_client.get(f"/api/admin/support/tickets/{test_ticket['id']}/conversation")
    assert convo_res.status_code == 200
    convo_data = convo_res.get_json()
    assert 'conversation' in convo_data
    assert len(convo_data['conversation']) >= 1  # Includes opening description

    # Post Admin Reply
    reply_res = admin_client.post(f"/api/admin/support/tickets/{test_ticket['id']}/reply", json={
        'message': 'We have reviewed your request and pushed an update.',
        'status': 'Resolved'
    })
    assert reply_res.status_code == 201
    reply_data = reply_res.get_json()
    assert reply_data['ticket']['status'] == 'Resolved'

    # 8. Section 7: FAQ Management
    faq_res = admin_client.post('/api/admin/faq', json={
        'question': 'How do I test admin FAQ creation?',
        'answer': 'You can manage FAQs dynamically through the Admin Support portal.',
        'category': 'Account Management',
        'is_published': True
    })
    assert faq_res.status_code == 201
    new_faq_id = faq_res.get_json()['faq']['id']

    # Toggle FAQ publish status
    toggle_res = admin_client.post(f'/api/admin/faq/{new_faq_id}/toggle-publish')
    assert toggle_res.status_code == 200
    assert toggle_res.get_json()['faq']['is_published'] is False

    # Delete FAQ
    del_res = admin_client.delete(f'/api/admin/faq/{new_faq_id}')
    assert del_res.status_code == 200

    # 9. Section 8: User Support History
    users_res = admin_client.get('/api/admin/support/users')
    assert users_res.status_code == 200
    users_list = users_res.get_json()['users']
    assert len(users_list) > 0

    target_user_id = test_ticket['user_id']
    hist_res = admin_client.get(f'/api/admin/support/users/{target_user_id}/history')
    assert hist_res.status_code == 200
    hist_data = hist_res.get_json()
    assert 'user' in hist_data
    assert 'tickets' in hist_data
    assert len(hist_data['tickets']) >= 1

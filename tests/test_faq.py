import pytest
from app import app, db, generate_confirmation_token
from models import User, FAQ, QuickQuestion, SupportTicket
from database import seed_faq_and_quick_questions


def create_user(client, email, password='Password123!', full_name='Test User', is_admin=False):
    """Helper to register, confirm, and optionally grant admin rights to a user."""
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
    """Helper to authenticate a client session."""
    return client.post('/login', json={'email': email, 'password': password})


def test_quick_questions_user_flow(client):
    """Verify that normal users can fetch active quick questions in display order."""
    with app.app_context():
        seed_faq_and_quick_questions()

    user_email = create_user(client, 'user_qq@example.com')
    login_client(client, user_email)

    resp = client.get('/api/quick-questions')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'quick_questions' in data
    qqs = data['quick_questions']
    assert len(qqs) >= 6

    # Verify order
    orders = [q['display_order'] for q in qqs]
    assert orders == sorted(orders)

    # Verify questions are active
    assert all(q['is_active'] is True for q in qqs)

    # Deactivate one question in DB and verify it is hidden from regular users
    with app.app_context():
        first_qq = QuickQuestion.query.first()
        first_qq.is_active = False
        target_id = first_qq.id
        db.session.commit()

    resp2 = client.get('/api/quick-questions')
    data2 = resp2.get_json()
    returned_ids = [q['id'] for q in data2['quick_questions']]
    assert target_id not in returned_ids


def test_faq_user_flow_and_filtering(client):
    """Verify published FAQ retrieval, category filtering, search, and hiding unpublished."""
    with app.app_context():
        seed_faq_and_quick_questions()

    user_email = create_user(client, 'user_faq@example.com')
    login_client(client, user_email)

    # 1. Fetch all published FAQs
    resp = client.get('/api/faq')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'faqs' in data
    assert data['total'] >= 10

    # 2. Category filtering
    resp_cat = client.get('/api/faq?category=Budget+Management')
    assert resp_cat.status_code == 200
    data_cat = resp_cat.get_json()
    assert len(data_cat['faqs']) > 0
    assert all(f['category'] == 'Budget Management' for f in data_cat['faqs'])

    # 3. Keyword search
    resp_search = client.get('/api/faq?q=spending')
    assert resp_search.status_code == 200
    data_search = resp_search.get_json()
    assert len(data_search['faqs']) > 0
    for f in data_search['faqs']:
        assert 'spending' in f['question'].lower() or 'spending' in f['answer'].lower()

    # 4. Hide unpublished FAQ from regular user
    with app.app_context():
        first_faq = FAQ.query.first()
        first_faq.is_published = False
        db.session.commit()
        unpub_id = first_faq.id

    resp_after = client.get('/api/faq')
    active_ids = [f['id'] for f in resp_after.get_json()['faqs']]
    assert unpub_id not in active_ids


def test_faq_admin_authorization_restrictions(client):
    """Verify non-admin and unauthenticated users are blocked from admin FAQ and QQ endpoints."""
    # Unauthenticated
    assert client.get('/api/admin/faq').status_code in (302, 401)
    assert client.post('/api/admin/faq', json={}).status_code in (302, 401)
    assert client.get('/api/admin/quick-questions').status_code in (302, 401)

    # Authenticated as standard user
    regular_email = create_user(client, 'regular_user@example.com', is_admin=False)
    login_client(client, regular_email)

    # Standard user receives 403 Forbidden
    assert client.get('/api/admin/faq').status_code == 403
    assert client.post('/api/admin/faq', json={'question': 'Q', 'answer': 'A', 'category': 'C'}).status_code == 403
    assert client.patch('/api/admin/faq/1', json={'is_published': False}).status_code == 403
    assert client.delete('/api/admin/faq/1').status_code == 403

    assert client.get('/api/admin/quick-questions').status_code == 403
    assert client.post('/api/admin/quick-questions', json={'question': 'Q', 'answer': 'A'}).status_code == 403
    assert client.patch('/api/admin/quick-questions/1', json={'is_active': False}).status_code == 403
    assert client.delete('/api/admin/quick-questions/1').status_code == 403
    assert client.post('/api/admin/quick-questions/reorder', json={'order': [1]}).status_code == 403


def test_admin_faq_crud_operations(client):
    """Verify administrator can create, view, update, and delete FAQs."""
    admin_email = create_user(client, 'admin_faq@example.com', is_admin=True)
    login_client(client, admin_email)

    # 1. Validation failure: missing fields
    resp_fail = client.post('/api/admin/faq', json={
        'question': 'Hi',
        'answer': 'No',
        'category': ''
    })
    assert resp_fail.status_code == 400

    # 2. Create valid FAQ
    resp_create = client.post('/api/admin/faq', json={
        'question': 'How do I change the display theme?',
        'answer': 'Click the sun/moon toggle button in the top navigation or press the T key.',
        'category': 'Account Management',
        'is_published': True
    })
    assert resp_create.status_code == 201
    created_faq = resp_create.get_json()['faq']
    faq_id = created_faq['id']
    assert created_faq['question'] == 'How do I change the display theme?'
    assert created_faq['is_published'] is True

    # 3. Admin list includes all FAQs
    resp_list = client.get('/api/admin/faq')
    assert resp_list.status_code == 200
    faq_ids = [f['id'] for f in resp_list.get_json()['faqs']]
    assert faq_id in faq_ids

    # 4. Admin update FAQ (unpublish)
    resp_update = client.patch(f'/api/admin/faq/{faq_id}', json={
        'is_published': False,
        'question': 'How do I toggle Dark Mode / Light Mode?'
    })
    assert resp_update.status_code == 200
    updated_faq = resp_update.get_json()['faq']
    assert updated_faq['is_published'] is False
    assert updated_faq['question'] == 'How do I toggle Dark Mode / Light Mode?'

    # 5. Admin delete FAQ
    resp_del = client.delete(f'/api/admin/faq/{faq_id}')
    assert resp_del.status_code == 200

    # Verify deleted
    with app.app_context():
        assert db.session.get(FAQ, faq_id) is None


def test_admin_quick_questions_crud_and_reorder(client):
    """Verify administrator can create, view, update, reorder, and delete quick questions."""
    admin_email = create_user(client, 'admin_qq@example.com', is_admin=True)
    login_client(client, admin_email)

    # 1. Validation failure
    resp_fail = client.post('/api/admin/quick-questions', json={
        'question': 'Q',
        'answer': 'A'
    })
    assert resp_fail.status_code == 400

    # 2. Create two quick questions
    resp_q1 = client.post('/api/admin/quick-questions', json={
        'question': 'Where can I see my net spending?',
        'answer': 'On the primary dashboard overview card.',
        'display_order': 1,
        'is_active': True
    })
    assert resp_q1.status_code == 201
    q1_id = resp_q1.get_json()['quick_question']['id']

    resp_q2 = client.post('/api/admin/quick-questions', json={
        'question': 'Are keyboard shortcuts supported?',
        'answer': 'Yes, press ? to view all keyboard shortcuts.',
        'display_order': 2,
        'is_active': True
    })
    assert resp_q2.status_code == 201
    q2_id = resp_q2.get_json()['quick_question']['id']

    # 3. Update quick question
    resp_up = client.patch(f'/api/admin/quick-questions/{q1_id}', json={
        'is_active': False
    })
    assert resp_up.status_code == 200
    assert resp_up.get_json()['quick_question']['is_active'] is False

    # 4. Reorder
    resp_reorder = client.post('/api/admin/quick-questions/reorder', json={
        'order': [q2_id, q1_id]
    })
    assert resp_reorder.status_code == 200

    with app.app_context():
        item2 = db.session.get(QuickQuestion, q2_id)
        item1 = db.session.get(QuickQuestion, q1_id)
        assert item2.display_order == 1
        assert item1.display_order == 2

    # 5. Delete quick question
    resp_del = client.delete(f'/api/admin/quick-questions/{q1_id}')
    assert resp_del.status_code == 200

    with app.app_context():
        assert db.session.get(QuickQuestion, q1_id) is None


def test_support_ticket_regression_with_faq(client):
    """Ensure existing support ticket submission and tracking continue to function cleanly."""
    user_email = create_user(client, 'regression_user@example.com')
    login_client(client, user_email)

    resp = client.post('/api/support/tickets', data={
        'category': 'Feature Request',
        'subject': 'Add multi-currency conversion support',
        'description': 'It would be great to support automatic currency conversion for international travel.'
    })
    assert resp.status_code == 201
    ticket = resp.get_json()['ticket']
    assert ticket['category'] == 'Feature Request'
    assert ticket['status'] == 'Open'

    # Retrieve user tickets
    resp_tickets = client.get('/api/support/tickets')
    assert resp_tickets.status_code == 200
    assert len(resp_tickets.get_json()['tickets']) >= 1

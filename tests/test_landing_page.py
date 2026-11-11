import pytest
from app import app, db, generate_confirmation_token
from models import User

def test_landing_page_renders_successfully(client):
    """Verify landing page serves 200 OK and contains proper metadata."""
    response = client.get('/')
    assert response.status_code == 200
    html = response.data.decode('utf-8')
    assert 'ExpenseFlow – Smart Expense Tracker' in html
    assert 'Track your expenses, manage budgets' in html
    assert '<meta name="viewport"' in html
    assert '/static/css/landing.css' in html
    assert '/static/js/landing.js' in html


def test_landing_page_required_sections_and_copy(client):
    """Verify all landing page sections and copy per specifications."""
    response = client.get('/')
    assert response.status_code == 200
    html = response.data.decode('utf-8')

    # Navigation items
    assert 'href="#home"' in html
    assert 'href="#features"' in html
    assert 'href="#how-it-works"' in html
    assert 'href="#dashboard-preview"' in html
    assert 'href="#about"' in html

    # Unauthenticated state navigation actions
    assert 'href="/login"' in html
    assert 'href="/register"' in html

    # Hero section required text
    assert 'Take Control of Your Money.' in html
    assert 'Build Better Financial Habits.' in html
    assert 'Track your expenses, manage budgets, understand your spending patterns, and make smarter financial decisions — all in one place.' in html
    assert "Get Started – It's Free" in html
    assert 'Explore Features' in html

    # Hero dashboard visual preview indicators
    assert 'Total Spent' in html
    assert 'This Month' in html
    assert 'Daily Average' in html
    assert 'Top Category' in html
    assert 'Spending Trajectory' in html
    assert 'Recent Transactions' in html
    assert 'Monthly Budget Ceiling' in html

    # Features (all 6 required)
    assert 'Expense Management' in html
    assert 'Easily record, categorize, edit, and manage daily transactions.' in html

    assert 'Expense Categorization' in html
    assert 'Organize expenses into meaningful categories to understand spending habits.' in html

    assert 'Budget Management' in html
    assert 'Set monthly budgets and track your spending against your limits.' in html

    assert 'Financial Analytics' in html
    assert 'Visualize expenses through interactive charts and category breakdowns.' in html

    assert 'Transaction History' in html
    assert 'Review previous transactions and search your financial records.' in html

    assert 'Reports and Export' in html
    assert 'Generate and download financial reports in PDF format' in html

    # How it works (all 3 steps)
    assert 'Create Your Account' in html
    assert 'Sign up and access your personal expense dashboard.' in html

    assert 'Track Your Expenses' in html
    assert 'Add expenses and organize them into meaningful categories.' in html

    assert 'Analyze Your Spending' in html
    assert 'Understand your financial habits and make better decisions.' in html

    # Dashboard preview showcase items
    assert 'Spending Trend' in html
    assert 'Category Breakdown' in html
    assert 'Recent Ledger' in html
    assert 'Budget Tracking' in html

    # Why Choose ExpenseFlow items
    assert 'Why Choose ExpenseFlow?' in html
    assert 'Simple and Intuitive Interface' in html
    assert 'Organized Financial Tracking' in html
    assert 'Better Spending Awareness' in html
    assert 'Accessible Across Devices' in html
    assert 'Secure Account-Based Access' in html

    # CTA section
    assert 'Your Financial Clarity Starts Today.' in html
    assert 'Start tracking your money, understanding your spending, and building better financial habits.' in html
    assert 'Get Started for Free' in html

    # Footer elements and legal modals
    assert '2026 ExpenseFlow. All rights reserved.' in html
    assert 'All Systems Operational' in html
    assert 'contact-modal' in html
    assert 'privacy-modal' in html
    assert 'terms-modal' in html


def test_landing_page_authenticated_user_navigation(client):
    """When a user is logged in, verify landing page surfaces Dashboard and Logout."""
    # Register and verify a user
    resp = client.post('/register', json={
        'full_name': 'Landing User',
        'email': 'landing@example.com',
        'password': 'Secret123!'
    })
    assert resp.status_code == 201
    token = generate_confirmation_token('landing@example.com')
    client.get(f'/confirm/{token}')

    # Login
    login_resp = client.post('/login', json={'email': 'landing@example.com', 'password': 'Secret123!'})
    assert login_resp.status_code == 200

    # Fetch landing page
    response = client.get('/')
    assert response.status_code == 200
    html = response.data.decode('utf-8')

    # Authenticated user should see dashboard and logout in nav
    assert 'href="/dashboard"' in html
    assert 'href="/logout"' in html

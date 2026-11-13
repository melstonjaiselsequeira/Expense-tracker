import io
import pytest
from datetime import datetime, date
from app import app, db
from models import User, Expense, ReportHistory

def register_and_login(client, email, password='Password123!', full_name='Report User'):
    """Helper to register, verify, and log in a user."""
    from app import generate_confirmation_token
    client.post('/register', json={
        'full_name': full_name,
        'email': email,
        'password': password
    })
    token = generate_confirmation_token(email)
    client.get(f'/confirm/{token}')
    login_resp = client.post('/login', json={'email': email, 'password': password})
    assert login_resp.status_code == 200
    return email

def create_expense(client, amount, category, description, date_str, status='paid'):
    """Helper to post an expense through the API."""
    resp = client.post('/api/expenses', json={
        'amount': amount,
        'category': category,
        'description': description,
        'date': date_str,
        'status': status
    })
    assert resp.status_code == 201
    return resp.get_json()


def test_legacy_export_endpoints_preserved(client):
    """Verify that existing legacy /api/export and /api/report endpoints still work."""
    email = register_and_login(client, 'legacy_rep@example.com')
    create_expense(client, 45.0, 'Food', 'Groceries', '2025-01-15')

    # Test legacy CSV
    csv_resp = client.get('/api/export')
    assert csv_resp.status_code == 200
    assert 'text/csv' in csv_resp.content_type
    assert b'Groceries' in csv_resp.data

    # Test legacy monthly PDF
    pdf_resp = client.get('/api/report/2025/1')
    assert pdf_resp.status_code == 200
    assert 'application/pdf' in pdf_resp.content_type
    assert pdf_resp.data.startswith(b'%PDF')


def test_monthly_report_downloads_january_2025(client):
    """Verify January 2025 historical monthly downloads in PDF, CSV, and XLSX formats."""
    email = register_and_login(client, 'jan2025_user@example.com')
    create_expense(client, 120.50, 'Food', 'January Supermarket', '2025-01-10', 'paid')
    create_expense(client, 85.00, 'Bills', 'January Electric Bill', '2025-01-20', 'paid')
    create_expense(client, 50.00, 'Entertainment', 'Movie tickets', '2025-01-25', 'planned')
    # Out of range expense
    create_expense(client, 200.00, 'Shopping', 'February Shoes', '2025-02-05', 'paid')

    # 1. Monthly PDF
    pdf_resp = client.get('/api/reports/download?period_type=monthly&year=2025&month=1&format=pdf')
    assert pdf_resp.status_code == 200
    assert 'application/pdf' in pdf_resp.content_type
    assert pdf_resp.data.startswith(b'%PDF')
    assert 'ExpenseFlow_January_2025.pdf' in pdf_resp.headers.get('Content-Disposition', '')

    # 2. Monthly CSV
    csv_resp = client.get('/api/reports/download?period_type=monthly&year=2025&month=1&format=csv')
    assert csv_resp.status_code == 200
    assert 'text/csv' in csv_resp.content_type
    csv_text = csv_resp.data.decode('utf-8')
    assert 'January Supermarket' in csv_text
    assert 'January Electric Bill' in csv_text
    assert 'Movie tickets' in csv_text
    assert 'February Shoes' not in csv_text  # Filtered out
    assert 'ExpenseFlow_January_2025.csv' in csv_resp.headers.get('Content-Disposition', '')

    # 3. Monthly Excel (XLSX)
    xlsx_resp = client.get('/api/reports/download?period_type=monthly&year=2025&month=1&format=xlsx')
    assert xlsx_resp.status_code == 200
    assert 'openxmlformats' in xlsx_resp.content_type
    assert 'ExpenseFlow_January_2025.xlsx' in xlsx_resp.headers.get('Content-Disposition', '')


def test_yearly_report_downloads(client):
    """Verify yearly report downloads include all transactions in that year across months."""
    email = register_and_login(client, 'year_rep_user@example.com')
    create_expense(client, 100.0, 'Transport', 'Q1 Train Pass', '2024-03-12')
    create_expense(client, 250.0, 'Health', 'Q3 Dental Checkup', '2024-08-15')
    create_expense(client, 300.0, 'Shopping', 'Q4 Holiday Gifts', '2024-12-20')
    # 2025 transaction should not be in 2024 report
    create_expense(client, 400.0, 'Education', '2025 Course', '2025-01-10')

    # Test Yearly CSV
    csv_resp = client.get('/api/reports/download?period_type=yearly&year=2024&format=csv')
    assert csv_resp.status_code == 200
    csv_text = csv_resp.data.decode('utf-8')
    assert 'Q1 Train Pass' in csv_text
    assert 'Q3 Dental Checkup' in csv_text
    assert 'Q4 Holiday Gifts' in csv_text
    assert '2025 Course' not in csv_text
    assert 'ExpenseFlow_Year_2024.csv' in csv_resp.headers.get('Content-Disposition', '')

    # Test Yearly Excel
    xlsx_resp = client.get('/api/reports/download?period_type=yearly&year=2024&format=xlsx')
    assert xlsx_resp.status_code == 200
    assert 'ExpenseFlow_Year_2024.xlsx' in xlsx_resp.headers.get('Content-Disposition', '')


def test_custom_date_range_downloads(client):
    """Verify custom date ranges filter transactions strictly between start and end dates."""
    email = register_and_login(client, 'custom_range_user@example.com')
    create_expense(client, 30.0, 'Food', 'Day 1 Dinner', '2025-06-10')
    create_expense(client, 45.0, 'Food', 'Day 3 Lunch', '2025-06-12')
    create_expense(client, 60.0, 'Food', 'Day 5 Party', '2025-06-15')
    create_expense(client, 90.0, 'Transport', 'Flight Ticket', '2025-06-25')

    # Query 2025-06-11 to 2025-06-16 (should include Day 3 and Day 5 only)
    resp = client.get('/api/reports/download?period_type=custom&start_date=2025-06-11&end_date=2025-06-16&format=csv')
    assert resp.status_code == 200
    csv_text = resp.data.decode('utf-8')
    assert 'Day 3 Lunch' in csv_text
    assert 'Day 5 Party' in csv_text
    assert 'Day 1 Dinner' not in csv_text
    assert 'Flight Ticket' not in csv_text
    assert 'ExpenseFlow_Custom_Report.csv' in resp.headers.get('Content-Disposition', '')


def test_user_data_isolation_in_reports(client):
    """Ensure user A cannot see user B's transactions in generated reports."""
    user_a = register_and_login(client, 'user_a@example.com', full_name='Alice User')
    create_expense(client, 500.0, 'Bills', 'Alice Rent Payment', '2025-04-01')

    # Log in as user B
    user_b = register_and_login(client, 'user_b@example.com', full_name='Bob User')
    create_expense(client, 75.0, 'Food', 'Bob Dining Out', '2025-04-05')

    # Bob downloads April 2025 report
    resp = client.get('/api/reports/download?period_type=monthly&year=2025&month=4&format=csv')
    assert resp.status_code == 200
    csv_text = resp.data.decode('utf-8')
    assert 'Bob Dining Out' in csv_text
    assert 'Alice Rent Payment' not in csv_text


def test_empty_period_and_validation_errors(client):
    """Ensure proper error responses for empty periods, invalid dates, and invalid formats."""
    email = register_and_login(client, 'empty_rep_user@example.com')

    # 1. Empty period (no expenses in 2022)
    resp = client.get('/api/reports/download?period_type=monthly&year=2022&month=1&format=pdf')
    assert resp.status_code == 404
    data = resp.get_json()
    assert 'no transactions found' in data['error'].lower()

    # 2. Invalid date range (start > end)
    resp_invalid = client.get('/api/reports/download?period_type=custom&start_date=2025-12-31&end_date=2025-01-01&format=csv')
    assert resp_invalid.status_code == 400
    assert 'cannot be after' in resp_invalid.get_json()['error'].lower()

    # 3. Invalid month
    resp_month = client.get('/api/reports/download?period_type=monthly&year=2025&month=13&format=pdf')
    assert resp_month.status_code == 400
    assert 'between 1 and 12' in resp_month.get_json()['error'].lower()

    # 4. Invalid format
    resp_fmt = client.get('/api/reports/download?period_type=monthly&year=2025&month=1&format=docx')
    assert resp_fmt.status_code == 400
    assert 'unsupported export format' in resp_fmt.get_json()['error'].lower()


def test_report_history_creation_and_listing(client):
    """Verify that successful report downloads create history records and /api/reports/history lists them."""
    email = register_and_login(client, 'history_user@example.com')
    create_expense(client, 150.0, 'Bills', 'Internet Bill', '2025-05-10')

    # Initially, history is empty
    hist_resp = client.get('/api/reports/history')
    assert hist_resp.status_code == 200
    assert hist_resp.get_json()['history'] == []
    assert hist_resp.get_json()['total'] == 0

    # 1. Download monthly report in PDF
    dl_pdf = client.get('/api/reports/download?period_type=monthly&year=2025&month=5&format=pdf')
    assert dl_pdf.status_code == 200

    # Check history contains 1 record
    hist_resp2 = client.get('/api/reports/history')
    assert hist_resp2.status_code == 200
    history = hist_resp2.get_json()['history']
    assert len(history) == 1
    assert history[0]['report_name'] == 'May 2025'
    assert history[0]['report_type'] == 'Monthly'
    assert history[0]['format'] == 'PDF'
    assert history[0]['start_date'] == '2025-05-01'
    assert history[0]['end_date'] == '2025-05-31'

    # 2. Download yearly report in CSV
    dl_csv = client.get('/api/reports/download?period_type=yearly&year=2025&format=csv')
    assert dl_csv.status_code == 200

    # Check history contains 2 records, most recent first
    hist_resp3 = client.get('/api/reports/history')
    history3 = hist_resp3.get_json()['history']
    assert len(history3) == 2
    assert history3[0]['report_name'] == 'Year 2025'
    assert history3[0]['report_type'] == 'Yearly'
    assert history3[0]['format'] == 'CSV'


def test_failed_report_generation_does_not_create_history(client):
    """Verify that 404 (no transactions) and 400 (validation errors) do NOT create history records."""
    email = register_and_login(client, 'fail_hist_user@example.com')

    # 404 empty period
    resp_404 = client.get('/api/reports/download?period_type=monthly&year=2021&month=1&format=pdf')
    assert resp_404.status_code == 404

    # 400 bad date range
    resp_400 = client.get('/api/reports/download?period_type=custom&start_date=2025-12-31&end_date=2025-01-01&format=csv')
    assert resp_400.status_code == 400

    # History should still be empty
    hist_resp = client.get('/api/reports/history')
    assert hist_resp.status_code == 200
    assert len(hist_resp.get_json()['history']) == 0


def test_download_again_regenerates_report(client):
    """Verify that /api/reports/download-again/<id> regenerates and streams the report from metadata."""
    email = register_and_login(client, 'dl_again_user@example.com')
    create_expense(client, 99.0, 'Shopping', 'New Jacket', '2025-07-14')

    # Download initial report
    dl_resp = client.get('/api/reports/download?period_type=monthly&year=2025&month=7&format=csv')
    assert dl_resp.status_code == 200

    # Retrieve history ID
    hist_resp = client.get('/api/reports/history')
    records = hist_resp.get_json()['history']
    assert len(records) == 1
    report_id = records[0]['id']

    # Now download again
    again_resp = client.get(f'/api/reports/download-again/{report_id}')
    assert again_resp.status_code == 200
    assert 'text/csv' in again_resp.content_type
    assert 'ExpenseFlow_July_2025.csv' in again_resp.headers.get('Content-Disposition', '')
    csv_text = again_resp.data.decode('utf-8')
    assert 'New Jacket' in csv_text
    assert '99.00' in csv_text


def test_report_history_user_isolation(client):
    """Verify that User B cannot see User A's history or access User A's reports via download-again."""
    # User A generates a report
    register_and_login(client, 'user_a_hist@example.com', full_name='User A')
    create_expense(client, 200.0, 'Health', 'Doctor Appointment', '2025-08-10')
    dl_resp = client.get('/api/reports/download?period_type=monthly&year=2025&month=8&format=pdf')
    assert dl_resp.status_code == 200

    hist_resp_a = client.get('/api/reports/history')
    records_a = hist_resp_a.get_json()['history']
    assert len(records_a) == 1
    report_id_a = records_a[0]['id']

    # User B logs in
    register_and_login(client, 'user_b_hist@example.com', full_name='User B')
    hist_resp_b = client.get('/api/reports/history')
    records_b = hist_resp_b.get_json()['history']
    assert len(records_b) == 0  # User B cannot see User A's history

    # User B attempts to download User A's report by ID
    unauth_resp = client.get(f'/api/reports/download-again/{report_id_a}')
    assert unauth_resp.status_code == 404
    assert 'unauthorized' in unauth_resp.get_json()['error'].lower() or 'not found' in unauth_resp.get_json()['error'].lower()


def test_report_history_deduplication(client):
    """Verify rapid re-clicks on the same report parameters within 30 seconds do not duplicate history entries."""
    email = register_and_login(client, 'dedup_user@example.com')
    create_expense(client, 40.0, 'Food', 'Quick Lunch', '2025-09-05')

    # Rapid successive requests with exact same parameters
    r1 = client.get('/api/reports/download?period_type=monthly&year=2025&month=9&format=csv')
    r2 = client.get('/api/reports/download?period_type=monthly&year=2025&month=9&format=csv')
    assert r1.status_code == 200
    assert r2.status_code == 200

    # History should only have 1 entry due to 30s de-duplication window
    hist_resp = client.get('/api/reports/history')
    records = hist_resp.get_json()['history']
    assert len(records) == 1


def test_instant_statement_report_export(client):
    """Verify that instant report export (/api/report/<year>/<month>) downloads the current month without tracking in history."""
    email = register_and_login(client, 'instant_rep_user@example.com')
    now = datetime.utcnow()
    current_year = now.year
    current_month = now.month
    create_expense(client, 88.0, 'Bills', 'Monthly Electricity', f"{current_year}-{current_month:02d}-01")

    # Call the instant report endpoint
    resp = client.get(f'/api/report/{current_year}/{current_month}')
    assert resp.status_code == 200
    assert 'application/pdf' in resp.content_type
    assert resp.data.startswith(b'%PDF')
    assert f'report_{current_year}_{current_month:02d}.pdf' in resp.headers.get('Content-Disposition', '')

    # Verify that instant report is NOT tracked in report history
    hist_resp = client.get('/api/reports/history')
    assert hist_resp.status_code == 200
    history = hist_resp.get_json()['history']
    assert len(history) == 0




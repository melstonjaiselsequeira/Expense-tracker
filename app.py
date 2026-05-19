import os
import csv
import io
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, Response
from flask_cors import CORS
from database import db, init_db
from models import Expense

# ── App Configuration ──────────────────────────────────────────────
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///expenses.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
CORS(app)

init_db(app)


# ── Seed sample data ──────────────────────────────────────────────
def seed_data():
    """Add sample expenses if the database is empty."""
    with app.app_context():
        if Expense.query.count() == 0:
            samples = [
                Expense(amount=45.50, category='Food', description='Groceries from supermarket', date=datetime.now().date() - timedelta(days=1)),
                Expense(amount=12.00, category='Transport', description='Uber ride to office', date=datetime.now().date()),
                Expense(amount=250.00, category='Bills', description='Electricity bill payment', date=datetime.now().date() - timedelta(days=5)),
                Expense(amount=89.99, category='Shopping', description='New running shoes', date=datetime.now().date() - timedelta(days=3)),
                Expense(amount=15.00, category='Entertainment', description='Netflix subscription', date=datetime.now().date() - timedelta(days=7)),
                Expense(amount=35.00, category='Health', description='Pharmacy medicines', date=datetime.now().date() - timedelta(days=2)),
                Expense(amount=120.00, category='Education', description='Online course subscription', date=datetime.now().date() - timedelta(days=10)),
                Expense(amount=28.50, category='Food', description='Dinner at restaurant', date=datetime.now().date() - timedelta(days=4)),
                Expense(amount=55.00, category='Transport', description='Monthly metro pass', date=datetime.now().date() - timedelta(days=8)),
                Expense(amount=199.00, category='Shopping', description='Wireless headphones', date=datetime.now().date() - timedelta(days=6)),
                Expense(amount=75.00, category='Bills', description='Internet bill', date=datetime.now().date() - timedelta(days=12)),
                Expense(amount=22.00, category='Food', description='Coffee and snacks', date=datetime.now().date() - timedelta(days=9)),
                Expense(amount=40.00, category='Entertainment', description='Movie tickets', date=datetime.now().date() - timedelta(days=11)),
                Expense(amount=500.00, category='Bills', description='Rent contribution', date=datetime.now().date() - timedelta(days=15)),
                Expense(amount=18.00, category='Health', description='Gym day pass', date=datetime.now().date() - timedelta(days=13)),
            ]
            db.session.add_all(samples)
            db.session.commit()
            print("[OK] Sample data seeded successfully!")

seed_data()


# ── Page Routes ───────────────────────────────────────────────────
@app.route('/')
def index():
    """Serve the main single-page application."""
    return render_template('index.html')


# ── API: List / Filter Expenses ───────────────────────────────────
@app.route('/api/expenses', methods=['GET'])
def get_expenses():
    """Get all expenses with optional filtering."""
    query = Expense.query

    # Filter by category
    category = request.args.get('category')
    if category and category != 'All':
        query = query.filter(Expense.category == category)

    # Filter by date range
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    if start_date:
        query = query.filter(Expense.date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        query = query.filter(Expense.date <= datetime.strptime(end_date, '%Y-%m-%d').date())

    # Search by description
    search = request.args.get('search')
    if search:
        query = query.filter(Expense.description.ilike(f'%{search}%'))

    # Sort
    sort = request.args.get('sort', 'date_desc')
    if sort == 'date_asc':
        query = query.order_by(Expense.date.asc())
    elif sort == 'amount_desc':
        query = query.order_by(Expense.amount.desc())
    elif sort == 'amount_asc':
        query = query.order_by(Expense.amount.asc())
    else:
        query = query.order_by(Expense.date.desc())

    expenses = query.all()
    return jsonify([e.to_dict() for e in expenses])


# ── API: Create Expense ──────────────────────────────────────────
@app.route('/api/expenses', methods=['POST'])
def create_expense():
    """Create a new expense."""
    data = request.get_json()

    if not data or not data.get('amount') or not data.get('category') or not data.get('description'):
        return jsonify({'error': 'Missing required fields: amount, category, description'}), 400

    try:
        expense = Expense(
            amount=float(data['amount']),
            category=data['category'],
            description=data['description'],
            date=datetime.strptime(data.get('date', datetime.now().strftime('%Y-%m-%d')), '%Y-%m-%d').date()
        )
        db.session.add(expense)
        db.session.commit()
        return jsonify(expense.to_dict()), 201
    except (ValueError, TypeError) as e:
        return jsonify({'error': f'Invalid data: {str(e)}'}), 400


# ── API: Update Expense ──────────────────────────────────────────
@app.route('/api/expenses/<int:expense_id>', methods=['PUT'])
def update_expense(expense_id):
    """Update an existing expense."""
    expense = Expense.query.get_or_404(expense_id)
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    try:
        if 'amount' in data:
            expense.amount = float(data['amount'])
        if 'category' in data:
            expense.category = data['category']
        if 'description' in data:
            expense.description = data['description']
        if 'date' in data:
            expense.date = datetime.strptime(data['date'], '%Y-%m-%d').date()

        db.session.commit()
        return jsonify(expense.to_dict())
    except (ValueError, TypeError) as e:
        return jsonify({'error': f'Invalid data: {str(e)}'}), 400


# ── API: Delete Expense ──────────────────────────────────────────
@app.route('/api/expenses/<int:expense_id>', methods=['DELETE'])
def delete_expense(expense_id):
    """Delete an expense."""
    expense = Expense.query.get_or_404(expense_id)
    db.session.delete(expense)
    db.session.commit()
    return jsonify({'message': 'Expense deleted successfully'})


# ── API: Dashboard Statistics ─────────────────────────────────────
@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get dashboard statistics."""
    expenses = Expense.query.all()

    if not expenses:
        return jsonify({
            'total': 0,
            'monthly': 0,
            'daily_avg': 0,
            'count': 0,
            'category_breakdown': {},
            'daily_trend': {},
            'top_category': 'N/A'
        })

    total = sum(e.amount for e in expenses)

    # Monthly total (current month)
    now = datetime.now()
    monthly_expenses = [e for e in expenses if e.date.month == now.month and e.date.year == now.year]
    monthly = sum(e.amount for e in monthly_expenses)

    # Daily average
    if expenses:
        dates = [e.date for e in expenses]
        date_range = (max(dates) - min(dates)).days + 1
        daily_avg = total / max(date_range, 1)
    else:
        daily_avg = 0

    # Category breakdown
    category_breakdown = {}
    for e in expenses:
        category_breakdown[e.category] = category_breakdown.get(e.category, 0) + e.amount

    # Top category
    top_category = max(category_breakdown, key=category_breakdown.get) if category_breakdown else 'N/A'

    # Daily trend (last 30 days)
    daily_trend = {}
    for i in range(29, -1, -1):
        day = (now - timedelta(days=i)).date()
        day_str = day.isoformat()
        daily_trend[day_str] = sum(e.amount for e in expenses if e.date == day)

    # Monthly trend (last 6 months)
    monthly_trend = {}
    for i in range(5, -1, -1):
        month_date = now - timedelta(days=i * 30)
        month_key = month_date.strftime('%Y-%m')
        month_label = month_date.strftime('%b %Y')
        monthly_trend[month_label] = sum(
            e.amount for e in expenses
            if e.date.strftime('%Y-%m') == month_key
        )

    return jsonify({
        'total': round(total, 2),
        'monthly': round(monthly, 2),
        'daily_avg': round(daily_avg, 2),
        'count': len(expenses),
        'category_breakdown': category_breakdown,
        'daily_trend': daily_trend,
        'monthly_trend': monthly_trend,
        'top_category': top_category
    })


# ── API: Export CSV ───────────────────────────────────────────────
@app.route('/api/export', methods=['GET'])
def export_csv():
    """Export all expenses as CSV."""
    expenses = Expense.query.order_by(Expense.date.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Date', 'Category', 'Description', 'Amount'])

    for e in expenses:
        writer.writerow([e.id, e.date.isoformat(), e.category, e.description, f'{e.amount:.2f}'])

    csv_content = output.getvalue()
    output.close()

    return Response(
        csv_content,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=expenses.csv'}
    )


# ── Run ───────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True, port=5000)

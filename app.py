import os
import csv
import io
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, Response, redirect, url_for, flash, session
from flask_cors import CORS
from flask_login import LoginManager, login_user, logout_user, current_user, login_required
from flask_wtf import CSRFProtect
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from itsdangerous import URLSafeTimedSerializer
from dotenv import load_dotenv
from email.utils import formataddr

load_dotenv()

from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

from database import db, init_db
from models import Expense, User

# ── App Configuration ───
app = Flask(__name__)

# Reverse proxy support (Gunicorn, Nginx, Heroku, Render, Cloudflare)
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Database configuration: supports PostgreSQL (DATABASE_URL / SQLALCHEMY_DATABASE_URI) with SQLite fallback
db_url = os.getenv('DATABASE_URL') or os.getenv('SQLALCHEMY_DATABASE_URI') or 'sqlite:///expenses.db'
if db_url.startswith('postgres://'):
    db_url = db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url

# Production connection pooling and resilience for PostgreSQL
if not db_url.startswith('sqlite'):
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': int(os.getenv('DB_POOL_SIZE', 10)),
        'max_overflow': int(os.getenv('DB_MAX_OVERFLOW', 20)),
        'pool_recycle': int(os.getenv('DB_POOL_RECYCLE', 300)),
        'pool_pre_ping': True,
    }

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['RATELIMIT_ENABLED'] = True

# Session & Cookie Security
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', 'False').lower() in ('true', '1')
app.config['SESSION_PERMANENT'] = False

# Initialise extensions
storage_uri = os.getenv('RATELIMIT_STORAGE_URI') or os.getenv('REDIS_URL') or 'memory://'
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=storage_uri
)

migrate = Migrate(app, db)
CORS(app)
csrf = CSRFProtect(app)
# Disable CSRF protection for API endpoints (easier for testing and API clients)
app.config['WTF_CSRF_ENABLED'] = False
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    user = db.session.get(User, int(user_id))
    if user and not user.is_verified:
        return None
    return user

# Security Headers
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

# Standard JSON error responses for API clients
@app.errorhandler(429)
def ratelimit_handler(e):
    if request.is_json or request.path.startswith('/api/'):
        return jsonify({'error': 'Rate limit exceeded. Please try again later.'}), 429
    return jsonify({'error': 'Rate limit exceeded. Please try again later.'}), 429

@app.errorhandler(404)
def not_found_handler(e):
    if request.is_json or request.path.startswith('/api/'):
        return jsonify({'error': 'Resource not found'}), 404
    return render_template('index.html'), 404

@app.errorhandler(500)
def server_error_handler(e):
    db.session.rollback()
    if request.is_json or request.path.startswith('/api/'):
        return jsonify({'error': 'Internal server error'}), 500
    return jsonify({'error': 'Internal server error'}), 500







init_db(app)

# ── Seed sample data (disabled during migrations) ───
# Uncomment the following line to seed data in a development environment after migrations have been applied.
# seed_data()

# ── Page Routes ──
# Authentication routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        if current_user.is_authenticated and current_user.is_verified:
            return redirect(url_for('dashboard'))
        if current_user.is_authenticated and not current_user.is_verified:
            logout_user()
            session.clear()
        return render_template('register.html')
    if request.method == 'POST':
        # Clear any existing session so new registration starts completely fresh
        logout_user()
        session.clear()

        data = request.get_json()
        full_name = data.get('full_name')
        email = data.get('email')
        password = data.get('password')
        if not full_name or not email or not password:
            return jsonify({'error': 'Missing required fields'}), 400
        if User.query.filter_by(email=email.lower()).first():
            return jsonify({'error': 'Email already registered'}), 400
        user = User(full_name=full_name, email=email.lower())
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        token = generate_confirmation_token(user.email)
        confirm_url = url_for('confirm_email', token=token, _external=True)
        html_content = build_email_html(
            title="Confirm your email address<br>to start tracking with ExpenseFlow",
            recipient_email=user.email,
            description_text=f"You can start tracking with ExpenseFlow right away once you've confirmed that <a href=\"mailto:{user.email}\" style=\"color: #8b5cf6; text-decoration: underline;\">{user.email}</a> is your email. Click the button below to confirm.",
            button_text="Confirm Email Address",
            button_url=confirm_url
        )
        send_email(
            user.email,
            'Confirm your account — ExpenseFlow',
            f'Please click to confirm: {confirm_url}',
            html_body=html_content
        )
        return jsonify({'message': 'Registration successful! Please verify email & log in to continue.'}), 201
    else:
        return render_template('register.html')

@app.route('/confirm/<token>')
def confirm_email(token):
    email = confirm_token(token)
    if not email:
        if request.is_json or (request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html):
            return jsonify({'error': 'Invalid or expired token'}), 400
        return render_template('login.html', error='Invalid or expired confirmation link.'), 400
    user = User.query.filter_by(email=email).first_or_404()
    if not user.is_verified:
        user.is_verified = True
        db.session.commit()
    # Ensure any previous session is cleared so user logs in afresh after verification
    logout_user()
    session.clear()
    if request.is_json or (request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html):
        return jsonify({'message': 'Email verified successfully'}), 200
    return render_template('verified.html', email=email), 200

# ── Resend Verification Email ──────────────────────────────────────
@app.route('/resend-verification', methods=['POST'])
@csrf.exempt
@limiter.limit("5 per minute")
def resend_verification():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    if not email:
        return jsonify({'error': 'Email is required'}), 400
    user = User.query.filter_by(email=email).first()
    # Always respond with success to prevent user enumeration
    if user and not user.is_verified:
        token = generate_confirmation_token(user.email)
        confirm_url = url_for('confirm_email', token=token, _external=True)
        html_content = build_email_html(
            title="Confirm your email address<br>to start tracking with ExpenseFlow",
            recipient_email=user.email,
            description_text=f"You can start tracking with ExpenseFlow right away once you've confirmed that <a href=\"mailto:{user.email}\" style=\"color: #8b5cf6; text-decoration: underline;\">{user.email}</a> is your email. Click the button below to confirm.",
            button_text="Confirm Email Address",
            button_url=confirm_url
        )
        send_email(
            user.email,
            'Confirm your account — ExpenseFlow',
            f'Please click to confirm: {confirm_url}',
            html_body=html_content
        )
    return jsonify({'message': 'If an unverified account exists with that email, a fresh verification link has been sent!'}), 200

@app.route('/login', methods=['GET', 'POST'])
@csrf.exempt
def login():
    if request.method == 'GET':
        if current_user.is_authenticated and current_user.is_verified:
            return redirect(url_for('dashboard'))
        if current_user.is_authenticated and not current_user.is_verified:
            logout_user()
            session.clear()
        return render_template('login.html')
    if request.method == 'POST':
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Missing JSON payload'}), 400
        email = data.get('email')
        password = data.get('password')
        if not email or not password:
            return jsonify({'error': 'Email and password required'}), 400
        user = User.query.filter_by(email=email.strip().lower()).first()
        if not user:
            return jsonify({
                'error': 'Account not found. Please sign up to continue.',
                'code': 'USER_NOT_FOUND'
            }), 404

        if not user.check_password(password):
            return jsonify({
                'error': 'Incorrect password. Please try again.',
                'code': 'INVALID_PASSWORD'
            }), 401

        if not user.is_verified:
            return jsonify({
                'error': 'Email not verified. Please verify your email before logging in.',
                'code': 'EMAIL_NOT_VERIFIED'
            }), 403

        session.permanent = False
        login_user(user, remember=False)
        return jsonify({
            'message': 'Login successful! Welcome back.'
        }), 200
    else:
        return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    if request.is_json or (request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html):
        return jsonify({'message': 'Logged out'}), 200
    return redirect(url_for('login'))

# Home page route
@app.route('/')
def index():
    """Serve the application: landing page for visitors, dashboard for logged-in users."""
    if current_user.is_authenticated and current_user.is_verified:
        return render_template('dashboard.html')
    if current_user.is_authenticated and not current_user.is_verified:
        logout_user()
        session.clear()
    return render_template('index.html')

# Authenticated Dashboard route
@app.route('/dashboard')
@login_required
def dashboard():
    """Serve the main authenticated expense dashboard."""
    if not current_user.is_verified:
        logout_user()
        session.clear()
        return redirect(url_for('login'))
    return render_template('dashboard.html')

# Password reset
@app.route('/reset-password-request', methods=['POST'])
@csrf.exempt
@limiter.limit("5 per minute")
def reset_password_request():
    data = request.get_json()
    email = data.get('email')
    user = User.query.filter_by(email=email.lower()).first()
    # Always respond with success to avoid enumeration
    if user:
        token = generate_confirmation_token(user.email)
        reset_url = url_for('reset_password', token=token, _external=True)
        html_content = build_email_html(
            title="Reset your password<br>for ExpenseFlow",
            recipient_email=user.email,
            description_text=f"We received a request to reset the password for <a href=\"mailto:{user.email}\" style=\"color: #8b5cf6; text-decoration: underline;\">{user.email}</a>. Click the button below to choose a new password.",
            button_text="Reset Password",
            button_url=reset_url
        )
        send_email(
            user.email,
            'Password Reset — ExpenseFlow',
            f'Click to reset password: {reset_url}',
            html_body=html_content
        )
    return jsonify({'message': 'If the email exists, a reset link has been sent'}), 200


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
@csrf.exempt
def reset_password(token):
    if request.method == 'POST':
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Missing JSON payload'}), 400
        new_password = data.get('password')
        if not new_password:
            return jsonify({'error': 'Password required'}), 400
        email = confirm_token(token)
        if not email:
            return jsonify({'error': 'Invalid or expired token'}), 400
        user = User.query.filter_by(email=email).first_or_404()
        user.set_password(new_password)
        db.session.commit()
        return jsonify({'message': 'Password has been reset'}), 200
    else:
        return render_template('reset_password.html')

# Helper functions for token and email
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet


def generate_confirmation_token(email):
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return serializer.dumps(email, salt='email-confirm')

def confirm_token(token, expiration=3600):
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    try:
        email = serializer.loads(token, salt='email-confirm', max_age=expiration)
    except Exception:
        return None
    return email

DEFAULT_LOGO_URL = os.getenv(
    'LOGO_URL',
    'https://cdn.jsdelivr.net/gh/melstonjaiselsequeira/Expense-tracker@main/static/img/logo_email.png'
)

def build_email_html(title, recipient_email, description_text, button_text, button_url, note_text=None):
    if not note_text:
        note_text = "If you didn't request for this, you can safely ignore this email."

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title.replace('<br>', ' ')}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #ffffff; margin: 0; padding: 40px 20px;">
    <tr>
      <td align="left" style="padding: 0;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width: 520px; margin: 0 auto; text-align: left;">
          <!-- Rounded Logo Box -->
          <tr>
            <td style="padding-bottom: 24px;">
              <table cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td align="center" valign="middle" style="width: 44px; height: 44px; border: 1px solid #e5e7eb; border-radius: 10px; background-color: #ffffff; text-align: center; vertical-align: middle;">
                    <img src="{DEFAULT_LOGO_URL}" alt="ExpenseFlow Logo" width="30" height="30" style="display: block; width: 30px; height: 30px; margin: auto; border: 0;" />
                  </td>
                  <td style="padding-left: 12px; vertical-align: middle;">
                    <span style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 20px; font-weight: 800; color: #111827; letter-spacing: -0.4px;">Expense<span style="color: #8b5cf6;">Flow</span></span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Heading -->
          <tr>
            <td style="padding-bottom: 18px;">
              <h1 style="margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 24px; font-weight: 700; line-height: 1.35; color: #111827; letter-spacing: -0.3px;">
                {title}
              </h1>
            </td>
          </tr>

          <!-- Description with Highlighted Email -->
          <tr>
            <td style="padding-bottom: 28px;">
              <p style="margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 15px; line-height: 1.6; color: #374151;">
                {description_text}
              </p>
            </td>
          </tr>

          <!-- Primary CTA Button (ExpenseFlow Purple) -->
          <tr>
            <td style="padding-bottom: 28px;">
              <table cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td align="center" style="border-radius: 6px; background-color: #7c3aed; background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%);">
                    <a href="{button_url}" target="_blank" style="display: inline-block; padding: 12px 24px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 14px; font-weight: 600; color: #ffffff; text-decoration: none; border-radius: 6px; letter-spacing: -0.1px;">
                      {button_text}
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Security Note -->
          <tr>
            <td style="padding-bottom: 36px;">
              <p style="margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 14px; line-height: 1.5; color: #6b7280;">
                {note_text}
              </p>
            </td>
          </tr>

          <!-- Divider -->
          <tr>
            <td>
              <hr style="border: none; border-top: 1px solid #f3f4f6; margin: 0 0 24px 0;">
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td>
              <table cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td valign="middle" style="padding-right: 8px;">
                    <img src="{DEFAULT_LOGO_URL}" alt="ExpenseFlow Logo" width="16" height="16" style="display: block; width: 16px; height: 16px; border: 0;" />
                  </td>
                  <td valign="middle" style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 12px; color: #9ca3af; line-height: 1.4;">
                    ExpenseFlow &bull; Smart Expense Tracking &amp; Budget Management
                  </td>
                </tr>
              </table>
              <p style="margin: 8px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 12px; color: #9ca3af; line-height: 1.4;">
                This email was sent to <a href="mailto:{recipient_email}" style="color: #6b7280; text-decoration: underline;">{recipient_email}</a>.
              </p>
              <p style="margin: 12px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 12px; color: #9ca3af; line-height: 1.5; word-break: break-all;">
                Button not working? Paste this link into your browser:<br>
                <a href="{button_url}" style="color: #8b5cf6; text-decoration: underline;">{button_url}</a>
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def send_email(to, subject, body, html_body=None):
    # Simple SMTP email; configure via environment variables
    import smtplib, os
    from email.message import EmailMessage
    if app.config.get('TESTING'):
        return
    smtp_server = os.getenv('SMTP_SERVER')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    smtp_user = os.getenv('SMTP_USER')
    smtp_password = os.getenv('SMTP_PASSWORD')
    from_email = os.getenv('FROM_EMAIL') or smtp_user
    if not smtp_server or not smtp_user or not smtp_password or smtp_server == 'smtp.example.com':
        print(f"\n[DEV MODE - EMAIL NOT SENT TO SMTP]\nTo: {to}\nSubject: {subject}\n{body}\n")
        return
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = formataddr(("ExpenseFlow", from_email))
    msg['To'] = to
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype='html')
    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
            print(f'Successfully sent email to {to} from {from_email}', flush=True)
    except Exception as e:
        print(f'Failed to send email to {to}: {e}', flush=True)


# ── API List / Filter Expenses ────
@app.route('/api/expenses', methods=['GET'])
@login_required
def get_expenses():
    """Get all expenses for the logged‑in user with optional filtering."""
    query = Expense.query.filter_by(user_id=current_user.id)

    # Filter by category
    category = request.args.get('category')
    if category and category != 'All':
        query = query.filter(Expense.category == category)

    # Filter by status (all, paid, planned)
    status_filter = request.args.get('status')
    if status_filter and status_filter.lower() in ('paid', 'planned'):
        query = query.filter(Expense.status == status_filter.lower())

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
        query = query.filter(Expense.description.ilike(f"%{search}%"))

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

# ── API Create Expense ────
@app.route('/api/expenses', methods=['POST'])
@login_required
def create_expense():
    """Create a new expense for the current user."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Missing JSON payload'}), 400
    if not data or not data.get('amount') or not data.get('category') or not data.get('description'):
        return jsonify({'error': 'Missing required fields amount, category, description'}), 400
    try:
        exp_date = datetime.strptime(data.get('date', datetime.now().strftime('%Y-%m-%d')), '%Y-%m-%d').date()
        raw_status = data.get('status')
        if raw_status and raw_status.lower() in ('paid', 'planned'):
            exp_status = raw_status.lower()
        elif exp_date > datetime.now().date():
            exp_status = 'planned'
        else:
            exp_status = 'paid'

        expense = Expense(
            amount=float(data['amount']),
            category=data['category'],
            description=data['description'],
            date=exp_date,
            status=exp_status,
            user_id=current_user.id,
        )
        db.session.add(expense)
        db.session.commit()
        return jsonify(expense.to_dict()), 201
    except (ValueError, TypeError) as e:
        return jsonify({'error': f'Invalid data {str(e)}'}), 400

# ── API Update Expense ──────────
@app.route('/api/expenses/<int:expense_id>', methods=['PUT'])
@login_required
def update_expense(expense_id):
    """Update an existing expense for the current user."""
    expense = db.get_or_404(Expense, expense_id)
    if expense.user_id != current_user.id:
        return jsonify({'error': 'Forbidden'}), 403
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Missing JSON payload'}), 400
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
        if 'status' in data and data['status'].lower() in ('paid', 'planned'):
            expense.status = data['status'].lower()
        db.session.commit()
        return jsonify(expense.to_dict())
    except (ValueError, TypeError) as e:
        return jsonify({'error': f'Invalid data {str(e)}'}), 400

# ── API Mark Expense Paid ───────────────────────────────────────
@app.route('/api/expenses/<int:expense_id>/mark-paid', methods=['POST', 'PUT'])
@login_required
def mark_expense_paid(expense_id):
    """Mark a planned expense as paid in-place without duplication."""
    expense = db.get_or_404(Expense, expense_id)
    if expense.user_id != current_user.id:
        return jsonify({'error': 'Forbidden'}), 403
    expense.status = 'paid'
    db.session.commit()
    return jsonify({
        'message': 'Expense marked as paid',
        'expense': expense.to_dict()
    })

# ── API Delete Expense ──────────────────────────────────────────
@app.route('/api/expenses/<int:expense_id>', methods=['DELETE'])
@login_required
def delete_expense(expense_id):
    # Ensure the expense belongs to the current user
    expense = db.get_or_404(Expense, expense_id)
    if expense.user_id != current_user.id:
        return jsonify({'error': 'Forbidden'}), 403
    db.session.delete(expense)
    db.session.commit()
    return jsonify({'message': 'Expense deleted successfully'})


# ── API Export CSV ───────────────────────────────────────────────
@app.route('/api/export', methods=['GET'])
@login_required
def export_csv():
    """Export expenses for the current user as CSV."""
    expenses = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Date', 'Category', 'Description', 'Amount', 'Status'])
    for e in expenses:
        writer.writerow([e.id, e.date.isoformat(), e.category, e.description, e.amount, e.status or 'paid'])
    csv_content = output.getvalue()
    output.close()
    return Response(
        csv_content,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=expenses.csv'}
    )

@app.route('/api/stats', methods=['GET'])
@login_required
def get_stats():
    """Get dashboard statistics for the logged‑in user."""
    user_budget = float(current_user.monthly_budget) if getattr(current_user, 'monthly_budget', None) is not None else 1000.0
    all_expenses = Expense.query.filter_by(user_id=current_user.id).all()
    
    # Strictly separate paid expenses (actual spending) from planned expenses
    paid_expenses = [e for e in all_expenses if (e.status or 'paid') == 'paid']
    planned_expenses = [e for e in all_expenses if (e.status or 'paid') == 'planned']

    now = datetime.now()
    monthly_paid = [e for e in paid_expenses if e.date.month == now.month and e.date.year == now.year]
    monthly_planned = [e for e in planned_expenses if e.date.month == now.month and e.date.year == now.year]

    total = sum(e.amount for e in paid_expenses)
    monthly = sum(e.amount for e in monthly_paid)
    planned_total = sum(e.amount for e in planned_expenses)
    planned_monthly = sum(e.amount for e in monthly_planned)

    if not paid_expenses:
        daily_avg = 0
    else:
        dates = [e.date for e in paid_expenses]
        date_range = (max(dates) - min(dates)).days + 1
        daily_avg = total / max(date_range, 1)

    # Category breakdown (only actual paid spending)
    category_breakdown = {}
    for e in paid_expenses:
        category_breakdown[e.category] = category_breakdown.get(e.category, 0) + e.amount
    top_category = max(category_breakdown, key=category_breakdown.get) if category_breakdown else 'N/A'

    # Daily trend (last 30 days of actual paid spending)
    daily_trend = {}
    for i in range(29, -1, -1):
        day = (now - timedelta(days=i)).date()
        day_str = day.isoformat()
        daily_trend[day_str] = sum(e.amount for e in paid_expenses if e.date == day)

    # Monthly trend (last 6 months of actual paid spending)
    monthly_trend = {}
    for i in range(5, -1, -1):
        month_date = now - timedelta(days=i * 30)
        month_key = month_date.strftime('%Y-%m')
        month_label = month_date.strftime('%b %Y')
        monthly_trend[month_label] = sum(e.amount for e in paid_expenses if e.date.strftime('%Y-%m') == month_key)

    return jsonify({
        'total': round(total, 2),
        'monthly': round(monthly, 2),
        'daily_avg': round(daily_avg, 2),
        'count': len(paid_expenses),
        'category_breakdown': category_breakdown,
        'daily_trend': daily_trend,
        'monthly_trend': monthly_trend,
        'top_category': top_category,
        'monthly_budget': user_budget,
        'planned_count': len(planned_expenses),
        'planned_total': round(planned_total, 2),
        'planned_monthly': round(planned_monthly, 2)
    })


@app.route('/api/budget', methods=['GET', 'POST', 'PUT'])
@login_required
def budget():
    """Get or update current user's monthly budget."""
    if request.method == 'GET':
        budget_val = float(current_user.monthly_budget) if getattr(current_user, 'monthly_budget', None) is not None else 1000.0
        return jsonify({'monthly_budget': budget_val})

    data = request.get_json(silent=True) or {}
    val = data.get('monthly_budget') if 'monthly_budget' in data else data.get('amount')
    try:
        amount = float(val)
        if amount <= 0:
            return jsonify({'error': 'Budget must be greater than zero'}), 400
        current_user.monthly_budget = round(amount, 2)
        db.session.commit()
        return jsonify({
            'message': 'Budget updated successfully',
            'monthly_budget': current_user.monthly_budget
        })
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid budget amount'}), 400





# ── PDF Report Generation ───────────────────────────────────────
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

def generate_pdf(user, year, month):
    """Generate a PDF report for a given user and month.
    Returns a BytesIO object containing the PDF data.
    """
    # Filter expenses for the month
    start_date = datetime(year, month, 1).date()
    # calculate last day of month
    if month == 12:
        end_date = datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1).date() - timedelta(days=1)
    expenses = Expense.query.filter(
        Expense.user_id == user.id,
        Expense.date >= start_date,
        Expense.date <= end_date
    ).order_by(Expense.date).all()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    # Title
    title = Paragraph(f"Monthly Expense Report - {start_date.strftime('%B %Y')}", styles['Title'])
    elements.append(title)
    elements.append(Paragraph(f"User: {user.full_name} ({user.email})", styles['Normal']))
    elements.append(Paragraph(f"Generated on: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", styles['Normal']))
    elements.append(Paragraph(" ", styles['Normal']))

    # Table data
    data = [['Date', 'Category', 'Description', 'Status', 'Amount']]
    paid_total = 0.0
    planned_total = 0.0
    for e in expenses:
        st = (e.status or 'paid').capitalize()
        data.append([
            e.date.strftime('%Y-%m-%d'),
            e.category,
            e.description,
            st,
            f"${e.amount:,.2f}"
        ])
        if (e.status or 'paid') == 'paid':
            paid_total += e.amount
        else:
            planned_total += e.amount
    if not expenses:
        data.append(['-', '-', 'No expenses for this month', '-', '-'])
    table = Table(data, colWidths=[1.2*inch, 1.3*inch, 2.3*inch, 1.0*inch, 1.0*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('ALIGN', (-1,1), (-1,-1), 'RIGHT'),
    ]))
    elements.append(table)
    elements.append(Paragraph(" ", styles['Normal']))
    elements.append(Paragraph(f"Total Paid Expenses: ${paid_total:,.2f}", styles['Heading2']))
    if planned_total > 0:
        elements.append(Paragraph(f"Planned Commitments (Pending Payment): ${planned_total:,.2f}", styles['Normal']))

    doc.build(elements)
    buffer.seek(0)
    return buffer

@app.route('/api/report/<int:year>/<int:month>', methods=['GET'])
@login_required
def download_report(year, month):
    """Endpoint to download PDF report for the logged‑in user."""
    try:
        pdf_buffer = generate_pdf(current_user, year, month)
        return Response(
            pdf_buffer.getvalue(),
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename=report_{year}_{month:02d}.pdf'
            }
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── Email with attachment helper ───────────────────────────────────
def send_email_with_attachment(to, subject, body, attachment_bytes, filename):
    import smtplib, os
    from email.message import EmailMessage
    from email.mime.application import MIMEApplication
    if app.config.get('TESTING'):
        return
    smtp_server = os.getenv('SMTP_SERVER')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    smtp_user = os.getenv('SMTP_USER')
    smtp_password = os.getenv('SMTP_PASSWORD')
    from_email = os.getenv('FROM_EMAIL') or smtp_user
    if not smtp_server or not smtp_user or not smtp_password or smtp_server == 'smtp.example.com':
        print(f"\n[DEV MODE - EMAIL NOT SENT TO SMTP]\nTo: {to}\nSubject: {subject}\n{body}\n")
        return
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = formataddr(("ExpenseFlow", from_email))
    msg['To'] = to
    msg.set_content(body)
    # attachment
    part = MIMEApplication(attachment_bytes, Name=filename)
    part['Content-Disposition'] = f'attachment; filename="{filename}"'
    msg.attach(part)
    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
            print(f'Successfully sent report email to {to} from {from_email}', flush=True)
    except Exception as e:
        print(f'Failed to send report email to {to}: {e}', flush=True)

# ── Scheduler for Monthly Emails ───────────────────────────────────
# Attempt to import APScheduler; if unavailable, fallback to no scheduler
try:
    from flask_apscheduler import APScheduler
    scheduler_available = True
except ImportError:
    scheduler_available = False
    # Simple placeholder class
    class APScheduler:
        def init_app(self, app):
            pass
        def start(self):
            pass

def send_monthly_reports():
    """Generate and email last month's report to each verified user."""
    with app.app_context():
        now = datetime.utcnow()
        # previous month
        first_of_current = datetime(now.year, now.month, 1)
        last_month_end = first_of_current - timedelta(days=1)
        year = last_month_end.year
        month = last_month_end.month
        users = User.query.filter_by(is_verified=True).all()
        for user in users:
            try:
                pdf_buf = generate_pdf(user, year, month)
                subject = f"Your Expense Report for {last_month_end.strftime('%B %Y')}"
                body = f"Hello {user.full_name},\n\nPlease find attached your expense report for {last_month_end.strftime('%B %Y')}.\n\nBest regards,\nExpenseFlow Team"
                send_email_with_attachment(user.email, subject, body, pdf_buf.getvalue(), f'report_{year}_{month:02d}.pdf')
            except Exception as e:
                print(f'Failed to send report to {user.email}: {e}')

class Config:
    SCHEDULER_API_ENABLED = True
    # Run at 08:00 UTC on the first day of each month
    JOBS = [
        {
            'id': 'monthly_report',
            'func': send_monthly_reports,
            'trigger': 'cron',
            'day': 1,
            'hour': 8,
            'minute': 0,
        }
    ]

scheduler = APScheduler()
app.config.from_object(Config())
scheduler.init_app(app)
scheduler.start()

# ── Run ───────────────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() in ('true', '1')
    app.run(host='0.0.0.0', port=port, debug=debug)


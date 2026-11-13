import os
import csv
import io
import uuid
from functools import wraps
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, Response, redirect, url_for, flash, session, has_request_context, send_from_directory
from flask_cors import CORS
from flask_login import LoginManager, login_user, logout_user, current_user, login_required
from flask_wtf import CSRFProtect
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from itsdangerous import URLSafeTimedSerializer
from dotenv import load_dotenv
from email.utils import formataddr
from werkzeug.utils import secure_filename

load_dotenv()

from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

from database import db, init_db
from models import Expense, User, SupportTicket, TicketMessage, FAQ, QuickQuestion, ReportHistory

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

# ── URL Detection Helper (Auto-detects live HTTPS domain or local host) ──
def get_app_url():
    """Detects the live application URL automatically (works in localhost and after deployment)."""
    if os.getenv('APP_URL'):
        return os.getenv('APP_URL').rstrip('/')
    if has_request_context():
        scheme = request.headers.get('X-Forwarded-Proto', request.scheme)
        host = request.headers.get('X-Forwarded-Host', request.host)
        return f"{scheme}://{host}"
    return 'http://127.0.0.1:5000'

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
        admin_emails = [e.strip().lower() for e in os.getenv('ADMIN_EMAILS', '').split(',') if e.strip()]
        if email.lower() in admin_emails:
            user.is_admin = True
            user.is_verified = True
        db.session.add(user)
        db.session.commit()
        token = generate_confirmation_token(user.email)
        confirm_url = f"{get_app_url()}/confirm/{token}"
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
        confirm_url = f"{get_app_url()}/confirm/{token}"
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
            'message': 'Login successful! Welcome back.',
            'is_admin': user.is_admin_user,
            'redirect_url': '/dashboard?view=admin-dashboard' if user.is_admin_user else '/dashboard'
        }), 200
    else:
        return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    session.clear()
    if request.is_json or (request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html):
        resp = jsonify({'message': 'Logged out'})
        resp.delete_cookie('session')
        resp.delete_cookie('remember_token')
        return resp, 200
    resp = redirect(url_for('index'))
    resp.delete_cookie('session')
    resp.delete_cookie('remember_token')
    return resp

# Home page route
@app.route('/')
def index():
    """Serve the application: landing page for visitors, dashboard for logged-in users."""
    if current_user.is_authenticated and current_user.is_verified:
        if current_user.is_admin_user:
            return redirect(url_for('dashboard') + '?view=admin-dashboard')
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
    view = request.args.get('view')
    if not view and current_user.is_admin_user:
        return redirect(url_for('dashboard') + '?view=admin-dashboard')
    active_view = view or ('admin-dashboard' if current_user.is_admin_user else 'dashboard')
    return render_template('dashboard.html', active_view=active_view)

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
        reset_url = f"{get_app_url()}/reset-password/{token}"
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


def send_via_brevo_api(to, subject, html_body, text_body, attachment_bytes=None, filename=None):
    """Sends an email using Brevo's HTTPS REST API over port 443 (bypasses all cloud firewalls)."""
    import urllib.request, json, os, base64
    api_key = os.getenv('BREVO_API_KEY')
    if not api_key:
        return False
    from_email = os.getenv('FROM_EMAIL') or 'nmj.kompany@gmail.com'
    url = 'https://api.brevo.com/v3/smtp/email'
    payload = {
        'sender': {'name': 'ExpenseFlow', 'email': from_email},
        'to': [{'email': to}],
        'subject': subject,
        'htmlContent': html_body or text_body,
        'textContent': text_body
    }
    if attachment_bytes and filename:
        payload['attachment'] = [{
            'name': filename,
            'content': base64.b64encode(attachment_bytes).decode('utf-8')
        }]
    headers = {
        'api-key': api_key,
        'Content-Type': 'application/json',
        'accept': 'application/json'
    }
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in (200, 201):
                print(f'Successfully sent email to {to} from {from_email} via Brevo HTTPS API', flush=True)
                return True
    except Exception as e:
        print(f'Brevo HTTPS API error for {to}: {e}', flush=True)
    return False


def send_email(to, subject, body, html_body=None):
    # Simple SMTP / HTTPS API email; configure via environment variables
    import smtplib, os
    from email.message import EmailMessage
    if app.config.get('TESTING'):
        return

    # 1. Primary for Cloud / Render: Brevo REST API over HTTPS (Port 443)
    if os.getenv('BREVO_API_KEY'):
        if send_via_brevo_api(to, subject, html_body, body):
            return

    # 2. Fallback to standard SMTP (for localhost or direct SMTP)
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


# ── Support & Help System ──────────────────────────────────────
SUPPORT_ATTACHMENT_DIR = os.path.join(app.root_path, 'static', 'uploads', 'support_attachments')
os.makedirs(SUPPORT_ATTACHMENT_DIR, exist_ok=True)
ALLOWED_ATTACHMENT_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
MAX_ATTACHMENT_SIZE = 5 * 1024 * 1024  # 5 MB


def admin_required(f):
    """Decorator to restrict access to authenticated administrators."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': 'Authentication required', 'code': 'UNAUTHORIZED'}), 401
        if not getattr(current_user, 'is_admin_user', False):
            return jsonify({'error': 'Admin authorization required', 'code': 'FORBIDDEN'}), 403
        return f(*args, **kwargs)
    return decorated_function


def generate_ticket_id():
    """Generate a clean, professional ticket ID like TKT-20261112-AB12."""
    date_str = datetime.utcnow().strftime('%Y%m%d')
    rand_hex = uuid.uuid4().hex[:6].upper()
    return f"TKT-{date_str}-{rand_hex}"


@app.route('/support')
@login_required
def support_redirect():
    """Convenience redirect to Help & Support view in dashboard."""
    return redirect(url_for('dashboard') + '?view=support')


@app.route('/admin')
@login_required
@admin_required
def admin_root_redirect():
    """Convenience redirect to Admin Dashboard in dashboard."""
    return redirect(url_for('dashboard') + '?view=admin-dashboard')


@app.route('/admin/support')
@login_required
@admin_required
def admin_support_redirect():
    """Convenience redirect to Admin Support view in dashboard."""
    return redirect(url_for('dashboard') + '?view=admin-dashboard')


@app.route('/api/support/tickets', methods=['POST'])
@login_required
@csrf.exempt
def submit_support_ticket():
    """Submit a new support ticket with optional screenshot attachment."""
    # Handle form data (multipart or urlencoded) or json
    if request.is_json:
        data = request.get_json(silent=True) or {}
        category = (data.get('category') or '').strip()
        subject = (data.get('subject') or '').strip()
        description = (data.get('description') or '').strip()
        attachment = None
    else:
        category = (request.form.get('category') or '').strip()
        subject = (request.form.get('subject') or '').strip()
        description = (request.form.get('description') or '').strip()
        attachment = request.files.get('attachment') if request.files else None

    # Validation
    valid_categories = ['General Query', 'Report a Problem', 'Feature Request']
    if category not in valid_categories:
        return jsonify({'error': f'Invalid category. Choose from: {", ".join(valid_categories)}'}), 400

    if not subject or len(subject) < 3 or len(subject) > 200:
        return jsonify({'error': 'Subject must be between 3 and 200 characters'}), 400

    if not description or len(description) < 10 or len(description) > 4000:
        return jsonify({'error': 'Message must be between 10 and 4000 characters'}), 400

    saved_filename = None
    if attachment and attachment.filename:
        filename = secure_filename(attachment.filename)
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        if ext not in ALLOWED_ATTACHMENT_EXTENSIONS:
            return jsonify({'error': 'Attachment must be an approved image format (PNG, JPG, JPEG, WEBP, GIF)'}), 400

        # Check attachment size
        attachment.seek(0, os.SEEK_END)
        size = attachment.tell()
        attachment.seek(0)
        if size > MAX_ATTACHMENT_SIZE:
            return jsonify({'error': 'Attachment exceeds maximum allowed size of 5 MB'}), 400

        ticket_ref = uuid.uuid4().hex[:8]
        saved_filename = f"tkt_{ticket_ref}_{uuid.uuid4().hex[:6]}.{ext}"
        attachment.save(os.path.join(SUPPORT_ATTACHMENT_DIR, saved_filename))

    ticket_id = generate_ticket_id()
    ticket = SupportTicket(
        ticket_id=ticket_id,
        user_id=current_user.id,
        category=category,
        subject=subject,
        description=description,
        attachment_path=saved_filename,
        status='Open'
    )
    db.session.add(ticket)
    db.session.commit()

    # Dispatch email notifications safely (failures do not block ticket creation)
    try:
        support_email = os.getenv('SUPPORT_EMAIL') or os.getenv('FROM_EMAIL')
        if support_email:
            admin_notify_html = build_email_html(
                title=f"New Support Ticket: {ticket_id}",
                recipient_email=support_email,
                description_text=(
                    f"A new support ticket has been submitted by <strong>{current_user.full_name}</strong> "
                    f"({current_user.email}).<br><br>"
                    f"<strong>Category:</strong> {category}<br>"
                    f"<strong>Subject:</strong> {subject}<br>"
                    f"<strong>Message:</strong><br><blockquote style='margin:10px 0; padding:10px 14px; background:#f8fafc; border-left:3px solid #8b5cf6;'>{description}</blockquote>"
                ),
                button_text="View in Admin Support",
                button_url=url_for('admin_support_redirect', _external=True)
            )
            send_email(
                support_email,
                f"[{ticket_id}] New Support Ticket: {subject}",
                f"New support ticket from {current_user.full_name} ({current_user.email}):\n\nCategory: {category}\nSubject: {subject}\n\n{description}",
                html_body=admin_notify_html
            )

        # Receipt to user
        user_receipt_html = build_email_html(
            title=f"Support Request Received ({ticket_id})",
            recipient_email=current_user.email,
            description_text=(
                f"Hello {current_user.full_name},<br><br>"
                f"We have received your support request (<strong>{ticket_id}</strong>) regarding <em>\"{subject}\"</em>. "
                f"Our support team has been notified and is reviewing your request.<br><br>"
                f"You can monitor the status and updates of this ticket directly in your ExpenseFlow dashboard under <strong>Help & Support</strong>."
            ),
            button_text="View My Tickets",
            button_url=url_for('support_redirect', _external=True)
        )
        send_email(
            current_user.email,
            f"Support Request Received — {ticket_id}",
            f"Hello {current_user.full_name},\n\nWe received your support ticket {ticket_id} regarding '{subject}'. You can view status in your dashboard.",
            html_body=user_receipt_html
        )
    except Exception as e:
        print(f"Notice: Support email dispatch non-blocking log: {e}", flush=True)

    return jsonify({
        'message': 'Your support request has been submitted successfully!',
        'ticket': ticket.to_dict()
    }), 201


@app.route('/api/support/tickets', methods=['GET'])
@login_required
def get_user_support_tickets():
    """Fetch all support tickets belonging to the authenticated user."""
    tickets = SupportTicket.query.filter_by(user_id=current_user.id).order_by(SupportTicket.created_at.desc()).all()
    return jsonify({
        'tickets': [t.to_dict() for t in tickets],
        'total': len(tickets)
    }), 200


@app.route('/api/support/tickets/<int:ticket_id>', methods=['GET'])
@login_required
def get_support_ticket_detail(ticket_id):
    """Retrieve full details for a specific support ticket with ownership validation."""
    ticket = db.session.get(SupportTicket, ticket_id)
    if not ticket:
        return jsonify({'error': 'Support ticket not found'}), 404

    # Ownership check: user can only view their own ticket, unless admin
    if ticket.user_id != current_user.id and not current_user.is_admin_user:
        return jsonify({'error': 'Unauthorized to view this support ticket', 'code': 'FORBIDDEN'}), 403

    return jsonify({
        'ticket': ticket.to_dict(include_user=current_user.is_admin_user)
    }), 200


@app.route('/api/support/attachments/<filename>', methods=['GET'])
@login_required
def get_support_attachment(filename):
    """Securely serve a ticket attachment to the ticket owner or an administrator."""
    # Prevent path traversal
    safe_name = secure_filename(filename)
    if not safe_name or safe_name != filename:
        return jsonify({'error': 'Invalid attachment filename'}), 400

    ticket = SupportTicket.query.filter_by(attachment_path=safe_name).first()
    if not ticket:
        return jsonify({'error': 'Attachment not found'}), 404

    # Verify authorization
    if ticket.user_id != current_user.id and not current_user.is_admin_user:
        return jsonify({'error': 'Access denied to attachment', 'code': 'FORBIDDEN'}), 403

    return send_from_directory(SUPPORT_ATTACHMENT_DIR, safe_name)


@app.route('/api/admin/support/dashboard', methods=['GET'])
@login_required
@admin_required
def admin_support_dashboard():
    """Summary statistics and recently submitted tickets for Support Dashboard (Admin only)."""
    total_tickets = SupportTicket.query.count()
    open_tickets = SupportTicket.query.filter_by(status='Open').count()
    in_progress_tickets = SupportTicket.query.filter_by(status='In Progress').count()
    resolved_tickets = SupportTicket.query.filter(SupportTicket.status.in_(['Resolved', 'Closed'])).count()
    closed_tickets = SupportTicket.query.filter_by(status='Closed').count()

    # Category counts
    queries_count = SupportTicket.query.filter_by(category='General Query').count()
    problems_count = SupportTicket.query.filter_by(category='Report a Problem').count()
    features_count = SupportTicket.query.filter_by(category='Feature Request').count()

    # Recent tickets
    recent_tickets = SupportTicket.query.order_by(SupportTicket.created_at.desc()).limit(8).all()
    active_users_count = db.session.query(SupportTicket.user_id).distinct().count()

    return jsonify({
        'stats': {
            'total_tickets': total_tickets,
            'open_tickets': open_tickets,
            'in_progress_tickets': in_progress_tickets,
            'resolved_tickets': resolved_tickets,
            'closed_tickets': closed_tickets,
            'active_users_count': active_users_count,
            'by_category': {
                'general_query': queries_count,
                'report_problem': problems_count,
                'feature_request': features_count,
            }
        },
        'recent_tickets': [t.to_dict(include_user=True) for t in recent_tickets]
    }), 200


@app.route('/api/admin/support/tickets', methods=['GET'])
@login_required
@admin_required
def admin_list_support_tickets():
    """List all support tickets across all users with search, filtering, and sorting (Admin only)."""
    query = SupportTicket.query.join(User)

    status_filter = request.args.get('status', '').strip()
    if status_filter and status_filter != 'All':
        query = query.filter(SupportTicket.status == status_filter)

    category_filter = request.args.get('category', '').strip()
    if category_filter and category_filter != 'All':
        query = query.filter(SupportTicket.category == category_filter)

    user_id_filter = request.args.get('user_id', type=int)
    if user_id_filter:
        query = query.filter(SupportTicket.user_id == user_id_filter)

    search = request.args.get('search', '').strip()
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            db.or_(
                SupportTicket.ticket_id.ilike(search_pattern),
                SupportTicket.subject.ilike(search_pattern),
                SupportTicket.description.ilike(search_pattern),
                User.email.ilike(search_pattern),
                User.full_name.ilike(search_pattern)
            )
        )

    sort = request.args.get('sort', 'date_desc').strip()
    if sort == 'date_asc':
        query = query.order_by(SupportTicket.created_at.asc())
    elif sort == 'status':
        query = query.order_by(SupportTicket.status.asc(), SupportTicket.created_at.desc())
    elif sort == 'ticket_id':
        query = query.order_by(SupportTicket.ticket_id.asc())
    else:
        query = query.order_by(SupportTicket.created_at.desc())

    tickets = query.all()
    return jsonify({
        'tickets': [t.to_dict(include_user=True) for t in tickets],
        'total': len(tickets)
    }), 200


@app.route('/api/admin/support/tickets/<int:ticket_id>', methods=['PATCH'])
@login_required
@admin_required
@csrf.exempt
def admin_update_support_ticket(ticket_id):
    """Update ticket status and admin notes (Admin only)."""
    ticket = db.session.get(SupportTicket, ticket_id)
    if not ticket:
        return jsonify({'error': 'Support ticket not found'}), 404

    data = request.get_json(silent=True) or {}
    status = data.get('status')
    admin_notes = data.get('admin_notes')

    valid_statuses = ['Open', 'Pending', 'In Progress', 'Resolved', 'Closed', 'Rejected']
    if status is not None:
        if status not in valid_statuses:
            return jsonify({'error': f'Invalid status. Choose from: {", ".join(valid_statuses)}'}), 400
        ticket.status = status

    if admin_notes is not None:
        ticket.admin_notes = admin_notes.strip()

    ticket.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'message': 'Ticket updated successfully',
        'ticket': ticket.to_dict(include_user=True)
    }), 200


@app.route('/api/admin/support/tickets/<int:ticket_id>/conversation', methods=['GET'])
@login_required
@admin_required
def admin_get_ticket_conversation(ticket_id):
    """Fetch ticket details and full conversation history (Admin only)."""
    ticket = db.session.get(SupportTicket, ticket_id)
    if not ticket:
        return jsonify({'error': 'Support ticket not found'}), 404

    conversation = [{
        'id': 0,
        'ticket_id': ticket.id,
        'sender_type': 'user',
        'sender_id': ticket.user_id,
        'sender_name': ticket.user.full_name if ticket.user else 'Customer',
        'sender_email': ticket.user.email if ticket.user else '',
        'message': ticket.description,
        'attachment_path': ticket.attachment_path,
        'has_attachment': bool(ticket.attachment_path),
        'created_at': ticket.created_at.isoformat(),
        'is_initial': True
    }]

    for msg in ticket.messages:
        conversation.append(msg.to_dict())

    user_ticket_count = SupportTicket.query.filter_by(user_id=ticket.user_id).count() if ticket.user_id else 0

    return jsonify({
        'ticket': ticket.to_dict(include_user=True),
        'conversation': conversation,
        'user_ticket_count': user_ticket_count
    }), 200


@app.route('/api/admin/support/tickets/<int:ticket_id>/reply', methods=['POST'])
@login_required
@admin_required
@csrf.exempt
def admin_reply_support_ticket(ticket_id):
    """Send an administrative reply to a support ticket and optionally update its status."""
    ticket = db.session.get(SupportTicket, ticket_id)
    if not ticket:
        return jsonify({'error': 'Support ticket not found'}), 404

    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    new_status = (data.get('status') or '').strip()

    if not message:
        return jsonify({'error': 'Reply message cannot be empty', 'code': 'VALIDATION_ERROR'}), 400

    valid_statuses = ['Open', 'Pending', 'In Progress', 'Resolved', 'Closed', 'Rejected']
    if new_status and new_status in valid_statuses:
        ticket.status = new_status
    elif ticket.status == 'Open':
        ticket.status = 'In Progress'

    reply = TicketMessage(
        ticket_id=ticket.id,
        sender_type='admin',
        sender_id=current_user.id,
        sender_name=current_user.full_name or 'Support Administrator',
        sender_email=current_user.email,
        message=message
    )
    ticket.updated_at = datetime.utcnow()
    db.session.add(reply)
    db.session.commit()

    # Non-blocking email dispatch to ticket owner
    try:
        if ticket.user and ticket.user.email:
            reply_email_html = build_email_html(
                title=f"Update on Support Ticket {ticket.ticket_id}",
                recipient_email=ticket.user.email,
                description_text=(
                    f"Hello {ticket.user.full_name},<br><br>"
                    f"Our support team has posted a reply regarding your request <strong>\"{ticket.subject}\"</strong>:<br><br>"
                    f"<blockquote style='margin:10px 0; padding:12px 16px; background:#f8fafc; border-left:3px solid #8b5cf6; font-size:14px; line-height:1.6;'>{message}</blockquote><br>"
                    f"<strong>Current Status:</strong> {ticket.status}<br><br>"
                    f"You can view the full conversation directly in your ExpenseFlow dashboard under Help & Support."
                ),
                button_text="View in ExpenseFlow",
                button_url=url_for('support_redirect', _external=True)
            )
            send_email(
                ticket.user.email,
                f"[{ticket.ticket_id}] Response from Support: {ticket.subject}",
                f"Hello {ticket.user.full_name},\n\nSupport response for {ticket.ticket_id}:\n\n{message}\n\nCurrent Status: {ticket.status}",
                html_body=reply_email_html
            )
    except Exception as e:
        print(f"Notice: Admin reply notification email log: {e}", flush=True)

    return jsonify({
        'message': 'Reply sent successfully',
        'reply': reply.to_dict(),
        'ticket': ticket.to_dict(include_user=True)
    }), 201


@app.route('/api/support/tickets/<int:ticket_id>/conversation', methods=['GET'])
@login_required
def get_user_ticket_conversation(ticket_id):
    """Retrieve full conversation history for the ticket owner or an administrator."""
    ticket = db.session.get(SupportTicket, ticket_id)
    if not ticket:
        return jsonify({'error': 'Support ticket not found'}), 404
    if ticket.user_id != current_user.id and not current_user.is_admin_user:
        return jsonify({'error': 'Unauthorized to view this conversation', 'code': 'FORBIDDEN'}), 403

    conversation = [{
        'id': 0,
        'ticket_id': ticket.id,
        'sender_type': 'user',
        'sender_id': ticket.user_id,
        'sender_name': ticket.user.full_name if ticket.user else 'Customer',
        'sender_email': ticket.user.email if ticket.user else '',
        'message': ticket.description,
        'attachment_path': ticket.attachment_path,
        'has_attachment': bool(ticket.attachment_path),
        'created_at': ticket.created_at.isoformat(),
        'is_initial': True
    }]
    for msg in ticket.messages:
        conversation.append(msg.to_dict())

    return jsonify({
        'ticket': ticket.to_dict(include_user=current_user.is_admin_user),
        'conversation': conversation
    }), 200


@app.route('/api/support/tickets/<int:ticket_id>/reply', methods=['POST'])
@login_required
@csrf.exempt
def user_reply_support_ticket(ticket_id):
    """Allow ticket owner to post a follow-up reply in their ticket conversation."""
    ticket = db.session.get(SupportTicket, ticket_id)
    if not ticket:
        return jsonify({'error': 'Support ticket not found'}), 404
    if ticket.user_id != current_user.id and not current_user.is_admin_user:
        return jsonify({'error': 'Unauthorized to reply to this ticket', 'code': 'FORBIDDEN'}), 403

    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'Message cannot be empty'}), 400

    reply = TicketMessage(
        ticket_id=ticket.id,
        sender_type='user',
        sender_id=current_user.id,
        sender_name=current_user.full_name,
        sender_email=current_user.email,
        message=message
    )
    if ticket.status == 'Resolved':
        ticket.status = 'In Progress'
    ticket.updated_at = datetime.utcnow()
    db.session.add(reply)
    db.session.commit()

    return jsonify({
        'message': 'Reply sent successfully',
        'reply': reply.to_dict(),
        'ticket': ticket.to_dict(include_user=current_user.is_admin_user)
    }), 201


@app.route('/api/admin/support/users', methods=['GET'])
@login_required
@admin_required
def admin_list_support_users():
    """List users with support activity summary (Admin only)."""
    search = request.args.get('search', '').strip()
    query = User.query
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            db.or_(
                User.email.ilike(search_pattern),
                User.full_name.ilike(search_pattern)
            )
        )

    users = query.order_by(User.full_name.asc()).all()
    user_list = []
    for u in users:
        ticket_count = len(u.support_tickets)
        open_count = sum(1 for t in u.support_tickets if t.status == 'Open')
        in_progress_count = sum(1 for t in u.support_tickets if t.status == 'In Progress')
        resolved_count = sum(1 for t in u.support_tickets if t.status in ('Resolved', 'Closed'))
        last_ticket = max(u.support_tickets, key=lambda t: t.created_at).created_at.isoformat() if u.support_tickets else None

        user_list.append({
            'id': u.id,
            'full_name': u.full_name,
            'email': u.email,
            'created_at': u.created_at.isoformat(),
            'is_verified': u.is_verified,
            'is_admin': u.is_admin,
            'ticket_count': ticket_count,
            'open_ticket_count': open_count,
            'in_progress_ticket_count': in_progress_count,
            'resolved_ticket_count': resolved_count,
            'last_ticket_at': last_ticket
        })

    # Sort users with tickets first, then newest ticket
    user_list.sort(key=lambda x: (x['ticket_count'] > 0, x['last_ticket_at'] or ''), reverse=True)
    return jsonify({'users': user_list, 'total': len(user_list)}), 200


@app.route('/api/admin/support/users/<int:user_id>/history', methods=['GET'])
@login_required
@admin_required
def admin_user_support_history(user_id):
    """Fetch complete support history, ticket list, and metrics for a specific user (Admin only)."""
    target_user = db.session.get(User, user_id)
    if not target_user:
        return jsonify({'error': 'User not found'}), 404

    tickets = SupportTicket.query.filter_by(user_id=user_id).order_by(SupportTicket.created_at.desc()).all()
    total_tickets = len(tickets)
    open_tickets = sum(1 for t in tickets if t.status == 'Open')
    in_progress_tickets = sum(1 for t in tickets if t.status == 'In Progress')
    resolved_tickets = sum(1 for t in tickets if t.status in ('Resolved', 'Closed'))

    ticket_details = []
    for t in tickets:
        td = t.to_dict(include_user=False)
        td['messages_count'] = len(t.messages)
        ticket_details.append(td)

    return jsonify({
        'user': {
            'id': target_user.id,
            'full_name': target_user.full_name,
            'email': target_user.email,
            'created_at': target_user.created_at.isoformat(),
            'is_verified': target_user.is_verified,
            'is_admin': target_user.is_admin,
        },
        'stats': {
            'total_tickets': total_tickets,
            'open_tickets': open_tickets,
            'in_progress_tickets': in_progress_tickets,
            'resolved_tickets': resolved_tickets
        },
        'tickets': ticket_details
    }), 200


# ── Quick Questions & FAQ Endpoints ──────────────────────────────

@app.route('/api/quick-questions', methods=['GET'])
@login_required
def get_quick_questions():
    """Retrieve all active quick questions ordered by display order."""
    qqs = QuickQuestion.query.filter_by(is_active=True).order_by(QuickQuestion.display_order.asc(), QuickQuestion.id.asc()).all()
    return jsonify({
        'quick_questions': [q.to_dict() for q in qqs],
        'total': len(qqs)
    }), 200


@app.route('/api/faq', methods=['GET'])
@login_required
def get_faqs():
    """Fetch published FAQs with optional category filtering and keyword search."""
    category = request.args.get('category', '').strip()
    q = request.args.get('q', '').strip()

    query = FAQ.query.filter_by(is_published=True)

    if category and category != 'All':
        query = query.filter(FAQ.category == category)

    if q:
        search_pattern = f"%{q}%"
        query = query.filter(
            db.or_(
                FAQ.question.ilike(search_pattern),
                FAQ.answer.ilike(search_pattern)
            )
        )

    faqs = query.order_by(FAQ.category.asc(), FAQ.id.asc()).all()
    return jsonify({
        'faqs': [f.to_dict() for f in faqs],
        'total': len(faqs)
    }), 200


# ── Admin FAQ Endpoints ──────────────────────────────────────────

@app.route('/api/admin/faq', methods=['GET'])
@login_required
@admin_required
def admin_list_faqs():
    """List all FAQs for administrative management (Admin only)."""
    category = request.args.get('category', '').strip()
    q = request.args.get('q', '').strip()

    query = FAQ.query
    if category and category != 'All':
        query = query.filter(FAQ.category == category)
    if q:
        search_pattern = f"%{q}%"
        query = query.filter(
            db.or_(
                FAQ.question.ilike(search_pattern),
                FAQ.answer.ilike(search_pattern)
            )
        )

    faqs = query.order_by(FAQ.category.asc(), FAQ.id.asc()).all()
    return jsonify({
        'faqs': [f.to_dict() for f in faqs],
        'total': len(faqs)
    }), 200


@app.route('/api/admin/faq', methods=['POST'])
@login_required
@admin_required
@csrf.exempt
def admin_create_faq():
    """Create a new FAQ record (Admin only)."""
    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip()
    answer = (data.get('answer') or '').strip()
    category = (data.get('category') or '').strip()
    is_published = data.get('is_published', True)

    if not question or len(question) < 3:
        return jsonify({'error': 'Question must be at least 3 characters', 'code': 'VALIDATION_ERROR'}), 400
    if not answer or len(answer) < 5:
        return jsonify({'error': 'Answer must be at least 5 characters', 'code': 'VALIDATION_ERROR'}), 400
    if not category:
        return jsonify({'error': 'Category is required', 'code': 'VALIDATION_ERROR'}), 400

    faq = FAQ(
        question=question,
        answer=answer,
        category=category,
        is_published=bool(is_published)
    )
    db.session.add(faq)
    db.session.commit()

    return jsonify({
        'message': 'FAQ created successfully',
        'faq': faq.to_dict()
    }), 201


@app.route('/api/admin/faq/<int:faq_id>', methods=['PATCH', 'PUT'])
@login_required
@admin_required
@csrf.exempt
def admin_update_faq(faq_id):
    """Update an existing FAQ record (Admin only)."""
    faq = db.session.get(FAQ, faq_id)
    if not faq:
        return jsonify({'error': 'FAQ not found', 'code': 'NOT_FOUND'}), 404

    data = request.get_json(silent=True) or {}
    if 'question' in data:
        q = data['question'].strip()
        if len(q) < 3:
            return jsonify({'error': 'Question must be at least 3 characters', 'code': 'VALIDATION_ERROR'}), 400
        faq.question = q
    if 'answer' in data:
        a = data['answer'].strip()
        if len(a) < 5:
            return jsonify({'error': 'Answer must be at least 5 characters', 'code': 'VALIDATION_ERROR'}), 400
        faq.answer = a
    if 'category' in data:
        cat = data['category'].strip()
        if not cat:
            return jsonify({'error': 'Category cannot be empty', 'code': 'VALIDATION_ERROR'}), 400
        faq.category = cat
    if 'is_published' in data:
        faq.is_published = bool(data['is_published'])

    faq.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'message': 'FAQ updated successfully',
        'faq': faq.to_dict()
    }), 200


@app.route('/api/admin/faq/<int:faq_id>', methods=['DELETE'])
@login_required
@admin_required
@csrf.exempt
def admin_delete_faq(faq_id):
    """Delete an FAQ record (Admin only)."""
    faq = db.session.get(FAQ, faq_id)
    if not faq:
        return jsonify({'error': 'FAQ not found', 'code': 'NOT_FOUND'}), 404

    db.session.delete(faq)
    db.session.commit()
    return jsonify({'message': 'FAQ deleted successfully'}), 200


@app.route('/api/admin/faq/<int:faq_id>/toggle-publish', methods=['POST'])
@login_required
@admin_required
@csrf.exempt
def admin_toggle_faq_published(faq_id):
    """Toggle an FAQ between published and draft status (Admin only)."""
    faq = db.session.get(FAQ, faq_id)
    if not faq:
        return jsonify({'error': 'FAQ not found', 'code': 'NOT_FOUND'}), 404

    faq.is_published = not faq.is_published
    faq.updated_at = datetime.utcnow()
    db.session.commit()

    status_str = "published" if faq.is_published else "deactivated (draft)"
    return jsonify({
        'message': f'FAQ is now {status_str}',
        'faq': faq.to_dict()
    }), 200


# ── Admin Quick Questions Endpoints ──────────────────────────────

@app.route('/api/admin/quick-questions', methods=['GET'])
@login_required
@admin_required
def admin_list_quick_questions():
    """List all Quick Questions for administrative management (Admin only)."""
    qqs = QuickQuestion.query.order_by(QuickQuestion.display_order.asc(), QuickQuestion.id.asc()).all()
    return jsonify({
        'quick_questions': [q.to_dict() for q in qqs],
        'total': len(qqs)
    }), 200


@app.route('/api/admin/quick-questions', methods=['POST'])
@login_required
@admin_required
@csrf.exempt
def admin_create_quick_question():
    """Create a new Quick Question (Admin only)."""
    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip()
    answer = (data.get('answer') or '').strip()
    display_order = data.get('display_order')
    is_active = data.get('is_active', True)

    if not question or len(question) < 3:
        return jsonify({'error': 'Question must be at least 3 characters', 'code': 'VALIDATION_ERROR'}), 400
    if not answer or len(answer) < 5:
        return jsonify({'error': 'Answer must be at least 5 characters', 'code': 'VALIDATION_ERROR'}), 400

    if display_order is None:
        max_order = db.session.query(db.func.max(QuickQuestion.display_order)).scalar() or 0
        display_order = max_order + 1

    qq = QuickQuestion(
        question=question,
        answer=answer,
        display_order=int(display_order),
        is_active=bool(is_active)
    )
    db.session.add(qq)
    db.session.commit()

    return jsonify({
        'message': 'Quick Question created successfully',
        'quick_question': qq.to_dict()
    }), 201


@app.route('/api/admin/quick-questions/<int:qq_id>', methods=['PATCH', 'PUT'])
@login_required
@admin_required
@csrf.exempt
def admin_update_quick_question(qq_id):
    """Update a Quick Question (Admin only)."""
    qq = db.session.get(QuickQuestion, qq_id)
    if not qq:
        return jsonify({'error': 'Quick Question not found', 'code': 'NOT_FOUND'}), 404

    data = request.get_json(silent=True) or {}
    if 'question' in data:
        q = data['question'].strip()
        if len(q) < 3:
            return jsonify({'error': 'Question must be at least 3 characters', 'code': 'VALIDATION_ERROR'}), 400
        qq.question = q
    if 'answer' in data:
        a = data['answer'].strip()
        if len(a) < 5:
            return jsonify({'error': 'Answer must be at least 5 characters', 'code': 'VALIDATION_ERROR'}), 400
        qq.answer = a
    if 'display_order' in data:
        qq.display_order = int(data['display_order'])
    if 'is_active' in data:
        qq.is_active = bool(data['is_active'])

    qq.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'message': 'Quick Question updated successfully',
        'quick_question': qq.to_dict()
    }), 200


@app.route('/api/admin/quick-questions/<int:qq_id>', methods=['DELETE'])
@login_required
@admin_required
@csrf.exempt
def admin_delete_quick_question(qq_id):
    """Delete a Quick Question (Admin only)."""
    qq = db.session.get(QuickQuestion, qq_id)
    if not qq:
        return jsonify({'error': 'Quick Question not found', 'code': 'NOT_FOUND'}), 404

    db.session.delete(qq)
    db.session.commit()
    return jsonify({'message': 'Quick Question deleted successfully'}), 200


@app.route('/api/admin/quick-questions/reorder', methods=['POST'])
@login_required
@admin_required
@csrf.exempt
def admin_reorder_quick_questions():
    """Reorder Quick Questions by receiving an ordered list of IDs (Admin only)."""
    data = request.get_json(silent=True) or {}
    order_ids = data.get('order', [])

    if not isinstance(order_ids, list):
        return jsonify({'error': 'order must be a list of IDs', 'code': 'VALIDATION_ERROR'}), 400

    for idx, item_id in enumerate(order_ids, start=1):
        qq = db.session.get(QuickQuestion, item_id)
        if qq:
            qq.display_order = idx

    db.session.commit()
    return jsonify({'message': 'Quick Questions reordered successfully'}), 200






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


def record_report_history(user_id, report_name, report_type, start_date, end_date, format_name):
    """Save report metadata to report_history table, avoiding immediate duplicate rows."""
    try:
        recent_cutoff = datetime.utcnow() - timedelta(seconds=30)
        existing = ReportHistory.query.filter(
            ReportHistory.user_id == user_id,
            ReportHistory.report_type == report_type,
            ReportHistory.start_date == start_date,
            ReportHistory.end_date == end_date,
            ReportHistory.format == format_name,
            ReportHistory.created_at >= recent_cutoff
        ).first()

        if not existing:
            entry = ReportHistory(
                user_id=user_id,
                report_name=report_name,
                report_type=report_type,
                start_date=start_date,
                end_date=end_date,
                format=format_name,
                created_at=datetime.utcnow()
            )
            db.session.add(entry)
            db.session.commit()
            return entry
        return existing
    except Exception as e:
        db.session.rollback()
        print(f"Error saving report history: {e}")
        return None


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


# ── Unified Historical Reports Download ────────────────────────────
def generate_custom_report_pdf(user, period_label, start_date, end_date, expenses):
    """Generate a multi-section PDF report with KPI summaries, category breakdown and transaction list."""
    paid_total = sum(e.amount for e in expenses if (e.status or 'paid') == 'paid')
    planned_total = sum(e.amount for e in expenses if (e.status or 'paid') == 'planned')
    total_expenses = paid_total + planned_total

    user_budget = float(user.monthly_budget) if getattr(user, 'monthly_budget', None) is not None else 1000.0
    days = max(1, (end_date - start_date).days + 1)
    if (end_date - start_date).days >= 360 and (end_date - start_date).days <= 366:
        effective_budget = user_budget * 12
    elif (end_date - start_date).days >= 27 and (end_date - start_date).days <= 31 and start_date.day == 1:
        effective_budget = user_budget
    else:
        effective_budget = round((user_budget / 30.0) * days, 2)
    savings = effective_budget - paid_total

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    elements = []

    # Title & Subtitle
    title_style = styles['Title']
    title_style.textColor = colors.HexColor('#7C3AED')
    elements.append(Paragraph(f"ExpenseFlow Report: {period_label}", title_style))
    elements.append(Paragraph(f"<b>Account Holder:</b> {user.full_name} ({user.email}) &nbsp;|&nbsp; <b>Generated:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", styles['Normal']))
    elements.append(Paragraph(" ", styles['Normal']))

    # Summary KPI Table
    summary_data = [
        ['Total Paid Expenses', 'Planned Commitments', 'Allocated Budget', 'Net Variance / Savings'],
        [f"${paid_total:,.2f}", f"${planned_total:,.2f}", f"${effective_budget:,.2f}", f"${savings:,.2f}"]
    ]
    summary_table = Table(summary_data, colWidths=[1.85*inch, 1.85*inch, 1.85*inch, 1.85*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F1F5F9')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#475569')),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 9),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,1), (-1,1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,1), (-1,1), 12),
        ('TEXTCOLOR', (0,1), (0,1), colors.HexColor('#EF4444')),
        ('TEXTCOLOR', (1,1), (1,1), colors.HexColor('#F59E0B')),
        ('TEXTCOLOR', (2,1), (2,1), colors.HexColor('#3B82F6')),
        ('TEXTCOLOR', (3,1), (3,1), colors.HexColor('#10B981') if savings >= 0 else colors.HexColor('#EF4444')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(summary_table)
    elements.append(Paragraph(" ", styles['Normal']))

    # Category Breakdown Table
    cat_breakdown = {}
    for e in expenses:
        cat_breakdown[e.category] = cat_breakdown.get(e.category, 0.0) + e.amount
    sorted_cats = sorted(cat_breakdown.items(), key=lambda x: x[1], reverse=True)

    cat_heading = Paragraph("<b>Category Breakdown</b>", styles['Heading3'])
    elements.append(cat_heading)
    cat_data = [['Category', 'Amount', '% of Total']]
    for cat_name, cat_amt in sorted_cats:
        pct = (cat_amt / total_expenses * 100) if total_expenses > 0 else 0
        cat_data.append([cat_name, f"${cat_amt:,.2f}", f"{pct:.1f}%"])
    cat_table = Table(cat_data, colWidths=[3.4*inch, 2.0*inch, 2.0*inch])
    cat_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#E2E8F0')),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    elements.append(cat_table)
    elements.append(Paragraph(" ", styles['Normal']))

    # Individual Transactions Table
    tx_heading = Paragraph("<b>Transaction Details</b>", styles['Heading3'])
    elements.append(tx_heading)
    tx_data = [['Date', 'Category', 'Description', 'Status', 'Amount']]
    for e in expenses:
        st = (e.status or 'paid').capitalize()
        desc = (e.description or '')[:35] + '...' if len(e.description or '') > 35 else (e.description or '')
        tx_data.append([
            e.date.strftime('%Y-%m-%d'),
            e.category,
            desc,
            st,
            f"${e.amount:,.2f}"
        ])
    tx_table = Table(tx_data, colWidths=[1.1*inch, 1.4*inch, 2.8*inch, 1.0*inch, 1.1*inch])
    tx_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F8FAFC')),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('ALIGN', (-1,0), (-1,-1), 'RIGHT'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    elements.append(tx_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer


def generate_custom_report_csv(user, period_label, start_date, end_date, expenses):
    """Generate a structured CSV report containing summary metrics, category totals, and transactions."""
    paid_total = sum(e.amount for e in expenses if (e.status or 'paid') == 'paid')
    planned_total = sum(e.amount for e in expenses if (e.status or 'paid') == 'planned')
    total_expenses = paid_total + planned_total

    user_budget = float(user.monthly_budget) if getattr(user, 'monthly_budget', None) is not None else 1000.0
    days = max(1, (end_date - start_date).days + 1)
    if (end_date - start_date).days >= 360 and (end_date - start_date).days <= 366:
        effective_budget = user_budget * 12
    elif (end_date - start_date).days >= 27 and (end_date - start_date).days <= 31 and start_date.day == 1:
        effective_budget = user_budget
    else:
        effective_budget = round((user_budget / 30.0) * days, 2)
    savings = effective_budget - paid_total

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(['ExpenseFlow Expense Report', period_label])
    writer.writerow(['Account Holder', f'{user.full_name} ({user.email})'])
    writer.writerow(['Date Range', f'{start_date.isoformat()} to {end_date.isoformat()}'])
    writer.writerow(['Generated At (UTC)', datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow([])

    writer.writerow(['--- FINANCIAL SUMMARY ---'])
    writer.writerow(['Total Paid Expenses', f'{paid_total:.2f}'])
    writer.writerow(['Planned Commitments', f'{planned_total:.2f}'])
    writer.writerow(['Total Spending (Paid + Planned)', f'{total_expenses:.2f}'])
    writer.writerow(['Allocated Budget', f'{effective_budget:.2f}'])
    writer.writerow(['Net Savings / Budget Variance', f'{savings:.2f}'])
    writer.writerow([])

    cat_breakdown = {}
    for e in expenses:
        cat_breakdown[e.category] = cat_breakdown.get(e.category, 0.0) + e.amount
    sorted_cats = sorted(cat_breakdown.items(), key=lambda x: x[1], reverse=True)

    writer.writerow(['--- CATEGORY BREAKDOWN ---'])
    writer.writerow(['Category', 'Total Amount', 'Percentage'])
    for cat, amt in sorted_cats:
        pct = (amt / total_expenses * 100) if total_expenses > 0 else 0
        writer.writerow([cat, f'{amt:.2f}', f'{pct:.1f}%'])
    writer.writerow([])

    writer.writerow(['--- TRANSACTION DETAILS ---'])
    writer.writerow(['ID', 'Date', 'Category', 'Description', 'Payment Method / Status', 'Amount'])
    for e in expenses:
        writer.writerow([e.id, e.date.isoformat(), e.category, e.description, (e.status or 'paid').capitalize(), f'{e.amount:.2f}'])

    csv_content = output.getvalue()
    output.close()
    return csv_content


def generate_custom_report_xlsx(user, period_label, start_date, end_date, expenses):
    """Generate a styled Excel (XLSX) workbook with summary KPIs, category breakdown, and formatted transactions."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    paid_total = sum(e.amount for e in expenses if (e.status or 'paid') == 'paid')
    planned_total = sum(e.amount for e in expenses if (e.status or 'paid') == 'planned')
    total_expenses = paid_total + planned_total

    user_budget = float(user.monthly_budget) if getattr(user, 'monthly_budget', None) is not None else 1000.0
    days = max(1, (end_date - start_date).days + 1)
    if (end_date - start_date).days >= 360 and (end_date - start_date).days <= 366:
        effective_budget = user_budget * 12
    elif (end_date - start_date).days >= 27 and (end_date - start_date).days <= 31 and start_date.day == 1:
        effective_budget = user_budget
    else:
        effective_budget = round((user_budget / 30.0) * days, 2)
    savings = effective_budget - paid_total

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Expense Report"
    ws.views.sheetView[0].showGridLines = True

    title_font = Font(name="Segoe UI", size=16, bold=True, color="7C3AED")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    section_font = Font(name="Segoe UI", size=12, bold=True, color="1E293B")
    bold_font = Font(name="Segoe UI", size=10, bold=True)
    normal_font = Font(name="Segoe UI", size=10)

    header_fill = PatternFill(start_color="7C3AED", end_color="7C3AED", fill_type="solid")
    sub_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    # Title Banner
    ws["A1"] = f"ExpenseFlow - {period_label}"
    ws["A1"].font = title_font

    ws["A2"] = f"Account: {user.full_name} ({user.email}) | Range: {start_date.isoformat()} to {end_date.isoformat()} | Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    ws["A2"].font = normal_font

    # Financial Summary
    ws["A4"] = "Financial Summary"
    ws["A4"].font = section_font
    summary_headers = ["Total Paid Expenses", "Planned Commitments", "Allocated Budget", "Budget Variance (Savings)"]
    summary_values = [paid_total, planned_total, effective_budget, savings]

    for col_idx, (h, v) in enumerate(zip(summary_headers, summary_values), 1):
        cell_h = ws.cell(row=5, column=col_idx, value=h)
        cell_h.font = header_font
        cell_h.fill = header_fill
        cell_h.alignment = Alignment(horizontal="center")
        cell_h.border = thin_border

        cell_v = ws.cell(row=6, column=col_idx, value=v)
        cell_v.font = bold_font
        cell_v.fill = sub_fill
        cell_v.number_format = '"$"#,##0.00'
        cell_v.alignment = Alignment(horizontal="right")
        cell_v.border = thin_border

    # Category Breakdown
    ws["A8"] = "Category Breakdown"
    ws["A8"].font = section_font

    cat_breakdown = {}
    for e in expenses:
        cat_breakdown[e.category] = cat_breakdown.get(e.category, 0.0) + e.amount
    sorted_cats = sorted(cat_breakdown.items(), key=lambda x: x[1], reverse=True)

    cat_headers = ["Category", "Amount", "Percentage"]
    for col_idx, h in enumerate(cat_headers, 1):
        cell = ws.cell(row=9, column=col_idx, value=h)
        cell.font = bold_font
        cell.fill = sub_fill
        cell.border = thin_border

    cur_row = 10
    for cat_name, cat_amt in sorted_cats:
        pct = (cat_amt / total_expenses) if total_expenses > 0 else 0
        c1 = ws.cell(row=cur_row, column=1, value=cat_name)
        c2 = ws.cell(row=cur_row, column=2, value=cat_amt)
        c3 = ws.cell(row=cur_row, column=3, value=pct)
        c1.font = normal_font
        c2.font = normal_font
        c3.font = normal_font
        c2.number_format = '"$"#,##0.00'
        c3.number_format = '0.0%'
        c1.border = thin_border
        c2.border = thin_border
        c3.border = thin_border
        cur_row += 1

    # Transactions Table
    cur_row += 1
    ws.cell(row=cur_row, column=1, value="Transaction Details").font = section_font
    cur_row += 1

    tx_headers = ["Date", "Category", "Description", "Status / Payment Method", "Amount"]
    for col_idx, h in enumerate(tx_headers, 1):
        cell = ws.cell(row=cur_row, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin_border
        if h == "Amount":
            cell.alignment = Alignment(horizontal="right")

    cur_row += 1
    for e in expenses:
        c1 = ws.cell(row=cur_row, column=1, value=e.date.isoformat())
        c2 = ws.cell(row=cur_row, column=2, value=e.category)
        c3 = ws.cell(row=cur_row, column=3, value=e.description)
        c4 = ws.cell(row=cur_row, column=4, value=(e.status or 'paid').capitalize())
        c5 = ws.cell(row=cur_row, column=5, value=e.amount)

        for c in (c1, c2, c3, c4, c5):
            c.font = normal_font
            c.border = thin_border
        c5.number_format = '"$"#,##0.00'
        c5.alignment = Alignment(horizontal="right")
        cur_row += 1

    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            val_str = str(cell.value or '')
            if len(val_str) > max_len and len(val_str) < 50:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 14)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


@app.route('/api/reports/download', methods=['GET'])
@login_required
def download_custom_report():
    """Unified endpoint to download historical expense reports in PDF, CSV, or Excel XLSX format."""
    period_type = (request.args.get('period_type') or 'monthly').strip().lower()
    export_format = (request.args.get('format') or 'pdf').strip().lower()

    if export_format not in ['pdf', 'csv', 'xlsx']:
        return jsonify({'error': f'Unsupported export format: {export_format}'}), 400

    now = datetime.now()

    if period_type == 'monthly':
        try:
            year = int(request.args.get('year', now.year))
            month = int(request.args.get('month', now.month))
            if not (1 <= month <= 12):
                return jsonify({'error': 'Month must be between 1 and 12'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid year or month value'}), 400

        start_date = datetime(year, month, 1).date()
        if month == 12:
            end_date = datetime(year + 1, 1, 1).date() - timedelta(days=1)
        else:
            end_date = datetime(year, month + 1, 1).date() - timedelta(days=1)
        period_label = start_date.strftime('%B %Y')
        filename = f"ExpenseFlow_{start_date.strftime('%B_%Y')}.{export_format}"

    elif period_type == 'yearly':
        try:
            year = int(request.args.get('year', now.year))
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid year value'}), 400
        start_date = datetime(year, 1, 1).date()
        end_date = datetime(year, 12, 31).date()
        period_label = f"Year {year}"
        filename = f"ExpenseFlow_Year_{year}.{export_format}"

    elif period_type == 'custom':
        start_str = (request.args.get('start_date') or '').strip()
        end_str = (request.args.get('end_date') or '').strip()
        if not start_str or not end_str:
            return jsonify({'error': 'Start date and End date are required for custom range'}), 400
        try:
            start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format. Expected YYYY-MM-DD'}), 400

        if start_date > end_date:
            return jsonify({'error': 'Start date cannot be after End date'}), 400

        period_label = f"{start_date.strftime('%b %d, %Y')} - {end_date.strftime('%b %d, %Y')}"
        filename = f"ExpenseFlow_Custom_Report.{export_format}"
    else:
        return jsonify({'error': f'Unsupported report period type: {period_type}'}), 400

    # Query strictly isolated to current_user
    expenses = Expense.query.filter(
        Expense.user_id == current_user.id,
        Expense.date >= start_date,
        Expense.date <= end_date
    ).order_by(Expense.date.asc()).all()

    if not expenses:
        return jsonify({
            'error': f'No transactions found for the selected period ({period_label})',
            'count': 0
        }), 404

    try:
        # Record report history upon successful generation
        record_report_history(current_user.id, period_label, period_type, start_date, end_date, export_format)

        if export_format == 'pdf':
            pdf_buf = generate_custom_report_pdf(current_user, period_label, start_date, end_date, expenses)
            return Response(
                pdf_buf.getvalue(),
                mimetype='application/pdf',
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}"',
                    'Access-Control-Expose-Headers': 'Content-Disposition'
                }
            )
        elif export_format == 'csv':
            csv_data = generate_custom_report_csv(current_user, period_label, start_date, end_date, expenses)
            return Response(
                csv_data,
                mimetype='text/csv',
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}"',
                    'Access-Control-Expose-Headers': 'Content-Disposition'
                }
            )
        elif export_format == 'xlsx':
            xlsx_buf = generate_custom_report_xlsx(current_user, period_label, start_date, end_date, expenses)
            return Response(
                xlsx_buf.getvalue(),
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}"',
                    'Access-Control-Expose-Headers': 'Content-Disposition'
                }
            )
    except Exception as e:
        print(f"Error generating report: {e}")
        return jsonify({'error': f'Failed to generate report: {str(e)}'}), 500


@app.route('/api/reports/history', methods=['GET'])
@login_required
def get_report_history():
    """Retrieve history of downloaded reports for the authenticated user."""
    try:
        history = ReportHistory.query.filter_by(user_id=current_user.id).order_by(ReportHistory.created_at.desc()).all()
        return jsonify({
            'history': [h.to_dict() for h in history],
            'total': len(history)
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/reports/download-again/<int:report_id>', methods=['GET'])
@login_required
def download_report_again(report_id):
    """Regenerate and download a report from saved history metadata."""
    history_entry = db.session.get(ReportHistory, report_id)
    if not history_entry or history_entry.user_id != current_user.id:
        return jsonify({'error': 'Report record not found or unauthorized'}), 404

    start_date = history_entry.start_date
    end_date = history_entry.end_date
    export_format = history_entry.format.lower()
    period_label = history_entry.report_name
    period_type = history_entry.report_type.lower()

    if period_type == 'monthly':
        filename = f"ExpenseFlow_{start_date.strftime('%B_%Y')}.{export_format}"
    elif period_type == 'yearly':
        filename = f"ExpenseFlow_Year_{start_date.year}.{export_format}"
    else:
        filename = f"ExpenseFlow_Custom_Report.{export_format}"

    expenses = Expense.query.filter(
        Expense.user_id == current_user.id,
        Expense.date >= start_date,
        Expense.date <= end_date
    ).order_by(Expense.date.asc()).all()

    if not expenses:
        return jsonify({
            'error': f'No transactions currently found for this report period ({period_label})',
            'count': 0
        }), 404

    try:
        if export_format == 'pdf':
            pdf_buf = generate_custom_report_pdf(current_user, period_label, start_date, end_date, expenses)
            return Response(
                pdf_buf.getvalue(),
                mimetype='application/pdf',
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}"',
                    'Access-Control-Expose-Headers': 'Content-Disposition'
                }
            )
        elif export_format == 'csv':
            csv_data = generate_custom_report_csv(current_user, period_label, start_date, end_date, expenses)
            return Response(
                csv_data,
                mimetype='text/csv',
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}"',
                    'Access-Control-Expose-Headers': 'Content-Disposition'
                }
            )
        elif export_format == 'xlsx':
            xlsx_buf = generate_custom_report_xlsx(current_user, period_label, start_date, end_date, expenses)
            return Response(
                xlsx_buf.getvalue(),
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}"',
                    'Access-Control-Expose-Headers': 'Content-Disposition'
                }
            )
    except Exception as e:
        print(f"Error regenerating report: {e}")
        return jsonify({'error': f'Failed to regenerate report: {str(e)}'}), 500

# ── Email with attachment helper ───────────────────────────────────
def send_email_with_attachment(to, subject, body, attachment_bytes, filename):
    import smtplib, os
    from email.message import EmailMessage
    from email.mime.application import MIMEApplication
    if app.config.get('TESTING'):
        return

    # 1. Primary for Cloud / Render: Brevo REST API over HTTPS (Port 443)
    if os.getenv('BREVO_API_KEY'):
        if send_via_brevo_api(to, subject, None, body, attachment_bytes, filename):
            return

    # 2. Fallback to standard SMTP (for localhost or direct SMTP)
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


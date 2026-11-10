# ExpenseFlow — Smart Multi-User Expense Tracker

ExpenseFlow is a production-ready, full-stack multi-user expense tracking web application built with Python Flask, SQLAlchemy, and a modern glassmorphic responsive UI. It features robust user authentication, data isolation, rate-limited password recovery, rich analytics, CSV/PDF report generation, and automated monthly scheduled reports.

---

## Features

- **Multi-User Authentication & Security:**
  - Secure registration with password hashing (PBKDF2-SHA256).
  - Timed cryptographic token-based email confirmation (`itsdangerous`).
  - Session-based authentication with Flask-Login and `login_required` route protection.
  - Rate limiting powered by `Flask-Limiter` (e.g., maximum 5 password reset requests per minute per IP to prevent abuse).
  - CSRF protection powered by `Flask-WTF`.
  - Secure password reset workflow.

- **Expense Management & Data Isolation:**
  - Full CRUD capabilities (Add, Edit, Delete, View) strictly isolated per authenticated user.
  - Categorization (Food, Transport, Utilities, Entertainment, Health, Shopping, Others).
  - Search by description and filter by date range or category.
  - Dynamic sorting by date (asc/desc) or amount (asc/desc).

- **Analytics & Visual Dashboard:**
  - Summary KPI cards: Total Spent, Current Month Expenses, Daily Average, and Top Spending Category.
  - Interactive spending trends and category breakdown powered by Chart.js.

- **Reporting & Exporting:**
  - Instant CSV export of complete user transaction history (`/api/export`).
  - Formatted monthly PDF expense report generation using ReportLab (`/api/report/<year>/<month>`).
  - Automated monthly scheduler (`Flask-APScheduler`) generating and emailing monthly PDF expense reports to verified users on the 1st of every month at 08:00 UTC.

---

## Tech Stack

- **Backend:** Python 3.10+, Flask 3.0
- **Database & ORM:** SQLite / SQLAlchemy 3.1, Flask-Migrate (Alembic)
- **Auth & Security:** Flask-Login, Flask-Limiter, Flask-WTF, itsdangerous, Werkzeug
- **Reporting:** ReportLab (PDF), Python standard `csv`
- **Scheduling:** Flask-APScheduler
- **Production Server:** Gunicorn (specified in `Procfile`)
- **Frontend:** HTML5, CSS3 (Glassmorphism design), Vanilla JavaScript, Chart.js, Font Awesome
- **Testing:** Pytest

---

## Directory Structure

```
Expense-tracker/
├── app.py                  # Main Flask application entry point and routes
├── database.py             # Database initialization and SQLAlchemy instance
├── models.py               # User and Expense database models
├── migrations/             # Alembic database migrations
├── static/
│   ├── css/style.css       # Glassmorphism styling and responsive design
│   └── js/app.js           # Single-page client-side logic and chart rendering
├── templates/
│   ├── index.html          # Main application dashboard
│   ├── login.html          # Login view
│   ├── register.html       # User registration view
│   └── reset_password.html # Password reset view
├── tests/
│   ├── conftest.py         # Pytest fixtures and test client setup
│   └── test_app.py         # Unit & integration tests
├── .env.example            # Template for environment variables
├── Procfile                # Gunicorn process definition for deployment
├── pytest.ini              # Pytest configuration
├── requirements.txt        # Python package dependencies
└── README.md               # Project documentation
```

---

## Installation & Setup

### 1. Clone the Repository & Create Virtual Environment
```bash
git clone <repository_url>
cd Expense-tracker
python -m venv venv

# On Windows:
venv\Scripts\activate

# On macOS/Linux:
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env` and configure your settings:
```bash
cp .env.example .env
```
Key variables:
- `SECRET_KEY`: Random secret string for signing cookies and tokens.
- `DATABASE_URL` or `SQLALCHEMY_DATABASE_URI`:
  - **SQLite:** `sqlite:///expenses.db`
  - **Local PostgreSQL:** `postgresql://postgres:yourpassword@localhost:5432/expenseflow`
  - **Cloud PostgreSQL (Neon, Supabase, Render, Railway, AWS RDS):** `postgresql://user:password@host/dbname?sslmode=require`
- `RATELIMIT_ENABLED`: Set to `True` to enforce rate limits.
- `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`: SMTP credentials for verification and report emails.

### 4. Database Setup & PostgreSQL Initialization
1. Create your database in PostgreSQL (e.g. via `psql` or pgAdmin):
   ```sql
   CREATE DATABASE expenseflow;
   ```
2. Put the connection string in your `.env` file:
   ```env
   DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/expenseflow
   ```
3. Run the application or initialize the tables:
   ```bash
   python app.py
   ```
   *(The app automatically executes `db.create_all()` via `init_db(app)` on startup, generating all tables (`users`, `expenses`) with proper primary and foreign keys).*

---

## Running the Application

### Development Server:
```bash
python app.py
```
Open your browser and navigate to `http://127.0.0.1:5000`.

### Production Server (Render / Gunicorn):
On Render, create a new **Web Service** pointing to your repository:
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn -c gunicorn.conf.py app:app` (or via included `Procfile`)
- **Environment Variables:** Set `DATABASE_URL` (from Render PostgreSQL), `SECRET_KEY`, and `FLASK_ENV=production`.

---

## Running Tests

Execute the automated test suite with `pytest`:
```bash
pytest -v
```
The test suite verifies:
1. **`test_login_requires_verification`**: Ensures unverified users receive `403` and verified users receive `200`.
2. **`test_expense_crud_isolation`**: Verifies strict multi-tenant data isolation—users cannot see, edit, or delete expenses belonging to other users.
3. **`test_password_reset_rate_limit`**: Enforces Flask-Limiter throttling—the 6th reset request within one minute returns HTTP `429 Too Many Requests`.
4. **`test_csv_and_pdf_exports`**: Validates CSV format and ReportLab binary PDF generation.

---

## API Endpoints Reference

### Authentication & Account
| Method | Endpoint | Description |
|---|---|---|
| `GET` / `POST` | `/register` | Render register page / register user |
| `GET` | `/confirm/<token>` | Verify user email address with signed token |
| `GET` / `POST` | `/login` | Render login page / authenticate user |
| `GET` | `/logout` | Log out authenticated user |
| `POST` | `/reset-password-request` | Request password reset email (Rate limited: 5/min) |
| `GET` / `POST` | `/reset-password/<token>` | Render reset view / submit new password |

### Expenses (Requires Login)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/expenses` | List current user's expenses with filters (`category`, `start_date`, `end_date`, `search`, `sort`) |
| `POST` | `/api/expenses` | Create a new expense for the logged-in user |
| `PUT` | `/api/expenses/<id>` | Update an expense (isolated to owner) |
| `DELETE` | `/api/expenses/<id>` | Delete an expense (isolated to owner) |

### Analytics & Reports (Requires Login)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/stats` | Aggregate metrics (totals, daily average, category breakdown, monthly trends) |
| `GET` | `/api/export` | Export expenses in CSV format |
| `GET` | `/api/report/<year>/<month>` | Generate and download monthly PDF report |

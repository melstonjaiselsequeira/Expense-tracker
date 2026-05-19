# ExpenseFlow — Smart Expense Tracker

A full-featured, visually stunning expense tracker web application built with Python Flask, SQLite, and a modern dark glassmorphism UI.

## Features

- **Interactive Dashboard** — Overview cards (total spent, monthly, daily avg, top category), spending trend line chart, category doughnut chart, and recent expenses list.
- **Manage Expenses** — Full CRUD (Add, Edit, Delete) capabilities via modal forms with category chip selection.
- **Filters & Search** — Filter expenses by date range, category, and search by description. Sort by newest, oldest, highest, or lowest amount.
- **CSV Export** — Download your complete expense history as a CSV file.
- **Responsive Design** — Works seamlessly on desktop, tablet, and mobile screens.

## Technology Stack

- **Backend:** Python 3, Flask
- **Database:** SQLite (via SQLAlchemy ORM)
- **Frontend:** HTML5, CSS3 (Custom Glassmorphism Design), Vanilla JavaScript
- **Charts:** Chart.js
- **Icons:** Font Awesome

## Installation & Setup

1. **Clone the repository** (or navigate to the project directory).
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Run the application:**
   ```bash
   python app.py
   ```
4. **Open in browser:**
   Navigate to `http://localhost:5000`

*Note: The app will automatically create a local SQLite database (`expenses.db`) and seed it with 15 sample expenses on first run.*

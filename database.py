from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text

db = SQLAlchemy()

def seed_faq_and_quick_questions():
    """Seed initial quick questions and FAQs if they do not exist."""
    try:
        from models import FAQ, QuickQuestion

        # 1. Seed Quick Questions
        if QuickQuestion.query.count() == 0:
            initial_qqs = [
                (
                    "How do I add a new expense?",
                    "Navigate to the Dashboard or Expenses tab, click '+ Add Expense' (or press 'N' on your keyboard), fill in the amount, category, date, and description, and click 'Save Expense'.",
                    1
                ),
                (
                    "How do I edit or delete an expense?",
                    "In the Expenses table or Recent Transactions list, find the expense and click the edit (pencil) icon to update details, or the delete (trash) icon to remove it permanently.",
                    2
                ),
                (
                    "How do I create a monthly budget?",
                    "Go to your Dashboard, locate the Monthly Budget card, and click the edit/set budget icon to input your monthly target. Your progress bar and spending indicator update automatically.",
                    3
                ),
                (
                    "How do I track my spending?",
                    "Use the visual spending breakdown charts and monthly trend analytics on the Dashboard, or filter expenses by category and date on the Expenses page.",
                    4
                ),
                (
                    "How do I download expense reports?",
                    "Click the 'Export CSV' or 'Export PDF' buttons in the sidebar navigation or Expenses table header to instantly download your formatted records.",
                    5
                ),
                (
                    "How do I reset my password?",
                    "Log out and click 'Forgot password?' on the login screen, or request a secure password reset link sent directly to your registered email address.",
                    6
                ),
            ]
            for q, a, order in initial_qqs:
                qq = QuickQuestion(question=q, answer=a, display_order=order, is_active=True)
                db.session.add(qq)
            db.session.commit()

        # 2. Seed FAQs
        if FAQ.query.count() == 0:
            initial_faqs = [
                # Account Management
                (
                    "How do I update my profile or change my account details?",
                    "Your account name and email are maintained through your authenticated profile. If you need to update your registered email address or account name, you can submit an Account Management support ticket below.",
                    "Account Management",
                    True
                ),
                (
                    "Can I access ExpenseFlow across multiple devices?",
                    "Yes! ExpenseFlow is a fully responsive web application. You can log in securely from your desktop, laptop, tablet, or smartphone browser with real-time data synchronization.",
                    "Account Management",
                    True
                ),
                (
                    "How do I log out of my session safely?",
                    "Click the Logout button located at the bottom of the sidebar navigation. This securely invalidates your active session token.",
                    "Account Management",
                    True
                ),

                # Expense Management
                (
                    "What categories are available for categorizing expenses?",
                    "ExpenseFlow includes Food, Transport, Shopping, Bills, Entertainment, Health, Education, and Other. Each category has its own distinct color badge and analytical breakdown on your Dashboard.",
                    "Expense Management",
                    True
                ),
                (
                    "Can I record planned or scheduled expenses before paying?",
                    "Yes! When adding or editing an expense, choose 'Scheduled' under Payment Status. Once you have paid, simply update the status to 'Paid' with one click.",
                    "Expense Management",
                    True
                ),
                (
                    "How can I filter expenses by specific dates or keywords?",
                    "In the Expenses view, use the live search bar to search descriptions and categories, or use the category dropdown and date filters to quickly narrow down your transactions.",
                    "Expense Management",
                    True
                ),

                # Budget Management
                (
                    "Does my monthly spending goal reset automatically each month?",
                    "Yes. The budget tracker automatically calculates spending against the current calendar month. Historical records and charts remain preserved for monthly trend analysis.",
                    "Budget Management",
                    True
                ),
                (
                    "What happens when I exceed my monthly budget ceiling?",
                    "When your spending exceeds 100% of your budget goal, the budget card badge changes to a high-contrast danger alert showing the exact overage amount so you can adjust your spending.",
                    "Budget Management",
                    True
                ),

                # Reports & Analytics
                (
                    "What file formats are supported for exporting reports?",
                    "You can export your expense data as CSV for spreadsheet analysis (Excel, Google Sheets) or download high-resolution PDF summaries with monthly aggregations.",
                    "Reports & Analytics",
                    True
                ),
                (
                    "How are the Monthly Spending Trend charts calculated?",
                    "Trend charts analyze your month-over-month expenses across all categories, displaying your net spending flow and helping you identify seasonal spending fluctuations.",
                    "Reports & Analytics",
                    True
                ),

                # Security & Privacy
                (
                    "How is my financial data protected?",
                    "ExpenseFlow uses secure PBKDF2 password hashing, HTTPS encryption in transit, session protection against CSRF, and account-level data isolation. No third parties have access to your personal financial records.",
                    "Security & Privacy",
                    True
                ),
                (
                    "Are my uploaded screenshot attachments safe?",
                    "All support ticket attachments are strictly validated for approved image formats (PNG, JPG, WEBP), size-checked, sanitized to prevent path traversal, and served only to authorized account owners or admins.",
                    "Security & Privacy",
                    True
                ),
            ]
            for q, a, cat, pub in initial_faqs:
                faq = FAQ(question=q, answer=a, category=cat, is_published=pub)
                db.session.add(faq)
            db.session.commit()
    except Exception as e:
        db.session.rollback()


def init_db(app):
    """Initialize the database with the Flask app."""
    db.init_app(app)
    with app.app_context():
        db.create_all()
        try:
            insp = inspect(db.engine)
            if 'users' in insp.get_table_names():
                cols = [c['name'] for c in insp.get_columns('users')]
                if 'monthly_budget' not in cols:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN monthly_budget FLOAT DEFAULT 1000.0"))
                    db.session.commit()
                if 'is_admin' not in cols:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE"))
                    db.session.commit()
            if 'expenses' in insp.get_table_names():
                cols = [c['name'] for c in insp.get_columns('expenses')]
                if 'status' not in cols:
                    db.session.execute(text("ALTER TABLE expenses ADD COLUMN status VARCHAR(20) DEFAULT 'paid'"))
                    db.session.execute(text("UPDATE expenses SET status = 'paid' WHERE status IS NULL"))
                    db.session.commit()
            # Seed FAQ and Quick Questions
            seed_faq_and_quick_questions()
        except Exception:
            db.session.rollback()

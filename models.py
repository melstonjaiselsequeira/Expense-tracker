from database import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


class User(db.Model):
    """User model for authentication and account management.

    Fields:
        id: Primary key.
        full_name: User's display name.
        email: Normalized unique email address.
        password_hash: Secure password hash.
        is_verified: Email verification flag.
        created_at: Timestamp of account creation.
        is_active: Compatibility flag for Flask-Login.
    """
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    monthly_budget = db.Column(db.Float, default=1000.0, nullable=True)
    username = db.Column(db.String(80), unique=True, nullable=True, index=True)
    profile_picture = db.Column(db.String(255), nullable=True)
    email_reports_enabled = db.Column(db.Boolean, default=True, nullable=False)
    has_consented_terms_privacy = db.Column(db.Boolean, default=False, nullable=False)
    consent_timestamp = db.Column(db.DateTime, nullable=True)
    consent_version = db.Column(db.String(32), nullable=True)

    # Relationship to expenses and support tickets
    expenses = db.relationship("Expense", backref="user", lazy=True, cascade="all, delete-orphan")
    support_tickets = db.relationship("SupportTicket", backref="user", lazy=True, cascade="all, delete-orphan")
    consents = db.relationship("UserConsent", backref="user", lazy="dynamic", cascade="all, delete-orphan")

    def set_password(self, password):
        """Hash and store the password using Werkzeug's generate_password_hash (pbkdf2:sha256)."""
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256")

    def check_password(self, password):
        """Verify a password against the stored hash."""
        return check_password_hash(self.password_hash, password)

    # Flask-Login required properties
    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    @property
    def is_admin_user(self):
        import os
        admin_emails = [e.strip().lower() for e in os.getenv('ADMIN_EMAILS', '').split(',') if e.strip()]
        return bool(self.is_admin or (self.email and self.email.lower() in admin_emails))

    @property
    def display_name(self):
        return self.username or self.full_name or 'User'

    @property
    def avatar_url(self):
        if self.profile_picture:
            return f"/static/uploads/profile_pictures/{self.profile_picture}"
        return None

    def to_profile_dict(self):
        return {
            'id': self.id,
            'username': self.username or self.full_name,
            'full_name': self.full_name,
            'email': self.email,
            'profile_picture': self.profile_picture,
            'avatar_url': self.avatar_url,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'is_admin': self.is_admin_user,
            'email_reports_enabled': getattr(self, 'email_reports_enabled', True),
            'has_consented_terms_privacy': getattr(self, 'has_consented_terms_privacy', False),
            'consent_version': getattr(self, 'consent_version', None),
            'consent_timestamp': self.consent_timestamp.isoformat() if getattr(self, 'consent_timestamp', None) else None
        }

    def get_id(self):
        return str(self.id)

    def __repr__(self):
        return f"<User {self.email}>"


class Expense(db.Model):
    """Model representing a single expense entry."""
    __tablename__ = 'expenses'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    status = db.Column(db.String(20), default='paid', nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        """Serialize the expense to a dictionary."""
        return {
            'id': self.id,
            'amount': self.amount,
            'category': self.category,
            'description': self.description,
            'date': self.date.isoformat(),
            'status': self.status or 'paid',
            'created_at': self.created_at.isoformat()
        }

    def __repr__(self):
        return f'<Expense {self.id}: {self.description} - ${self.amount} ({self.status})>'


class SupportTicket(db.Model):
    """Model representing a customer support request/ticket."""
    __tablename__ = 'support_tickets'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ticket_id = db.Column(db.String(30), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True)
    category = db.Column(db.String(50), nullable=False)   # 'General Query', 'Report a Problem', 'Feature Request'
    subject = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    attachment_path = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default='Open', nullable=False) # 'Open', 'In Progress', 'Resolved', 'Closed'
    admin_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Conversation thread messages
    messages = db.relationship("TicketMessage", backref="ticket", lazy=True, cascade="all, delete-orphan", order_by="TicketMessage.created_at.asc()")

    def to_dict(self, include_user=False):
        """Serialize support ticket to dictionary."""
        data = {
            'id': self.id,
            'ticket_id': self.ticket_id,
            'user_id': self.user_id,
            'category': self.category,
            'subject': self.subject,
            'description': self.description,
            'has_attachment': bool(self.attachment_path),
            'attachment_filename': self.attachment_path,
            'status': self.status,
            'admin_notes': self.admin_notes or '',
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'message_count': len(self.messages) if self.messages else 0,
        }
        if include_user:
            if self.user:
                data['user_name'] = self.user.full_name
                data['user_email'] = self.user.email
            else:
                data['user_name'] = 'Guest Contact'
                data['user_email'] = 'Visitor / Public Inquiry'
        return data

    def __repr__(self):
        return f'<SupportTicket {self.ticket_id}: {self.subject} ({self.status})>'


class TicketMessage(db.Model):
    """Model representing a message in a support ticket conversation."""
    __tablename__ = 'ticket_messages'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('support_tickets.id', ondelete='CASCADE'), nullable=False, index=True)
    sender_type = db.Column(db.String(20), nullable=False)  # 'admin' or 'user'
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    sender_name = db.Column(db.String(120), nullable=False)
    sender_email = db.Column(db.String(120), nullable=True)
    message = db.Column(db.Text, nullable=False)
    attachment_path = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    sender = db.relationship('User', foreign_keys=[sender_id], lazy=True)

    def to_dict(self):
        """Serialize message to dictionary."""
        return {
            'id': self.id,
            'ticket_id': self.ticket_id,
            'sender_type': self.sender_type,
            'sender_id': self.sender_id,
            'sender_name': self.sender_name,
            'sender_email': self.sender_email or '',
            'message': self.message,
            'attachment_path': self.attachment_path,
            'has_attachment': bool(self.attachment_path),
            'created_at': self.created_at.isoformat(),
        }

    def __repr__(self):
        return f'<TicketMessage {self.id}: {self.sender_type} ({self.sender_name}) on ticket {self.ticket_id}>'


class FAQ(db.Model):
    """Model representing a Frequently Asked Question."""
    __tablename__ = 'faqs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    question = db.Column(db.String(255), nullable=False)
    answer = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(100), nullable=False, index=True)
    is_published = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        """Serialize FAQ to dictionary."""
        return {
            'id': self.id,
            'question': self.question,
            'answer': self.answer,
            'category': self.category,
            'is_published': self.is_published,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }

    def __repr__(self):
        return f'<FAQ {self.id}: {self.question[:30]} ({self.category})>'


class QuickQuestion(db.Model):
    """Model representing a Quick Question with instant answer."""
    __tablename__ = 'quick_questions'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    question = db.Column(db.String(255), nullable=False)
    answer = db.Column(db.Text, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        """Serialize Quick Question to dictionary."""
        return {
            'id': self.id,
            'question': self.question,
            'answer': self.answer,
            'display_order': self.display_order,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }

    def __repr__(self):
        return f'<QuickQuestion {self.id}: {self.question[:30]} (order={self.display_order})>'


class ReportHistory(db.Model):
    """Model representing historical report downloads metadata."""
    __tablename__ = 'report_history'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    report_name = db.Column(db.String(120), nullable=False)
    report_type = db.Column(db.String(20), nullable=False)  # 'monthly', 'yearly', 'custom'
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    format = db.Column(db.String(10), nullable=False)       # 'pdf', 'csv', 'xlsx'
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationship back to User
    user = db.relationship('User', backref=db.backref('report_histories', lazy=True, cascade='all, delete-orphan'))

    def to_dict(self):
        """Serialize report history metadata to dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'report_name': self.report_name,
            'report_type': self.report_type.capitalize(),
            'start_date': self.start_date.isoformat(),
            'end_date': self.end_date.isoformat(),
            'format': self.format.upper(),
            'created_at': self.created_at.isoformat(),
        }

    def __repr__(self):
        return f'<ReportHistory {self.id}: {self.report_name} ({self.format}) user={self.user_id}>'


class UserConsent(db.Model):
    """Audit log of user consents under DPDP Act, 2023.

    Records consent grants and revocations, policy versions, timestamps, and network context.
    """
    __tablename__ = 'user_consents'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True)
    consent_type = db.Column(db.String(64), nullable=False, index=True)  # 'terms_and_privacy', 'monthly_reports'
    policy_version = db.Column(db.String(32), nullable=False, default='1.0')
    has_consented = db.Column(db.Boolean, default=True, nullable=False)
    ip_address = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(256), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'consent_type': self.consent_type,
            'policy_version': self.policy_version,
            'has_consented': self.has_consented,
            'ip_address': self.ip_address,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }

    def __repr__(self):
        return f'<UserConsent user={self.user_id} type={self.consent_type} consented={self.has_consented}>'







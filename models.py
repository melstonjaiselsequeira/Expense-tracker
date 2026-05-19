from database import db
from datetime import datetime


class Expense(db.Model):
    """Model representing a single expense entry."""
    __tablename__ = 'expenses'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        """Serialize the expense to a dictionary."""
        return {
            'id': self.id,
            'amount': self.amount,
            'category': self.category,
            'description': self.description,
            'date': self.date.isoformat(),
            'created_at': self.created_at.isoformat()
        }

    def __repr__(self):
        return f'<Expense {self.id}: {self.description} - ${self.amount}>'

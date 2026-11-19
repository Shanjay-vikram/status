from datetime import datetime, timezone
from flask_login import UserMixin
from . import db

def utcnow():
    return datetime.now(timezone.utc)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(160), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_code = db.Column(db.String(40), unique=True, nullable=False)
    legal_name = db.Column(db.String(200), nullable=False)
    contact_name = db.Column(db.String(160))
    email = db.Column(db.String(180))
    phone = db.Column(db.String(50))
    address = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_number = db.Column(db.String(40), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    subject = db.Column(db.String(240), nullable=False)
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), default="MEDIUM")
    status = db.Column(db.String(40), default="OPEN")
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    customer = db.relationship("Customer")
    creator = db.relationship("User", foreign_keys=[created_by])
    problems = db.relationship("Problem", backref="ticket", cascade="all, delete-orphan", order_by="Problem.id")
    updates = db.relationship("StageUpdate", backref="ticket", cascade="all, delete-orphan", order_by="StageUpdate.created_at")
    submissions = db.relationship("Submission", backref="ticket", cascade="all, delete-orphan", order_by="Submission.version_number")
    attachments = db.relationship("Attachment", backref="ticket", cascade="all, delete-orphan", order_by="Attachment.created_at")

class Problem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("ticket.id"), nullable=False)
    problem_number = db.Column(db.String(30), nullable=False)
    title = db.Column(db.String(240), nullable=False)
    description = db.Column(db.Text, nullable=False)
    severity = db.Column(db.String(20), default="MEDIUM")
    status = db.Column(db.String(40), default="OPEN")
    assigned_engineer_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    root_cause = db.Column(db.Text)
    solution_summary = db.Column(db.Text)
    engineer = db.relationship("User", foreign_keys=[assigned_engineer_id])
    questions = db.relationship("Question", backref="problem", cascade="all, delete-orphan")

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    problem_id = db.Column(db.Integer, db.ForeignKey("problem.id"), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    conclusion = db.Column(db.Text)
    justifications = db.relationship("Justification", backref="question", cascade="all, delete-orphan")

class Justification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id"), nullable=False)
    justification_text = db.Column(db.Text, nullable=False)
    evidence_reference = db.Column(db.Text)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    author = db.relationship("User")

class StageUpdate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("ticket.id"), nullable=False)
    problem_id = db.Column(db.Integer, db.ForeignKey("problem.id"))
    stage = db.Column(db.String(50), nullable=False)
    update_text = db.Column(db.Text, nullable=False)
    next_action = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    author = db.relationship("User")

class Attachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("ticket.id"), nullable=False)
    problem_id = db.Column(db.Integer, db.ForeignKey("problem.id"))
    file_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    uploader = db.relationship("User")

class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("ticket.id"), nullable=False)
    version_number = db.Column(db.Integer, nullable=False)
    summary = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), default="PENDING")
    submitted_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    submitted_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    decision_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    decision_at = db.Column(db.DateTime(timezone=True))
    decision_comments = db.Column(db.Text)
    submitter = db.relationship("User", foreign_keys=[submitted_by])
    reviewer = db.relationship("User", foreign_keys=[decision_by])

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    action = db.Column(db.String(80), nullable=False)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    actor = db.relationship("User")

import csv, io, os, uuid
from functools import wraps
from pathlib import Path
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_from_directory, abort, make_response
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from . import db
from .models import User, Customer, Ticket, Problem, StageUpdate, Attachment, Submission, AuditLog, Question, Justification

main = Blueprint("main", __name__)
ALLOWED = {"pdf", "png", "jpg", "jpeg", "txt", "csv", "xlsx", "docx"}

def roles_required(*roles):
    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return deco

def audit(action, details=""):
    db.session.add(AuditLog(actor_id=current_user.id, action=action, details=details))

def visible_ticket_query():
    q = Ticket.query
    if current_user.role == "CUSTOMER":
        q = q.filter_by(customer_id=current_user.customer_id)
    elif current_user.role == "ENGINEER":
        q = q.join(Problem).filter(Problem.assigned_engineer_id == current_user.id).distinct()
    return q

def get_ticket_or_404(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    if current_user.role == "CUSTOMER" and ticket.customer_id != current_user.customer_id:
        abort(403)
    if current_user.role == "ENGINEER" and not any(p.assigned_engineer_id == current_user.id for p in ticket.problems):
        abort(403)
    return ticket

@main.route("/")
@login_required
def dashboard():
    tickets = visible_ticket_query().order_by(Ticket.created_at.desc()).limit(10).all()
    all_q = visible_ticket_query()
    counts = {
        "total": all_q.count(),
        "open": all_q.filter(Ticket.status.in_(["OPEN", "IN_PROGRESS"])).count(),
        "pending": all_q.filter_by(status="PENDING_APPROVAL").count(),
        "resolved": all_q.filter_by(status="APPROVED").count(),
    }
    return render_template("dashboard.html", tickets=tickets, counts=counts)

@main.route("/customers")
@roles_required("ADMIN", "SUPPORT")
def customers():
    return render_template("customers.html", customers=Customer.query.order_by(Customer.legal_name).all())

@main.route("/customers/new", methods=["GET", "POST"])
@roles_required("ADMIN", "SUPPORT")
def customer_new():
    if request.method == "POST":
        code = request.form.get("customer_code", "").strip().upper()
        name = request.form.get("legal_name", "").strip()
        if not code or not name:
            flash("Customer code and company name are required.", "danger")
        elif Customer.query.filter_by(customer_code=code).first():
            flash("Customer code already exists.", "danger")
        else:
            customer = Customer(customer_code=code, legal_name=name,
                contact_name=request.form.get("contact_name", "").strip(),
                email=request.form.get("email", "").strip(), phone=request.form.get("phone", "").strip(),
                address=request.form.get("address", "").strip())
            db.session.add(customer); db.session.flush(); audit("CUSTOMER_CREATED", f"{code} - {name}"); db.session.commit()
            flash("Customer created.", "success"); return redirect(url_for("main.customers"))
    return render_template("customer_form.html")

@main.route("/users")
@roles_required("ADMIN")
def users():
    return render_template("users.html", users=User.query.order_by(User.created_at.desc()).all())

@main.route("/users/new", methods=["GET", "POST"])
@roles_required("ADMIN")
def user_new():
    customers = Customer.query.order_by(Customer.legal_name).all()
    if request.method == "POST":
        username=request.form.get("username", "").strip(); email=request.form.get("email", "").strip().lower()
        password=request.form.get("password", ""); role=request.form.get("role", "")
        if role not in {"ADMIN", "SUPPORT", "ENGINEER", "MANAGEMENT", "CUSTOMER"}:
            flash("Select a valid role.", "danger")
        elif len(password) < 10:
            flash("Password must be at least 10 characters.", "danger")
        elif User.query.filter((User.username==username)|(User.email==email)).first():
            flash("Username or email already exists.", "danger")
        else:
            cid=request.form.get("customer_id") or None
            if role == "CUSTOMER" and not cid:
                flash("Choose a customer for a Customer login.", "danger")
            else:
                u=User(username=username,email=email,password_hash=generate_password_hash(password),
                    full_name=request.form.get("full_name", "").strip(),role=role,customer_id=int(cid) if cid else None)
                db.session.add(u); audit("USER_CREATED", f"{username} ({role})"); db.session.commit()
                flash("User account created.", "success"); return redirect(url_for("main.users"))
    return render_template("user_form.html", customers=customers)

@main.route("/tickets")
@login_required
def tickets():
    return render_template("tickets.html", tickets=visible_ticket_query().order_by(Ticket.created_at.desc()).all())

@main.route("/tickets/new", methods=["GET", "POST"])
@roles_required("ADMIN", "SUPPORT")
def ticket_new():
    customers=Customer.query.order_by(Customer.legal_name).all()
    engineers=User.query.filter_by(role="ENGINEER", is_active=True).all()
    if request.method == "POST":
        customer_id=request.form.get("customer_id", type=int)
        subject=request.form.get("subject", "").strip(); desc=request.form.get("description", "").strip()
        titles=request.form.getlist("problem_title[]"); descriptions=request.form.getlist("problem_description[]")
        if not customer_id or not subject or not desc or not any(t.strip() for t in titles):
            flash("Customer, ticket subject, description and at least one problem are required.", "danger")
        else:
            ticket=Ticket(ticket_number=f"HC-{__import__('datetime').datetime.now():%Y%m%d}-{uuid.uuid4().hex[:5].upper()}",
                customer_id=customer_id,subject=subject,description=desc,priority=request.form.get("priority","MEDIUM"),created_by=current_user.id)
            db.session.add(ticket); db.session.flush()
            for i,(title,pdesc) in enumerate(zip(titles, descriptions),1):
                if title.strip():
                    engineer_id=request.form.getlist("engineer_id[]")
                    pid=int(engineer_id[i-1]) if i-1 < len(engineer_id) and engineer_id[i-1] else None
                    ticket.problems.append(Problem(problem_number=f"P-{i:02d}",title=title.strip(),description=pdesc.strip(),
                        severity=request.form.getlist("severity[]")[i-1] if i-1 < len(request.form.getlist("severity[]")) else "MEDIUM",
                        assigned_engineer_id=pid))
            audit("TICKET_CREATED", ticket.ticket_number); db.session.commit()
            flash(f"Ticket {ticket.ticket_number} created.", "success"); return redirect(url_for("main.ticket_detail", ticket_id=ticket.id))
    return render_template("ticket_form.html", customers=customers, engineers=engineers)

@main.route("/tickets/<int:ticket_id>")
@login_required
def ticket_detail(ticket_id):
    ticket=get_ticket_or_404(ticket_id)
    chart_data=[]
    for attachment in ticket.attachments:
        if attachment.file_name.lower().endswith(".csv"):
            try:
                with open(os.path.join(current_app.config["UPLOAD_FOLDER"], attachment.stored_name), "r", encoding="utf-8-sig", newline="") as f:
                    rows=list(csv.DictReader(f))[:100]
                if rows:
                    headers=list(rows[0].keys())
                    numeric=[]
                    for h in headers:
                        vals=[]
                        for row in rows:
                            try: vals.append(float(row.get(h, "")))
                            except (ValueError, TypeError): pass
                        if len(vals)>=2: numeric.append((h, vals))
                    if numeric:
                        chart_data.append({"name": attachment.file_name, "labels": [str(i+1) for i in range(len(numeric[0][1]))], "series": [{"label":h,"data":vals} for h,vals in numeric[:3]]})
            except (OSError, UnicodeError, csv.Error):
                pass
    return render_template("ticket_detail.html", ticket=ticket, chart_data=chart_data)

@main.route("/tickets/<int:ticket_id>/update", methods=["POST"])
@roles_required("ADMIN", "SUPPORT", "ENGINEER")
def ticket_update(ticket_id):
    ticket=get_ticket_or_404(ticket_id)
    stage=request.form.get("stage", "").strip(); text=request.form.get("update_text", "").strip()
    if not stage or not text:
        flash("Stage and update details are required.", "danger")
    else:
        update=StageUpdate(ticket_id=ticket.id,stage=stage,update_text=text,next_action=request.form.get("next_action", "").strip(),created_by=current_user.id)
        ticket.status="IN_PROGRESS"; db.session.add(update); audit("STAGE_UPDATED", f"{ticket.ticket_number}: {stage}"); db.session.commit()
        flash("Stage update saved.", "success")
    return redirect(url_for("main.ticket_detail", ticket_id=ticket.id))

@main.route("/tickets/<int:ticket_id>/upload", methods=["POST"])
@roles_required("ADMIN", "SUPPORT", "ENGINEER")
def upload(ticket_id):
    ticket=get_ticket_or_404(ticket_id); file=request.files.get("file")
    if not file or not file.filename:
        flash("Choose a file to upload.", "danger")
    else:
        original=secure_filename(file.filename); ext=original.rsplit(".",1)[-1].lower() if "." in original else ""
        if ext not in ALLOWED:
            flash("File type not allowed. Allowed: PDF, images, TXT, CSV, XLSX, DOCX.", "danger")
        else:
            stored=f"{uuid.uuid4().hex}_{original}"
            file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], stored))
            db.session.add(Attachment(ticket_id=ticket.id,file_name=original,stored_name=stored,uploaded_by=current_user.id))
            audit("FILE_UPLOADED", f"{ticket.ticket_number}: {original}"); db.session.commit()
            flash("File uploaded.", "success")
    return redirect(url_for("main.ticket_detail", ticket_id=ticket.id))

@main.route("/attachments/<int:attachment_id>")
@login_required
def attachment_download(attachment_id):
    attachment=Attachment.query.get_or_404(attachment_id); ticket=get_ticket_or_404(attachment.ticket_id)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], attachment.stored_name, as_attachment=True, download_name=attachment.file_name)

@main.route("/problems/<int:problem_id>/analysis", methods=["POST"])
@roles_required("ADMIN", "SUPPORT", "ENGINEER")
def problem_analysis(problem_id):
    problem=Problem.query.get_or_404(problem_id); get_ticket_or_404(problem.ticket_id)
    problem.root_cause=request.form.get("root_cause", "").strip()
    problem.solution_summary=request.form.get("solution_summary", "").strip()
    problem.status="ANALYSIS" if problem.root_cause else problem.status
    db.session.commit(); flash("Problem analysis saved.", "success")
    return redirect(url_for("main.ticket_detail", ticket_id=problem.ticket_id))

@main.route("/problems/<int:problem_id>/questions", methods=["POST"])
@roles_required("ADMIN", "SUPPORT", "ENGINEER")
def add_question(problem_id):
    problem=Problem.query.get_or_404(problem_id); get_ticket_or_404(problem.ticket_id)
    qtext=request.form.get("question_text", "").strip(); conclusion=request.form.get("conclusion", "").strip()
    if qtext:
        q=Question(problem_id=problem.id,question_text=qtext,conclusion=conclusion); db.session.add(q); db.session.flush()
        justification=request.form.get("justification", "").strip()
        if justification:
            db.session.add(Justification(question_id=q.id,justification_text=justification,evidence_reference=request.form.get("evidence_reference", ""),author_id=current_user.id))
        db.session.commit(); flash("Question and justification saved.", "success")
    return redirect(url_for("main.ticket_detail", ticket_id=problem.ticket_id))

@main.route("/tickets/<int:ticket_id>/submit", methods=["POST"])
@roles_required("ADMIN", "SUPPORT", "ENGINEER")
def submit_ticket(ticket_id):
    ticket=get_ticket_or_404(ticket_id); summary=request.form.get("summary", "").strip()
    if not summary:
        flash("Submission summary is required.", "danger")
    elif not ticket.problems:
        flash("Add at least one problem before submission.", "danger")
    else:
        version=(max([s.version_number for s in ticket.submissions]) if ticket.submissions else 0)+1
        sub=Submission(ticket_id=ticket.id,version_number=version,summary=summary,submitted_by=current_user.id)
        db.session.add(sub); ticket.status="PENDING_APPROVAL"; audit("SUBMITTED_FOR_APPROVAL", ticket.ticket_number); db.session.commit()
        flash("Ticket submitted to Management for approval.", "success")
    return redirect(url_for("main.ticket_detail", ticket_id=ticket.id))

@main.route("/approvals")
@roles_required("ADMIN", "MANAGEMENT")
def approvals():
    pending=Submission.query.filter_by(status="PENDING").order_by(Submission.submitted_at).all()
    return render_template("approvals.html", submissions=pending)

@main.route("/approvals/<int:submission_id>/decision", methods=["POST"])
@roles_required("ADMIN", "MANAGEMENT")
def decision(submission_id):
    sub=Submission.query.get_or_404(submission_id); choice=request.form.get("decision"); comments=request.form.get("comments", "").strip()
    if choice not in {"APPROVED", "RETURNED"} or not comments:
        flash("Choose a decision and enter comments.", "danger")
    else:
        sub.status=choice; sub.decision_by=current_user.id; sub.decision_comments=comments
        sub.decision_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc)
        sub.ticket.status="APPROVED" if choice=="APPROVED" else "IN_PROGRESS"
        audit(f"MANAGEMENT_{choice}", sub.ticket.ticket_number); db.session.commit()
        flash(f"Submission {choice.lower()}.", "success")
    return redirect(url_for("main.approvals"))

@main.route("/tickets/<int:ticket_id>/report")
@login_required
def report(ticket_id):
    ticket=get_ticket_or_404(ticket_id)
    approved=[s for s in ticket.submissions if s.status=="APPROVED"]
    if current_user.role=="CUSTOMER" and not approved:
        abort(403)
    if not approved and current_user.role not in {"ADMIN", "MANAGEMENT", "SUPPORT", "ENGINEER"}:
        abort(403)
    filename=f"{ticket.ticket_number}_report.pdf"; path=os.path.join(current_app.config["REPORT_FOLDER"], filename)
    styles=getSampleStyleSheet(); story=[Paragraph("HardwareCare - Ticket Investigation Report", styles["Title"]),Spacer(1,12)]
    story += [Paragraph(f"Ticket: {ticket.ticket_number}",styles["Heading2"]),Paragraph(f"Customer: {ticket.customer.legal_name}",styles["BodyText"]),Paragraph(f"Subject: {ticket.subject}",styles["BodyText"]),Paragraph(f"Priority: {ticket.priority} | Status: {ticket.status}",styles["BodyText"]),Spacer(1,12),Paragraph("Ticket Description",styles["Heading2"]),Paragraph(ticket.description.replace("&","&amp;"),styles["BodyText"]),Spacer(1,10)]
    for p in ticket.problems:
        story += [Paragraph(f"{p.problem_number}: {p.title}",styles["Heading2"]),Paragraph(p.description.replace("&","&amp;"),styles["BodyText"]),Paragraph(f"Severity: {p.severity} | Status: {p.status}",styles["BodyText"])]
        if p.root_cause: story.append(Paragraph("Root cause: "+p.root_cause.replace("&","&amp;"),styles["BodyText"]))
        if p.solution_summary: story.append(Paragraph("Solution: "+p.solution_summary.replace("&","&amp;"),styles["BodyText"]))
        for q in p.questions:
            story.append(Paragraph("Question: "+q.question_text.replace("&","&amp;"),styles["BodyText"]))
            if q.conclusion: story.append(Paragraph("Conclusion: "+q.conclusion.replace("&","&amp;"),styles["BodyText"]))
            for j in q.justifications: story.append(Paragraph("Justification: "+j.justification_text.replace("&","&amp;"),styles["BodyText"]))
        story.append(Spacer(1,8))
    if ticket.updates:
        story.append(Paragraph("Stage History",styles["Heading2"]))
        data=[["Stage","Update","Date"]]+[[u.stage,u.update_text[:250],u.created_at.strftime("%Y-%m-%d %H:%M")] for u in ticket.updates]
        table=Table(data,repeatRows=1,colWidths=[90,330,90]); table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#173b5e")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.4,colors.grey),("VALIGN",(0,0),(-1,-1),"TOP")])); story.append(table)
    if approved:
        story += [Spacer(1,12),Paragraph("Management Approval",styles["Heading2"]),Paragraph(f"Approved by: {approved[-1].reviewer.full_name if approved[-1].reviewer else 'Management'}",styles["BodyText"]),Paragraph(f"Comments: {(approved[-1].decision_comments or '').replace('&','&amp;')}",styles["BodyText"])]
    SimpleDocTemplate(path,pagesize=A4,rightMargin=40,leftMargin=40,topMargin=40,bottomMargin=40).build(story)
    return send_from_directory(current_app.config["REPORT_FOLDER"],filename,as_attachment=True)

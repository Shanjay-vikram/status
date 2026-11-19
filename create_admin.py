from getpass import getpass
from app import create_app, db
from app.models import User
from werkzeug.security import generate_password_hash

app = create_app()
with app.app_context():
    if User.query.filter_by(username="admin").first():
        print("An admin account with username 'admin' already exists.")
    else:
        full_name = input("Admin full name: ").strip() or "HardwareCare Administrator"
        email = input("Admin email: ").strip().lower()
        password = getpass("Create password (minimum 12 characters): ")
        confirm = getpass("Confirm password: ")
        if len(password) < 12:
            raise SystemExit("Password must be at least 12 characters.")
        if password != confirm:
            raise SystemExit("Passwords do not match.")
        if not email or User.query.filter_by(email=email).first():
            raise SystemExit("A valid, unused email address is required.")
        user = User(username="admin", email=email, password_hash=generate_password_hash(password),
                    full_name=full_name, role="ADMIN", is_active=True)
        db.session.add(user)
        db.session.commit()
        print("Admin created. Sign in with username: admin and the password you entered.")

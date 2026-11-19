import os
from pathlib import Path
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

BASE_DIR = Path(__file__).resolve().parent.parent
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

@login_manager.user_loader
def load_user(user_id):
    from .models import User
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None

def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-only-change-this-secret-key"),
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///hardwarecare.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=int(os.getenv("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)),
        UPLOAD_FOLDER=str(BASE_DIR / "uploads"),
        REPORT_FOLDER=str(BASE_DIR / "reports"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    Path(app.config["UPLOAD_FOLDER"]).mkdir(exist_ok=True)
    Path(app.config["REPORT_FOLDER"]).mkdir(exist_ok=True)
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "warning"
    csrf.init_app(app)

    from .auth import auth
    from .routes import main
    app.register_blueprint(auth, url_prefix="/auth")
    app.register_blueprint(main)

    with app.app_context():
        from . import models
        db.create_all()
    return app

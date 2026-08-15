"""Tests for authentication: hashing, tokens, register/login and the full
forgot-password flow. Uses a temporary SQLite database so no production data
is touched.
"""
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import create_access_token, hash_password, verify_access_token, verify_password
from app.database import Base, get_db
from app.main import app
from app.models import user  # noqa: F401  (register tables)
from app.models.user import PasswordReset, User

_tmp = tempfile.mkdtemp()
_engine = create_engine(f"sqlite:///{Path(_tmp) / 'test.db'}", connect_args={"check_same_thread": False})
_TestingSession = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
Base.metadata.create_all(bind=_engine)


def _override_db():
    db = _TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_db

client = TestClient(app)

EMAIL = "ali.raza@example.com"
PASSWORD = "SuperSecret123!"
NEW_PASSWORD = "NewSecret456!"


# --- security primitives --------------------------------------------------------

def test_password_hash_round_trip():
    stored = hash_password(PASSWORD)
    assert stored != PASSWORD
    assert verify_password(PASSWORD, stored)
    assert not verify_password("wrong", stored)


def test_access_token_round_trip():
    token = create_access_token(7)
    assert verify_access_token(token) == 7
    assert verify_access_token("garbage.token") is None


# --- register / login ------------------------------------------------------------

def test_register_and_login():
    res = client.post("/api/v1/auth/register", json={"email": EMAIL, "name": "Ali Raza", "password": PASSWORD})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["user"]["email"] == EMAIL
    assert body["token"]

    # duplicate registration is rejected
    dup = client.post("/api/v1/auth/register", json={"email": EMAIL, "name": "Ali Raza", "password": PASSWORD})
    assert dup.status_code == 409


def test_login_ok_and_wrong_password():
    ok = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert ok.status_code == 200, ok.text
    assert ok.json()["token"]

    bad = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": "wrong-password"})
    assert bad.status_code == 401

    unknown = client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": PASSWORD})
    assert unknown.status_code == 401


def test_me_with_token():
    login = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}).json()
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {login['token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == EMAIL

    bad = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.token"})
    assert bad.status_code == 401


# --- forgot password -------------------------------------------------------------

def test_forgot_password_flow():
    # Request reset for the registered account (SMTP unconfigured -> dev link)
    res = client.post("/api/v1/auth/forgot-password", json={"email": EMAIL})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["reset_sent"] is True
    assert body["dev_reset_link"], "expected dev reset link when SMTP is unconfigured"

    link = body["dev_reset_link"]
    token = parse_qs(urlparse(link).query)["token"][0]
    assert token

    # Wrong / expired token is rejected
    bad = client.post("/api/v1/auth/reset-password", json={"token": "bogus-token", "new_password": NEW_PASSWORD})
    assert bad.status_code == 400

    # Reset with the real token
    ok = client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})
    assert ok.status_code == 200, ok.text

    # Old password must NOT work; new password must
    old = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert old.status_code == 401
    new = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": NEW_PASSWORD})
    assert new.status_code == 200, new.text

    # Token must not be reusable after success
    reuse = client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "Another123!"})
    assert reuse.status_code == 400


def test_forgot_password_unknown_email_returns_generic():
    res = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})
    assert res.status_code == 200
    body = res.json()
    assert body["dev_reset_link"] is None  # no account -> no dev link


def test_token_is_stored_hashed():
    with _TestingSession() as db:
        records = db.query(PasswordReset).all()
        assert records
        for record in records:
            assert record.token_hash and ":" not in record.token_hash
        users = db.query(User).all()
        assert any(u.email == EMAIL for u in users)
        for u in users:
            assert "pbkdf2_sha256$" in u.password_hash  # never plain text

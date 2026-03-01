import os
from jose import jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
from dotenv import load_dotenv
import sys

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")

if not SECRET_KEY:
    print("⚠️ WARNING: SECRET_KEY not set. Admin authentication will not work.")

if not ADMIN_PASSWORD_HASH:
    print("⚠️ WARNING: ADMIN_PASSWORD_HASH not set. Admin login will not work.")

pwd_context = CryptContext(
    schemes=["bcrypt_sha256"],
    deprecated="auto"
)

def verify_password(password):
    return pwd_context.verify(password, ADMIN_PASSWORD_HASH)

def create_token():
    return jwt.encode(
        {"exp": datetime.utcnow() + timedelta(hours=8)},
        SECRET_KEY,
        algorithm=ALGORITHM
    )
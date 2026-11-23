
import hmac
import hashlib
import secrets

from fastapi import Request, HTTPException, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Advisor




def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)

    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        310000
    ).hex()

    return f"{salt}${hashed}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, expected_hash = stored_hash.split("$", 1)

        actual_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            310000
        ).hex()

        return hmac.compare_digest(actual_hash, expected_hash)

    except Exception:
        return False




def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
):
    session_user = request.session.get("user")

    if not session_user:
        raise HTTPException(
            status_code=401,
            detail="Please log in."
        )

    if session_user.get("role") == "admin":
        return {
            "role": "admin",
            "username": session_user["username"]
        }

    if session_user.get("role") == "advisor":
        advisor = db.query(Advisor).filter(
            Advisor.id == session_user["advisor_id"],
            Advisor.is_active == True
        ).first()

        if not advisor:
            request.session.clear()
            raise HTTPException(
                status_code=401,
                detail="Advisor account is unavailable."
            )

        return {
            "role": "advisor",
            "advisor_id": advisor.id,
            "username": advisor.username,
            "advisor": advisor
        }

    raise HTTPException(
        status_code=401,
        detail="Invalid login session."
    )




def require_admin(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin permission required."
        )

    return user


def require_advisor(user=Depends(get_current_user)):
    if user["role"] != "advisor":
        raise HTTPException(
            status_code=403,
            detail="Advisor login required."
        )

    return user
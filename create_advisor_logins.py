import secrets
from getpass import getpass

from app.database import SessionLocal
from app.models import Advisor
from app.security.auth import hash_password


db = SessionLocal()

try:

    advisors = db.query(Advisor).all()

    for advisor in advisors:

        print("\nAdvisor:", advisor.name)
        print("Username:", advisor.username)

        password = getpass(
            "Enter a new temporary password: "
        )

        advisor.password_hash = hash_password(password)
        advisor.is_active = True

    db.commit()

    print("\nAdvisor login credentials updated.")

finally:
    db.close()

from app.database import SessionLocal
from app.models import Advisor
from app.security.auth import hash_password

db = SessionLocal()

try:
    username = "advisor.demo"
    password = "Coastal@123"

    advisor = db.query(Advisor).filter(
        Advisor.username == username
    ).first()

    if advisor:
        advisor.password_hash = hash_password(password)
        advisor.is_active = True
        print("Existing demo account updated.")

    else:
        advisor = Advisor(
            name="Demo Service Advisor",
            username=username,
            password_hash=hash_password(password),
            phone="919876543210",
            email="advisor.demo@example.com",
            is_active=True
        )

        db.add(advisor)
        print("Demo advisor account created.")

    db.commit()

    print("\n========== DEMO LOGIN ==========")
    print("Username: advisor.demo")
    print("Password: Coastal@123")
    print("================================")

except Exception as e:
    db.rollback()
    print("Error:", e)

finally:
    db.close()

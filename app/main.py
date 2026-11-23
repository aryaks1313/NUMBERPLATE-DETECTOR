import os
import uuid
import hmac
import csv
import io
import time as clock_time

from pathlib import Path
from datetime import datetime, timedelta, timezone, date, time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

import cv2

from fastapi import (FastAPI,Depends,HTTPException,Request,UploadFile,File)

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import case
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.database import Base, engine, get_db, SessionLocal
from app.config import settings
from app.models import Advisor, Booking, Detection, Notification
from app.schemas import BookingCreateRequest

from app.security.auth import (hash_password,verify_password,get_current_user,require_admin,require_advisor)

from app.services.detector import plate_detector
from app.services.ocr import read_plate_result
from app.services.plate_utils import (normalize_plate,is_plausible_indian_plate,format_indian_plate,clean_indian_plate,)
from app.services.booking_service import (
    INDIA_TZ,
    count_advisor_slot_bookings,
    find_available_advisor,
    find_booking,
    get_indian_today,
    slot_index,
)
from app.services.monitor import camera_monitor
from app.services.messaging import queue_advisor_notifications, send_test_email
from app.services.google_oauth import gmail_oauth_status

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Coastal Star Service Gate Intelligence",version="3.0")

STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = BASE_DIR / "uploads"
VIDEO_DIR = UPLOAD_DIR / "videos"
DETECTION_DIR = UPLOAD_DIR / "detections"

STATIC_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)
VIDEO_DIR.mkdir(exist_ok=True)
DETECTION_DIR.mkdir(exist_ok=True)

app.mount("/static",StaticFiles(directory=str(STATIC_DIR)),name="static")

app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)),name="uploads")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv(
        "SESSION_SECRET",
        "replace-this-secret"
    ),
    same_site="lax",
    https_only=False
)



class LoginRequest(BaseModel):
    username: str
    password: str


class AdvisorCreateRequest(BaseModel):
    name: str
    username: str
    password: str
    phone: str
    email: str | None = None


class NotificationUpdateRequest(BaseModel):
    is_read: bool | None = None
    status: str | None = None


class AdvisorContactUpdateRequest(BaseModel):
    phone: str
    email: str | None = None




@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "login.html")


@app.get("/dashboard")
def dashboard_page():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {
        "status": "running",
        "application": "Coastal Star Service Gate"
    }



@app.post("/api/login")
def login(
    data: LoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):

    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "")


    if (
        hmac.compare_digest(data.username, admin_username)
        and admin_password
        and hmac.compare_digest(data.password, admin_password)
    ):

        request.session.clear()

        request.session["user"] = {
            "role": "admin",
            "username": admin_username
        }

        return {
            "message": "Admin login successful",
            "role": "admin",
            "redirect": "/dashboard"
        }


    advisor = db.query(Advisor).filter(
        Advisor.username == data.username,
        Advisor.is_active == True
    ).first()

    if not advisor or not verify_password(
        data.password,
        advisor.password_hash
    ):

        raise HTTPException(
            status_code=401,
            detail="Invalid username or password."
        )

    request.session.clear()

    request.session["user"] = {
        "role": "advisor",
        "advisor_id": advisor.id,
        "username": advisor.username
    }

    return {
        "message": "Advisor login successful",
        "role": "advisor",
        "advisor_name": advisor.name,
        "redirect": "/dashboard"
    }




@app.post("/api/logout")
def logout(request: Request):

    request.session.clear()

    return {
        "message": "Logged out successfully"
    }




@app.get("/api/me")
def current_user(user=Depends(get_current_user)):

    if user["role"] == "admin":

        return {
            "role": "admin",
            "username": user["username"]
        }

    advisor = user["advisor"]

    return {
        "role": "advisor",
        "advisor_id": advisor.id,
        "name": advisor.name,
        "username": advisor.username
    }




@app.post("/api/advisors")
def create_advisor(
    data: AdvisorCreateRequest,
    admin=Depends(require_admin),
    db: Session = Depends(get_db)
):

    existing = db.query(Advisor).filter(
        Advisor.username == data.username
    ).first()

    if existing:

        raise HTTPException(
            status_code=400,
            detail="Username already exists."
        )

    advisor = Advisor(
        name=data.name,
        username=data.username,
        password_hash=hash_password(data.password),
        phone=data.phone,
        email=data.email,
        is_active=True
    )

    db.add(advisor)
    db.commit()
    db.refresh(advisor)

    return {
        "message": "Advisor account created",
        "advisor_id": advisor.id,
        "username": advisor.username
    }


@app.get("/api/advisors")
def list_advisors(
    admin=Depends(require_admin),
    db: Session = Depends(get_db)
):

    advisors = db.query(Advisor).filter(
        Advisor.is_active == True
    ).order_by(Advisor.name).all()

    return [
        {
            "id": a.id,
            "name": a.name,
            "username": a.username,
            "phone": a.phone,
            "email": a.email,
            "is_active": a.is_active
        }
        for a in advisors
    ]


@app.patch("/api/advisors/{advisor_id}/contact")
def update_advisor_contact(
    advisor_id: int,
    data: AdvisorContactUpdateRequest,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    advisor = db.query(Advisor).filter(Advisor.id == advisor_id).first()
    if advisor is None:
        raise HTTPException(status_code=404, detail="Advisor not found.")

    phone = data.phone.strip()
    phone_digits = "".join(character for character in phone if character.isdigit())
    if len(phone_digits) not in (10, 12) or (len(phone_digits) == 12 and not phone_digits.startswith("91")):
        raise HTTPException(
            status_code=400,
            detail="Enter a 10-digit Indian mobile number, optionally with +91.",
        )
    advisor.phone = phone
    advisor.email = (data.email or "").strip() or None
    db.commit()
    return {"message": "Advisor contact details updated.", "advisor_id": advisor.id}


@app.get("/api/admin/notification-status")
def admin_notification_status(
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    active_advisors = db.query(Advisor).filter(Advisor.is_active == True).all()
    email_missing = []
    if not settings.EMAIL_ENABLED:
        email_missing.append("Set EMAIL_ENABLED=true in .env.")
    oauth_status = gmail_oauth_status() if settings.EMAIL_AUTH_METHOD == "oauth" else None
    if oauth_status:
        email_missing.extend(oauth_status["messages"] if not oauth_status["ready"] else [])
    else:
        if not settings.SMTP_USERNAME:
            email_missing.append("Set SMTP_USERNAME to the sending Gmail account.")
        if not settings.SMTP_PASSWORD:
            email_missing.append("Set SMTP_PASSWORD to a Google App Password.")
    if not any(advisor.email for advisor in active_advisors):
        email_missing.append("Save a recipient email on the assigned advisor.")

    whatsapp_missing = []
    if not settings.WHATSAPP_ENABLED:
        whatsapp_missing.append("Set WHATSAPP_ENABLED=true in .env.")
    if not settings.WHATSAPP_ACCESS_TOKEN:
        whatsapp_missing.append("Set the WhatsApp Cloud API access token.")
    if not settings.WHATSAPP_PHONE_NUMBER_ID:
        whatsapp_missing.append("Set the WhatsApp Business phone number ID.")
    if not settings.WHATSAPP_TEMPLATE_NAME:
        whatsapp_missing.append("Set an approved WhatsApp template name.")

    return {
        "email": {
            "ready": not email_missing,
            "enabled": settings.EMAIL_ENABLED,
            "test_ready": bool(
                settings.EMAIL_ENABLED
                and (
                    oauth_status["ready"] if oauth_status else
                    settings.SMTP_USERNAME and settings.SMTP_PASSWORD
                )
            ),
            "messages": email_missing or ["Gmail alerts are configured."],
        },
        "whatsapp": {
            "ready": not whatsapp_missing,
            "enabled": settings.WHATSAPP_ENABLED,
            "messages": whatsapp_missing or ["WhatsApp alerts are configured."],
        },
    }


@app.post("/api/admin/notifications/test-email")
def send_admin_test_email(
    admin=Depends(require_admin),
):
    try:
        recipient = send_test_email()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": f"Test email sent to {recipient}. Check Inbox and Spam."}




@app.get("/api/bookings")
def list_bookings(
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    query = db.query(Booking)

    if user["role"] == "advisor":

        query = query.filter(
            Booking.advisor_id == user["advisor_id"]
        )

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    upcoming = Booking.booking_date >= today
    bookings = query.order_by(
        case((upcoming, 0), else_=1),
        case((upcoming, Booking.booking_date), else_=None).asc(),
        case((Booking.booking_date < today, Booking.booking_date), else_=None).desc(),
        case((upcoming, Booking.booking_time), else_=None).asc(),
        case((Booking.booking_date < today, Booking.booking_time), else_=None).desc(),
    ).all()

    return [
        {
            "id": b.id,
            "customer_name": b.customer_name,
            "phone": b.phone,
            "vehicle_number": b.vehicle_number,
            "vehicle_model": b.vehicle_model,
            "booking_date": str(b.booking_date),
            "booking_time": str(b.booking_time),
            "service_type": b.service_type,
            "status": b.status,
            "advisor": b.advisor.name if b.advisor else None,
            "advisor_id": b.advisor_id
        }
        for b in bookings
    ]


@app.get("/api/bookings/{booking_id}")
def booking_details(
    booking_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    booking = db.query(Booking).filter(
        Booking.id == booking_id
    ).first()

    if not booking:

        raise HTTPException(
            status_code=404,
            detail="Booking not found."
        )

    if (
        user["role"] == "advisor"
        and booking.advisor_id != user["advisor_id"]
    ):

        raise HTTPException(
            status_code=403,
            detail="You cannot view another advisor's booking."
        )

    return {
        "id": booking.id,
        "customer_name": booking.customer_name,
        "phone": booking.phone,
        "vehicle_number": booking.vehicle_number,
        "vehicle_model": booking.vehicle_model,
        "booking_date": str(booking.booking_date),
        "booking_time": str(booking.booking_time),
        "service_type": booking.service_type,
        "status": booking.status,
        "advisor": booking.advisor.name if booking.advisor else None
    }




@app.post("/api/bookings")
def create_booking(
    data: BookingCreateRequest,
    admin=Depends(require_admin),
    db: Session = Depends(get_db)
):

    advisor = db.query(Advisor).filter(
        Advisor.id == data.advisor_id,
        Advisor.is_active == True
    ).first()

    if not advisor:

        raise HTTPException(
            status_code=404,
            detail="Assigned advisor not found."
        )

    vehicle_number = normalize_plate(
        data.vehicle_number
    )

    if not is_plausible_indian_plate(vehicle_number):

        raise HTTPException(
            status_code=400,
            detail="Invalid vehicle registration number."
        )

    used_slots = count_advisor_slot_bookings(
        db, advisor.id, data.booking_date, data.booking_time
    )
    if used_slots >= settings.BOOKINGS_PER_ADVISOR_SLOT:
        raise HTTPException(
            status_code=409,
            detail=(
                f"No booking slot remains for {advisor.name} in this "
                f"{settings.BOOKING_SLOT_MINUTES}-minute time slot. "
                f"The limit is {settings.BOOKINGS_PER_ADVISOR_SLOT} vehicles."
            ),
        )

    booking = Booking(
        customer_name=data.customer_name.strip(),
        phone=data.phone.strip(),
        vehicle_number=vehicle_number,
        vehicle_model=data.vehicle_model.strip(),
        booking_date=data.booking_date,


        booking_time=data.booking_time.strftime("%H:%M"),

        service_type=data.service_type.strip(),
        status=data.status,
        advisor_id=advisor.id
    )

    db.add(booking)
    db.commit()
    db.refresh(booking)

    return {
        "message": "Booking created successfully",
        "booking_id": booking.id,
        "assigned_advisor": advisor.name
    }


def parse_booking_import_date(value: str) -> date:
    value = (value or "").strip()
    for date_format in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    raise ValueError("booking_date must be YYYY-MM-DD or DD-MM-YYYY")


@app.get("/api/bookings-template")
def download_booking_template(admin=Depends(require_admin)):
    return FileResponse(
        BASE_DIR / "sample_bookings.csv",
        media_type="text/csv",
        filename="sample_bookings.csv",
    )


@app.post("/api/bookings/import")
def import_bookings_csv(
    file: UploadFile = File(...),
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    if Path(file.filename or "").suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")

    content = file.file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="CSV file exceeds the 5 MB limit.")

    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must use UTF-8 encoding.") from exc

    reader = csv.DictReader(io.StringIO(decoded))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV has no header row.")
    headers = {header.strip().lower() for header in reader.fieldnames if header}
    required = {
        "customer_name", "phone", "vehicle_number", "vehicle_model",
        "booking_date", "booking_time", "service_type",
    }
    missing = sorted(required - headers)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"CSV is missing required columns: {', '.join(missing)}",
        )
    if "advisor_id" not in headers and "advisor_name" not in headers:
        raise HTTPException(
            status_code=400,
            detail="CSV must include an advisor_id or advisor_name column.",
        )

    advisors = db.query(Advisor).filter(Advisor.is_active == True).all()
    advisors_by_id = {str(advisor.id): advisor for advisor in advisors}
    advisors_by_name = {advisor.name.strip().casefold(): advisor for advisor in advisors}
    new_bookings = []
    seen = set()
    pending_slot_counts = {}
    skipped = 0
    errors = []

    for row_number, raw_row in enumerate(reader, start=2):
        row = {
            (key or "").strip().lower(): (value or "").strip()
            for key, value in raw_row.items()
        }
        if not any(row.values()):
            continue
        try:
            vehicle_number = clean_indian_plate(row.get("vehicle_number", ""))
            if not vehicle_number:
                raise ValueError("invalid Indian vehicle number")
            booking_date = parse_booking_import_date(row["booking_date"])
            booking_time = time.fromisoformat(row["booking_time"])
            advisor = None
            advisor_id = row.get("advisor_id", "")
            if advisor_id:
                advisor = advisors_by_id.get(advisor_id)
            if advisor is None and row.get("advisor_name"):
                advisor = advisors_by_name.get(row["advisor_name"].casefold())
            if advisor is None:
                raise ValueError("advisor_id/advisor_name does not match an active advisor")
            for field in ("customer_name", "phone", "vehicle_model", "service_type"):
                if not row.get(field):
                    raise ValueError(f"{field} is required")

            key = (vehicle_number, booking_date)
            if key in seen or db.query(Booking).filter(
                Booking.vehicle_number == vehicle_number,
                Booking.booking_date == booking_date,
            ).first():
                skipped += 1
                seen.add(key)
                continue
            seen.add(key)
            status = row.get("status") or "Scheduled"
            if status.strip().lower() not in {"cancelled", "canceled", "completed", "closed"}:
                slot_key = (advisor.id, booking_date, slot_index(booking_time))
                used = count_advisor_slot_bookings(
                    db, advisor.id, booking_date, booking_time
                ) + pending_slot_counts.get(slot_key, 0)
                if used >= settings.BOOKINGS_PER_ADVISOR_SLOT:
                    raise ValueError(
                        f"no slot remains for advisor {advisor.name} in this "
                        f"{settings.BOOKING_SLOT_MINUTES}-minute slot "
                        f"(capacity {settings.BOOKINGS_PER_ADVISOR_SLOT})"
                    )
                pending_slot_counts[slot_key] = pending_slot_counts.get(slot_key, 0) + 1
            new_bookings.append(Booking(
                customer_name=row["customer_name"],
                phone=row["phone"],
                vehicle_number=vehicle_number,
                vehicle_model=row["vehicle_model"],
                booking_date=booking_date,
                booking_time=booking_time.strftime("%H:%M"),
                service_type=row["service_type"],
                status=status,
                advisor_id=advisor.id,
            ))
        except (KeyError, ValueError) as exc:
            errors.append(f"Row {row_number}: {exc}")

    if errors:
        raise HTTPException(
            status_code=400,
            detail="CSV import was not applied. " + "; ".join(errors[:10]),
        )
    if not new_bookings and skipped == 0:
        raise HTTPException(status_code=400, detail="CSV contains no booking rows.")

    db.add_all(new_bookings)
    db.commit()
    return {
        "message": f"Imported {len(new_bookings)} booking(s); skipped {skipped} duplicate(s).",
        "imported_count": len(new_bookings),
        "skipped_count": skipped,
    }




@app.get("/api/advisor/dashboard")
def advisor_dashboard(
    user=Depends(require_advisor),
    db: Session = Depends(get_db)
):

    advisor_id = user["advisor_id"]

    bookings = db.query(Booking).filter(
        Booking.advisor_id == advisor_id
    ).count()

    notifications = db.query(Notification).filter(
        Notification.advisor_id == advisor_id
    ).count()

    unread = db.query(Notification).filter(
        Notification.advisor_id == advisor_id,
        Notification.is_read == False
    ).count()

    detections = (
        db.query(Detection)
        .join(Booking, Detection.booking_id == Booking.id)
        .filter(Booking.advisor_id == advisor_id)
        .count()
    )

    recent_notifications = (
        db.query(Notification)
        .filter(Notification.advisor_id == advisor_id)
        .order_by(Notification.id.desc())
        .limit(10)
        .all()
    )

    return {
        "total_bookings": bookings,
        "total_notifications": notifications,
        "unread_notifications": unread,
        "matched_vehicles": detections,
        "notifications": [
            {
                "id": n.id,
                "message": n.message,
                "channel": n.channel,
                "status": n.status,
                "is_read": n.is_read,
                "created_at": (
                    n.created_at.isoformat()
                    if n.created_at else None
                )
            }
            for n in recent_notifications
        ]
    }




@app.get("/api/advisor/notifications")
def advisor_notifications(
    user=Depends(require_advisor),
    db: Session = Depends(get_db)
):

    notifications = (
        db.query(Notification)
        .filter(
            Notification.advisor_id == user["advisor_id"]
        )
        .order_by(Notification.id.desc())
        .all()
    )

    return [
        {
            "id": n.id,
            "message": n.message,
            "channel": n.channel,
            "status": n.status,
            "is_read": n.is_read,
            "created_at": (
                n.created_at.isoformat()
                if n.created_at else None
            )
        }
        for n in notifications
    ]


@app.post("/api/advisor/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    user=Depends(require_advisor),
    db: Session = Depends(get_db)
):

    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.advisor_id == user["advisor_id"]
    ).first()

    if not notification:

        raise HTTPException(
            status_code=404,
            detail="Notification not found."
        )

    notification.is_read = True
    db.commit()

    return {
        "message": "Notification marked as read"
    }


@app.patch("/api/notifications/{notification_id}")
def update_notification(
    notification_id: int,
    data: NotificationUpdateRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = db.query(Notification).filter(
        Notification.id == notification_id
    ).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found.")
    if (
        user["role"] != "admin"
        and notification.advisor_id != user.get("advisor_id")
    ):
        raise HTTPException(status_code=404, detail="Notification not found.")

    if data.status is not None:
        new_status = data.status.strip().lower()
        if new_status not in ("created", "completed"):
            raise HTTPException(
                status_code=400,
                detail="Status must be 'created' or 'completed'.",
            )
        notification.status = new_status
        if new_status == "completed":
            notification.is_read = True
    if data.is_read is not None:
        notification.is_read = data.is_read

    db.commit()
    return {"message": "Notification updated."}



@app.get("/api/admin/dashboard")
def admin_dashboard(
    admin=Depends(require_admin),
    db: Session = Depends(get_db)
):

    return {
        "total_advisors": db.query(Advisor).count(),
        "total_bookings": db.query(Booking).count(),
        "total_detections": db.query(Detection).count(),
        "matched_detections": db.query(Detection).filter(
            Detection.match_status == "matched"
        ).count(),
        "camera": camera_monitor.status()
    }




def _save_detection_and_notification(db, result, advisor, booking_id):
    detection = Detection(
        plate_number=normalize_plate(result.get("plate_number")),
        ocr_text=result.get("ocr_text"),
        confidence=float(result.get("confidence") or 0),
        image_path=result.get("image_path"),
        match_status="matched",
        booking_id=booking_id,
    )
    db.add(detection)
    db.flush()
    message = (
        "New service gate arrival\n"
        f"Vehicle: {result.get('plate_display') or result.get('plate_number')}\n"
        f"Customer: {result.get('customer_name') or 'Walk-in customer'}\n"
        f"Vehicle model: {result.get('vehicle_model') or 'Unknown vehicle'}\n"
        f"Appointment: {result.get('booking_time') or 'Walk-in'}\n"
        f"Service: {result.get('service_type') or 'Walk-in service'}\n"
        f"Service advisor: {advisor.name}\n"
        "Please prepare for customer arrival."
    )
    db.add(Notification(
        detection_id=detection.id,
        advisor_id=advisor.id,
        message=message,
        channel="dashboard",
        status="created",
    ))
    return message


def _assign_walk_in(db, frame, result):
    now = datetime.now(INDIA_TZ)
    booking_date = now.date()
    booking_time = now.strftime("%H:%M")
    advisor = find_available_advisor(db, booking_date, booking_time)
    if advisor is None:
        return None

    booking = Booking(
        customer_name="Walk-in customer",
        phone="Not provided",
        vehicle_number=normalize_plate(result["plate_number"]),
        vehicle_model="Unknown vehicle",
        booking_date=booking_date,
        booking_time=booking_time,
        service_type="Walk-in service",
        status="Walk-in",
        advisor_id=advisor.id,
    )
    db.add(booking)
    db.flush()

    filename = f"{uuid.uuid4().hex}.jpg"
    image_path = DETECTION_DIR / filename
    cv2.imwrite(str(image_path), frame)
    result.update({
        "status": "walk_in_assigned",
        "booking_id": booking.id,
        "customer_name": booking.customer_name,
        "vehicle_model": booking.vehicle_model,
        "advisor": advisor.name,
        "advisor_id": advisor.id,
        "booking_time": booking_time,
        "service_type": booking.service_type,
        "image_path": f"/uploads/detections/{filename}",
        "message": f"No appointment was found. Walk-in assigned to {advisor.name}.",
    })
    message = _save_detection_and_notification(db, result, advisor, booking.id)
    db.commit()
    queue_advisor_notifications(advisor, {**result, "message": message})
    return result


def process_frame(frame, source="live", persist=True):

    db = SessionLocal()

    try:

        detections = plate_detector.detect(frame)

        if not detections:

            return {
                "status": "no_plate",
                "plate_number": None,
                "ocr_text": None,
                "confidence": None,
                "box": None,
                "source": source,
                "message": "No plate visible. Aim the camera at a vehicle plate."
            }

        best = max(
            detections,
            key=lambda item: item["confidence"]
        )

        plate_crop = best["crop"]

        confidence = best["confidence"]

        box = best["box"]

        if confidence < settings.PLATE_MIN_DETECTION_CONFIDENCE:
            return {
                "status": "low_confidence",
                "plate_number": None,
                "plate_display": None,
                "ocr_text": None,
                "confidence": float(confidence),
                "ocr_confidence": 0.0,
                "box": box,
                "source": source,
                "message": "Plate detection confidence is below the minimum.",
            }

        ocr_result = read_plate_result(plate_crop)
        ocr_text = ocr_result["text"]
        ocr_confidence = float(ocr_result["confidence"] or 0)
        plate_number = normalize_plate(ocr_text)

        common_result = {

            "plate_number": plate_number,

            "plate_display": format_indian_plate(plate_number),

            "ocr_text": str(ocr_text or ""),

            "confidence": float(confidence),

            "ocr_confidence": ocr_confidence,

            "box": box,

            "source": source

        }

        if (
            confidence < settings.PLATE_MIN_DETECTION_CONFIDENCE
            or ocr_confidence < settings.OCR_MIN_CONFIDENCE
        ):
            return {
                **common_result,
                "status": "low_confidence",
                "message": (
                    "Plate is hidden because detection or OCR confidence "
                    "is below the configured minimum."
                ),
            }

        if not is_plausible_indian_plate(plate_number):

            return {

                **common_result,

                "status": "invalid_plate",

                "message": "OCR result is not a valid plate format."

            }

        booking = find_booking(
            db,
            plate_number
        )

        corrected_plate = getattr(booking, "matched_plate", None)
        if corrected_plate:
            plate_number = normalize_plate(corrected_plate)
            common_result["plate_number"] = plate_number
            common_result["plate_display"] = format_indian_plate(plate_number)

        if not booking:
            unmatched = {
                **common_result,
                "status": "unmatched",
                "message": "Valid plate detected, but no booking was found.",
            }
            if persist:
                assigned = _assign_walk_in(db, frame, unmatched)
                if assigned:
                    return assigned
                unmatched["message"] = (
                    "Valid plate detected, but all advisor slots are full."
                )
            return unmatched


        if booking.id is None:
            image_path = None
            if persist:
                filename = f"{uuid.uuid4().hex}.jpg"
                cv2.imwrite(str(DETECTION_DIR / filename), frame)
                image_path = f"/uploads/detections/{filename}"
            sample_result = {
                **common_result,
                "status": "matched",
                "booking_id": None,
                "customer_name": booking.customer_name,
                "vehicle_model": booking.vehicle_model,
                "advisor": booking.advisor.name,
                "advisor_id": booking.advisor.id,
                "booking_time": str(booking.booking_time),
                "service_type": booking.service_type,
                "image_path": image_path,
                "message": "Sample CSV booking successfully matched.",
            }
            if persist:
                recent_cutoff = datetime.now(timezone.utc) - timedelta(
                    minutes=settings.DUPLICATE_WINDOW_MINUTES
                )
                recent_csv_match = db.query(Detection).filter(
                    Detection.plate_number == plate_number,
                    Detection.booking_id.is_(None),
                    Detection.created_at >= recent_cutoff,
                ).first()
                if recent_csv_match:
                    sample_result.update({
                        "status": "duplicate",
                        "message": "This vehicle was recently detected.",
                    })
                    return sample_result

                advisor = db.query(Advisor).filter(
                    Advisor.id == booking.advisor_id,
                    Advisor.is_active == True,
                ).first()
                if advisor:
                    message = _save_detection_and_notification(
                        db, sample_result, advisor, None
                    )
                    db.commit()
                    queue_advisor_notifications(
                        advisor, {**sample_result, "message": message}
                    )
            return sample_result

        if not persist:
            return {
                **common_result,
                "status": "matched",
                "booking_id": booking.id,
                "customer_name": booking.customer_name,
                "vehicle_model": booking.vehicle_model,
                "advisor": booking.advisor.name,
                "advisor_id": booking.advisor.id,
                "booking_time": str(booking.booking_time),
                "service_type": booking.service_type,
                "message": "Booking successfully matched.",
            }

        cutoff = datetime.now(
            timezone.utc
        ) - timedelta(minutes=10)

        recent = db.query(Detection).filter(

            Detection.plate_number == plate_number,

            Detection.booking_id == booking.id,

            Detection.created_at >= cutoff

        ).first()

        if recent:

            return {

                **common_result,

                "status": "duplicate",

                "booking_id": booking.id,

                "customer_name": booking.customer_name,

                "vehicle_model": booking.vehicle_model,

                "advisor": booking.advisor.name,

                "message": (
                    "This vehicle was recently detected."
                )

            }

        filename = f"{uuid.uuid4().hex}.jpg"

        image_path = DETECTION_DIR / filename

        cv2.imwrite(
            str(image_path),
            frame
        )

        detection = Detection(

            plate_number=plate_number,

            ocr_text=ocr_text,

            confidence=float(confidence),

            image_path=f"/uploads/detections/{filename}",

            match_status="matched",

            booking_id=booking.id

        )

        db.add(detection)

        db.flush()

        advisor = booking.advisor

        message = (

            "New service gate arrival\n"

            f"Vehicle: {plate_number}\n"

            f"Customer: {booking.customer_name}\n"

            f"Vehicle model: {booking.vehicle_model}\n"

            f"Appointment: {booking.booking_time}\n"

            f"Service: {booking.service_type}\n"

            "Please prepare for customer arrival."

        )

        db.add(

            Notification(

                detection_id=detection.id,

                advisor_id=advisor.id,

                message=message,

                channel="dashboard",

                status="created"

            )

        )

        db.commit()

        queue_advisor_notifications(advisor, {
            **common_result,
            "customer_name": booking.customer_name,
            "vehicle_model": booking.vehicle_model,
            "advisor": advisor.name,
            "booking_time": str(booking.booking_time),
            "service_type": booking.service_type,
            "message": message,
        })

        return {

            **common_result,

            "status": "matched",

            "booking_id": booking.id,

            "customer_name": booking.customer_name,

            "vehicle_model": booking.vehicle_model,

            "advisor": advisor.name,

            "advisor_id": advisor.id,

            "booking_time": str(booking.booking_time),

            "service_type": booking.service_type,

            "image_path": (
                f"/uploads/detections/{filename}"
            ),

            "message": "Booking successfully matched."

        }

    except Exception:

        db.rollback()

        raise

    finally:

        db.close()


def process_camera_frame(frame):

    return process_frame(
        frame,
        source="live"
    )




def persist_video_result(result):
    """Persist one best video frame, notify an advisor, or assign a walk-in."""
    original_status = result.get("status")
    if original_status not in ("matched", "unmatched"):
        return False

    plate_number = normalize_plate(result.get("plate_number"))
    if not plate_number:
        return False

    db = SessionLocal()
    try:
        booking_id = result.get("booking_id")
        booking = None
        if booking_id is not None:
            booking = db.query(Booking).filter(Booking.id == booking_id).first()

        if original_status == "unmatched":
            now = datetime.now(INDIA_TZ)
            booking_time = now.strftime("%H:%M")
            advisor = find_available_advisor(db, now.date(), booking_time)
            if advisor is None:
                return False
            booking = Booking(
                customer_name="Walk-in customer",
                phone="Not provided",
                vehicle_number=plate_number,
                vehicle_model="Unknown vehicle",
                booking_date=now.date(),
                booking_time=booking_time,
                service_type="Walk-in service",
                status="Walk-in",
                advisor_id=advisor.id,
            )
            db.add(booking)
            db.flush()
            booking_id = booking.id
            result.update({
                "status": "walk_in_assigned",
                "booking_id": booking.id,
                "customer_name": booking.customer_name,
                "vehicle_model": booking.vehicle_model,
                "advisor": advisor.name,
                "advisor_id": advisor.id,
                "booking_time": booking_time,
                "service_type": booking.service_type,
                "message": f"No appointment was found. Walk-in assigned to {advisor.name}.",
            })
        else:
            advisor_id = booking.advisor_id if booking else result.get("advisor_id")
            advisor = db.query(Advisor).filter(
                Advisor.id == advisor_id,
                Advisor.is_active == True,
            ).first()
            if advisor is None:
                return False

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        recent = db.query(Detection).filter(
            Detection.plate_number == plate_number,
            Detection.booking_id == (booking.id if booking else None),
            Detection.created_at >= cutoff,
        ).first()
        if recent:
            db.rollback()
            return False

        result["image_path"] = result.get("image_path")
        message = _save_detection_and_notification(
            db, result, advisor, booking.id if booking else None
        )
        db.commit()
        queue_advisor_notifications(advisor, {**result, "message": message})
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.post("/api/video/upload")
def upload_video(
    video: UploadFile = File(...),
    admin=Depends(require_admin)
):

    allowed_extensions = {
        ".mp4",
        ".avi",
        ".mov",
        ".mkv"
    }

    extension = Path(video.filename or "").suffix.lower()

    if extension not in allowed_extensions:

        raise HTTPException(
            status_code=400,
            detail="Unsupported video format."
        )

    video_path = VIDEO_DIR / (
        f"{uuid.uuid4().hex}{extension}"
    )

    # Save uploaded file
    max_size = 200 * 1024 * 1024
    size = 0

    try:

        with video_path.open("wb") as output:

            while True:

                chunk = video.file.read(1024 * 1024)

                if not chunk:
                    break

                size += len(chunk)

                if size > max_size:

                    raise HTTPException(
                        status_code=413,
                        detail="Video exceeds 200 MB limit."
                    )

                output.write(chunk)

    except Exception:

        if video_path.exists():
            video_path.unlink()

        raise

    finally:

        video.file.close()

    cap = cv2.VideoCapture(str(video_path))

    if not cap.isOpened():

        video_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=400,
            detail="Could not open uploaded video."
        )

    fps = cap.get(cv2.CAP_PROP_FPS)

    total_frames = int(
        cap.get(cv2.CAP_PROP_FRAME_COUNT)
    )

    duration = (
        total_frames / fps
        if fps and fps > 0 else 0
    )


    target_fps = max(1.0, settings.VIDEO_SAMPLE_FPS)
    sample_interval = max(
        1,
        round(fps / target_fps) if fps and fps > 0 else 1
    )

    frame_index = 0
    processed_frames = 0
    processing_started = clock_time.perf_counter()

    best_by_plate = {}

    try:

        while True:

            ret, frame = cap.read()

            if not ret:
                break

            if frame_index % sample_interval == 0:

                processed_frames += 1

                try:
                    result = process_frame(
                        frame,
                        source="video",
                        persist=False,
                    )
                except Exception as exc:
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            f"Video analysis failed at frame {frame_index}. "
                            "Check PaddleOCR dependencies/model access and the "
                            f"plate detector. Details: {exc}"
                        ),
                    ) from exc

                plate = normalize_plate(result.get("plate_number"))
                if (
                    not plate
                    or not is_plausible_indian_plate(plate)
                    or result.get("status") not in ("matched", "unmatched")
                ):
                    frame_index += 1
                    continue

                result["plate_number"] = plate
                result["plate_display"] = format_indian_plate(plate)
                result["frame_number"] = frame_index
                result["_frame"] = frame.copy()

                previous = best_by_plate.get(plate)
                if (
                    previous
                    and result.get("status") == "matched"
                    and previous.get("status") != "matched"
                ):
                    previous["status"] = "matched"
                    for field in (
                        "booking_id", "customer_name", "vehicle_model",
                        "advisor", "advisor_id", "booking_time", "service_type",
                    ):
                        previous[field] = result.get(field)
                if previous and previous.get("status") == "matched":
                    if result.get("status") != "matched":
                        for field in (
                            "booking_id", "customer_name", "vehicle_model",
                            "advisor", "advisor_id", "booking_time", "service_type",
                        ):
                            result[field] = previous.get(field)
                        result["status"] = "matched"

                result_quality = min(
                    float(result.get("confidence") or 0),
                    float(result.get("ocr_confidence") or 0),
                )
                previous_quality = min(
                    float(previous.get("confidence") or 0),
                    float(previous.get("ocr_confidence") or 0),
                ) if previous else -1
                if previous is None or result_quality > previous_quality:
                    best_by_plate[plate] = result

            frame_index += 1

    finally:

        cap.release()

    results = list(best_by_plate.values())
    notifications_created = 0
    notifications_skipped = 0
    for result in results:
        filename = f"{uuid.uuid4().hex}.jpg"
        image_path = DETECTION_DIR / filename
        if cv2.imwrite(str(image_path), result.pop("_frame")):
            result["image_path"] = f"/uploads/detections/{filename}"
        result["source"] = "video"
        if result.get("status") in ("matched", "unmatched"):
            if persist_video_result(result):
                notifications_created += 1
            else:
                notifications_skipped += 1

    results.sort(key=lambda result: result.get("frame_number", 0))
    processing_elapsed = max(0.001, clock_time.perf_counter() - processing_started)

    return {
        "message": "Video processing completed",
        "video_filename": video_path.name,
        "duration_seconds": round(duration, 2),
        "total_frames": total_frames,
        "processed_frames": processed_frames,
        "processing_fps": round(processed_frames / processing_elapsed, 2),
        "target_sample_fps": target_fps,
        "recognized_plate_count": len(results),
        "notifications_created": notifications_created,
        "notifications_skipped": notifications_skipped,
        "walk_in_assigned_count": sum(
            1 for result in results
            if result.get("status") == "walk_in_assigned"
        ),
        "sample_interval_seconds": round(
            sample_interval / fps, 3
        ) if fps and fps > 0 else 1,
        "results": results,
        "matched_count": sum(
            1 for r in results
            if r["status"] == "matched"
        ),
        "unmatched_count": sum(
            1 for r in results
            if r["status"] == "unmatched"
        ),
    }




def get_camera_source():

    source = os.getenv("CAMERA_SOURCE", "0")

    if source.isdigit():

        return int(source)

    return source




@app.post("/api/monitor/start")
def start_monitor(
    admin=Depends(require_admin)
):

    source = get_camera_source()

    interval = float(
        os.getenv(
            "CAMERA_PROCESS_INTERVAL",
            "0.0"
        )
    )

    return camera_monitor.start(
        camera_source=source,
        process_frame=process_camera_frame,
        interval=interval
    )


@app.post("/api/monitor/stop")
def stop_monitor(
    admin=Depends(require_admin)
):

    return camera_monitor.stop()


@app.get("/api/monitor/status")
def monitor_status(
    user=Depends(get_current_user)
):

    return camera_monitor.status()




@app.get("/api/admin/notifications")
def admin_notifications(
    admin=Depends(require_admin),
    db: Session = Depends(get_db)
):

    notifications = (
        db.query(Notification)
        .order_by(Notification.id.desc())
        .limit(100)
        .all()
    )

    return [
        {
            "id": n.id,
            "advisor": n.advisor.name if n.advisor else None,
            "message": n.message,
            "channel": n.channel,
            "status": n.status,
            "is_read": n.is_read,
            "created_at": (
                n.created_at.isoformat()
                if n.created_at else None
            )
        }
        for n in notifications
    ]

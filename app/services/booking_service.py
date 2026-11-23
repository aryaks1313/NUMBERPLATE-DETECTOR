import csv
from datetime import date, datetime, time
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import Advisor, Booking
from app.config import settings
from app.services.plate_utils import clean_indian_plate, normalize_plate


INDIA_TZ = ZoneInfo("Asia/Kolkata")
BASE_DIR = Path(__file__).resolve().parents[2]
SAMPLE_BOOKINGS_PATH = BASE_DIR / "sample_bookings.csv"


def get_indian_today():
    return datetime.now(INDIA_TZ).date()


def slot_index(value) -> int:
    """Return the 30-minute (or configured) slot containing a time value."""
    if isinstance(value, str):
        value = time.fromisoformat(value.strip())
    if not isinstance(value, time):
        raise ValueError("A valid booking time is required.")
    slot_minutes = max(1, settings.BOOKING_SLOT_MINUTES)
    return (value.hour * 60 + value.minute) // slot_minutes


def count_advisor_slot_bookings(db: Session, advisor_id: int, booking_date: date, booking_time):
    """Count non-cancelled bookings in the advisor's selected time block."""
    target_slot = slot_index(booking_time)
    bookings = db.query(Booking).filter(
        Booking.advisor_id == advisor_id,
        Booking.booking_date == booking_date,
    ).all()
    active = 0
    database_keys = set()
    for booking in bookings:
        if str(booking.status or "").strip().lower() in {
            "cancelled", "canceled", "completed", "closed"
        }:
            continue
        try:
            if slot_index(booking.booking_time) == target_slot:
                active += 1
                database_keys.add((
                    normalize_plate(booking.vehicle_number),
                    booking.advisor_id,
                    booking.booking_date,
                    slot_index(booking.booking_time),
                ))
        except (TypeError, ValueError):
            continue

    # Count fallback CSV appointments too, unless that same row was imported.
    if SAMPLE_BOOKINGS_PATH.is_file():
        with SAMPLE_BOOKINGS_PATH.open(encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                try:
                    row_date = date.fromisoformat(row["booking_date"])
                    row_time = time.fromisoformat(row["booking_time"])
                    row_advisor = int(row["advisor_id"])
                    row_slot = slot_index(row_time)
                except (KeyError, TypeError, ValueError):
                    continue
                if (
                    row_advisor != advisor_id
                    or row_date != booking_date
                    or row_slot != target_slot
                    or str(row.get("status", "")).strip().lower()
                    in {"cancelled", "canceled", "completed", "closed"}
                ):
                    continue
                csv_key = (
                    normalize_plate(row.get("vehicle_number", "")),
                    row_advisor,
                    row_date,
                    row_slot,
                )
                if csv_key not in database_keys:
                    active += 1
    return active


def find_available_advisor(db: Session, booking_date: date, booking_time):
    """Choose the least-loaded active advisor who still has a slot."""
    advisors = db.query(Advisor).filter(
        Advisor.is_active == True
    ).order_by(Advisor.id).all()
    available = []
    for advisor in advisors:
        used = count_advisor_slot_bookings(
            db, advisor.id, booking_date, booking_time
        )
        if used < settings.BOOKINGS_PER_ADVISOR_SLOT:
            available.append((used, advisor.id, advisor))
    if not available:
        return None
    return min(available, key=lambda entry: (entry[0], entry[1]))[2]


def _one_edit_apart(first: str, second: str) -> bool:
    if abs(len(first) - len(second)) > 1:
        return False
    i = j = edits = 0
    while i < len(first) and j < len(second):
        if first[i] == second[j]:
            i += 1
            j += 1
            continue
        edits += 1
        if edits > 1:
            return False
        if len(first) > len(second):
            i += 1
        elif len(second) > len(first):
            j += 1
        else:
            i += 1
            j += 1
    edits += (len(first) - i) + (len(second) - j)
    return edits == 1


def _csv_bookings(db: Session, today: date):
    bookings = []
    if not SAMPLE_BOOKINGS_PATH.is_file():
        return bookings

    with SAMPLE_BOOKINGS_PATH.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            try:
                if date.fromisoformat(row["booking_date"]) != today:
                    continue
                advisor_id = int(row["advisor_id"])
            except (KeyError, TypeError, ValueError):
                continue

            advisor = db.query(Advisor).filter(Advisor.id == advisor_id).first()
            advisor_name = (
                advisor.name if advisor
                else row.get("advisor_name") or f"Advisor {advisor_id}"
            )
            bookings.append(SimpleNamespace(
                id=None,
                customer_name=row.get("customer_name", ""),
                phone=row.get("phone", ""),
                vehicle_number=row.get("vehicle_number", ""),
                vehicle_model=row.get("vehicle_model", ""),
                booking_date=today,
                booking_time=row.get("booking_time", ""),
                service_type=row.get("service_type", ""),
                status=row.get("status", "confirmed"),
                advisor_id=advisor_id,
                advisor=SimpleNamespace(id=advisor_id, name=advisor_name),
            ))
    return bookings


def find_booking(db: Session, plate_number: str):
    normalized = clean_indian_plate(plate_number) or normalize_plate(plate_number)
    if not normalized:
        return None

    today = get_indian_today()
    bookings = db.query(Booking).filter(Booking.booking_date == today).all()
    for booking in bookings:
        if normalize_plate(booking.vehicle_number) == normalized:
            return booking

    candidates = [
        booking for booking in bookings
        if _one_edit_apart(normalized, normalize_plate(booking.vehicle_number))
    ]
    if len(candidates) == 1:
        candidates[0].matched_plate = candidates[0].vehicle_number
        return candidates[0]
    if candidates:
        return None

    csv_bookings = _csv_bookings(db, today)
    for booking in csv_bookings:
        if normalize_plate(booking.vehicle_number) == normalized:
            return booking

    candidates = [
        booking for booking in csv_bookings
        if _one_edit_apart(normalized, normalize_plate(booking.vehicle_number))
    ]
    if len(candidates) == 1:
        candidates[0].matched_plate = candidates[0].vehicle_number
        return candidates[0]
    return None

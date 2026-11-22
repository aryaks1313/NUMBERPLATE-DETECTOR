import csv
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import Advisor, Booking
from app.services.plate_utils import clean_indian_plate, normalize_plate


INDIA_TZ = ZoneInfo("Asia/Kolkata")
BASE_DIR = Path(__file__).resolve().parents[2]
SAMPLE_BOOKINGS_PATH = BASE_DIR / "sample_bookings.csv"


def get_indian_today():
    return datetime.now(INDIA_TZ).date()


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

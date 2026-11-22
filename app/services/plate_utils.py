import re


_INDIAN_PLATE = re.compile(r"^[A-Z]{2}\d{1,2}[A-Z]{1,3}\d{4}$")
_DIGIT_FIX = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8"})
_LETTER_FIX = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B"})


def normalize_plate(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def clean_indian_plate(value: str) -> str:
    """Normalize common OCR confusions in the numeric/alphabetic plate slots."""
    plate = normalize_plate(value)
    candidates = [plate]
    # Regular Indian plates with a two-digit RTO code and a two-letter series.
    if len(plate) == 10 and plate[:2].isalpha():
        digits = plate[2:4].translate(_DIGIT_FIX)
        series = plate[4:6].translate(_LETTER_FIX)
        number = plate[6:].translate(_DIGIT_FIX)
        candidates.append(plate[:2] + digits + series + number)
    # Also allow the single-digit RTO variation used on older registrations.
    if len(plate) == 9 and plate[:2].isalpha():
        candidate = (
            plate[:2] + plate[2:3].translate(_DIGIT_FIX)
            + plate[3:5].translate(_LETTER_FIX)
            + plate[5:].translate(_DIGIT_FIX)
        )
        candidates.append(candidate)
    return next((candidate for candidate in candidates if _INDIAN_PLATE.fullmatch(candidate)), "")


def format_indian_plate(value: str) -> str:
    plate = clean_indian_plate(value)
    if not plate:
        return normalize_plate(value)
    # E.g. KL 07 AB 1234, while retaining one-digit RTO codes.
    registration = re.fullmatch(r"([A-Z]{2})(\d{1,2})([A-Z]{1,3})(\d{4})", plate)
    return " ".join(registration.groups()) if registration else plate


def is_plausible_indian_plate(value: str) -> bool:
    return bool(clean_indian_plate(value))

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


class Settings:
    DATABASE_URL = os.getenv("DATABASE_URL")

    YOLO_MODEL_PATH = os.getenv(
        "YOLO_MODEL_PATH",
        "best.pt"
    )

    YOLO_CONFIDENCE = float(
        os.getenv("YOLO_CONFIDENCE", "0.35")
    )

    YOLO_IMAGE_SIZE = int(
        os.getenv("YOLO_IMAGE_SIZE", "640")
    )

    ROI_X1 = float(os.getenv("ROI_X1", "0.0"))
    ROI_Y1 = float(os.getenv("ROI_Y1", "0.0"))
    ROI_X2 = float(os.getenv("ROI_X2", "1.0"))
    ROI_Y2 = float(os.getenv("ROI_Y2", "1.0"))

    DUPLICATE_WINDOW_MINUTES = int(
        os.getenv("DUPLICATE_WINDOW_MINUTES", "10")
    )

    PLATE_MIN_DETECTION_CONFIDENCE = float(
        os.getenv("PLATE_MIN_DETECTION_CONFIDENCE", "0.35")
    )
    OCR_MIN_CONFIDENCE = float(os.getenv("OCR_MIN_CONFIDENCE", "0.75"))
    PADDLEOCR_DEVICE = os.getenv("PADDLEOCR_DEVICE", "cpu")
    PADDLEOCR_DETECTION_MODEL_DIR = os.getenv("PADDLEOCR_DETECTION_MODEL_DIR", "")
    PADDLEOCR_RECOGNITION_MODEL_DIR = os.getenv("PADDLEOCR_RECOGNITION_MODEL_DIR", "")
    VIDEO_SAMPLE_FPS = float(os.getenv("VIDEO_SAMPLE_FPS", "4"))

    BOOKINGS_PER_ADVISOR_SLOT = int(
        os.getenv("BOOKINGS_PER_ADVISOR_SLOT", "2")
    )
    BOOKING_SLOT_MINUTES = int(os.getenv("BOOKING_SLOT_MINUTES", "30"))

    EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
    EMAIL_AUTH_METHOD = os.getenv("EMAIL_AUTH_METHOD", "oauth").strip().lower()
    GMAIL_OAUTH_CLIENT_FILE = os.getenv("GMAIL_OAUTH_CLIENT_FILE", "")
    GMAIL_OAUTH_TOKEN_FILE = os.getenv(
        "GMAIL_OAUTH_TOKEN_FILE", "gmail-oauth-token.json"
    )
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "")

    WHATSAPP_ENABLED = os.getenv("WHATSAPP_ENABLED", "false").lower() == "true"
    WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v27.0")
    WHATSAPP_TEMPLATE_NAME = os.getenv(
        "WHATSAPP_TEMPLATE_NAME", "service_gate_arrival"
    )
    WHATSAPP_TEMPLATE_LANGUAGE = os.getenv(
        "WHATSAPP_TEMPLATE_LANGUAGE", "en_US"
    )

settings = Settings()

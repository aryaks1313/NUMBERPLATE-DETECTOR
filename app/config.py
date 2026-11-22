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

    TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")

    DUPLICATE_WINDOW_MINUTES = int(
        os.getenv("DUPLICATE_WINDOW_MINUTES", "10")
    )

settings = Settings()

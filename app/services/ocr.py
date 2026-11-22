from pathlib import Path

import cv2
import pytesseract

from app.config import settings
from app.services.plate_utils import clean_indian_plate


def _configure_tesseract():
    """Use an explicit configured path, or find the standard Windows install."""
    if settings.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
        return

    candidates = (
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    )
    for candidate in candidates:
        if candidate.is_file():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            return


_configure_tesseract()


def preprocess_plate(image):
    if image is None or image.size == 0:
        return ()

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    height, width = gray.shape[:2]
    scale = max(4, min(8, 240 // max(1, height)))
    enlarged = cv2.resize(
        gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
    )
    denoised = cv2.bilateralFilter(enlarged, 9, 35, 35)
    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(denoised)
    thresholded = cv2.adaptiveThreshold(
        enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 9
    )
    return enlarged, enhanced, thresholded, cv2.bitwise_not(thresholded)


def read_plate(image):
    if image is None or image.size == 0:
        return ""

    height, width = image.shape[:2]
    if height > width:
        image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        height, width = image.shape[:2]
    if width >= height * 1.8 and height >= 20:
        # Detector boxes often include the plate border. Trim a small margin
        # so Tesseract sees the character row as one line.
        image = image[
            int(height * 0.10):int(height * 0.90),
            int(width * 0.02):int(width * 0.98),
        ]

    whitelist = "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    candidates = []
    for index, processed in enumerate(preprocess_plate(image)):
        # PSM 8 handles tightly cropped registrations with visible inter-character gaps.
        modes = (8, 7) if index == 0 else (8,)
        for psm in modes:
            raw = pytesseract.image_to_string(
                processed, config=f"--oem 3 --psm {psm} {whitelist}"
            )
            cleaned = clean_indian_plate(raw)
            if cleaned:
                candidates.append(cleaned)

    if not candidates:
        return ""
    # Prefer Indian registration lengths (9–10 characters); avoid joining noise.
    return max(candidates, key=lambda value: (9 <= len(value) <= 10, len(value)))

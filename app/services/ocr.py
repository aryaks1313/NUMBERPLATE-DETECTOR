"""PaddleOCR helpers for reading Indian registration plates."""

import json
import threading

import cv2

from app.config import settings
from app.services.plate_utils import clean_indian_plate


_ocr_engine = None
_ocr_lock = threading.Lock()


def preprocess_plate(image):
    """Make a few clear variants of a plate crop for OCR."""
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


def _get_ocr_engine():
    """Load PaddleOCR on first use so the web app can start without eager model download."""
    global _ocr_engine
    if _ocr_engine is not None:
        return _ocr_engine

    with _ocr_lock:
        if _ocr_engine is not None:
            return _ocr_engine
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise RuntimeError(
                "PaddleOCR is not installed. Install the PaddleOCR and PaddlePaddle "
                "packages listed in requirements.txt, then restart the application."
            ) from exc

        try:
            ocr_options = {
                "lang": "en",
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
                "use_textline_orientation": False,
                "device": settings.PADDLEOCR_DEVICE,
            }
            if settings.PADDLEOCR_DETECTION_MODEL_DIR:
                ocr_options["text_detection_model_dir"] = (
                    settings.PADDLEOCR_DETECTION_MODEL_DIR
                )
            if settings.PADDLEOCR_RECOGNITION_MODEL_DIR:
                ocr_options["text_recognition_model_dir"] = (
                    settings.PADDLEOCR_RECOGNITION_MODEL_DIR
                )
            _ocr_engine = PaddleOCR(
                **ocr_options,
            )
        except Exception as exc:
            raise RuntimeError(
                "Could not initialize PaddleOCR. Check the installed PaddleOCR "
                "dependencies and model download access. Set "
                "PADDLE_PDX_MODEL_SOURCE=BOS or configure local model directories. "
                f"Details: {exc}"
            ) from exc
    return _ocr_engine


def _result_payload(result):
    payload = getattr(result, "json", None)
    if callable(payload):
        payload = payload()
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return {}
    if not isinstance(payload, dict):
        return {}
    return payload.get("res", payload)


def read_plate_result(image):
    """Return cleaned plate text and PaddleOCR recognition confidence (0 to 1)."""
    if image is None or image.size == 0:
        return {"text": "", "confidence": 0.0}

    height, width = image.shape[:2]
    if height > width:
        image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        height, width = image.shape[:2]
    if width >= height * 1.8 and height >= 20:
        image = image[
            int(height * 0.10):int(height * 0.90),
            int(width * 0.02):int(width * 0.98),
        ]

    engine = _get_ocr_engine()
    candidates = []
    # Try the fast enlarged crop first; use the enhanced image only if confidence is low.
    for processed in preprocess_plate(image)[:2]:
        # PaddleOCR's image pipeline is most consistent with three-channel arrays.
        paddle_image = cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)
        for result in engine.predict(paddle_image):
            data = _result_payload(result)
            texts = data.get("rec_texts")
            scores = data.get("rec_scores")
            if texts is None:
                texts = []
            if scores is None:
                scores = []
            joined_text = "".join(str(value) for value in texts)
            plate = clean_indian_plate(joined_text)
            if not plate:
                continue

            valid_scores = [
                float(score) for score in scores
                if score is not None
            ]
            confidence = (
                sum(valid_scores) / len(valid_scores)
                if valid_scores else 0.0
            )
            candidates.append({"text": plate, "confidence": confidence})
        if candidates and max(item["confidence"] for item in candidates) >= settings.OCR_MIN_CONFIDENCE:
            break

    if not candidates:
        return {"text": "", "confidence": 0.0}
    return max(
        candidates,
        key=lambda item: (item["confidence"], 9 <= len(item["text"]) <= 10),
    )


def read_plate(image):
    """Compatibility helper for code that needs only the OCR string."""
    return read_plate_result(image)["text"]

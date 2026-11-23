from pathlib import Path
import os

import cv2
import torch
from ultralytics import YOLO

from app.config import settings


BASE_DIR = Path(__file__).resolve().parent.parent.parent


torch.set_num_threads(min(8, max(1, os.cpu_count() or 1)))


class PlateDetector:

    def __init__(self):
        self.model = None

        model_path = Path(settings.YOLO_MODEL_PATH)

        if not model_path.is_absolute():
            model_path = BASE_DIR / model_path

        self.model_path = model_path.resolve()

    def load_model(self):

        if self.model is not None:
            return self.model

        if not self.model_path.exists():

            raise FileNotFoundError(
                f"YOLO model not found: {self.model_path}"
            )

        print(f"Loading YOLO model: {self.model_path}")

        self.model = YOLO(str(self.model_path))

        print("YOLO model loaded successfully.")

        return self.model

    def apply_roi(self, image):

        height, width = image.shape[:2]

        x1 = int(settings.ROI_X1 * width)
        y1 = int(settings.ROI_Y1 * height)

        x2 = int(settings.ROI_X2 * width)
        y2 = int(settings.ROI_Y2 * height)

        x1 = max(0, min(x1, width - 1))
        y1 = max(0, min(y1, height - 1))

        x2 = max(x1 + 1, min(x2, width))
        y2 = max(y1 + 1, min(y2, height))

        roi = image[y1:y2, x1:x2]

        return roi, x1, y1

    def detect(self, image):

        model = self.load_model()

        roi, offset_x, offset_y = self.apply_roi(image)

        detections = []

        height, width = image.shape[:2]

       
        image_size = max(224, int(settings.YOLO_IMAGE_SIZE))
        
        confidence_threshold = min(float(settings.YOLO_CONFIDENCE), 0.15)
        orientations = (
            (roi, None),
            (cv2.rotate(roi, cv2.ROTATE_90_COUNTERCLOCKWISE), "ccw"),
            (cv2.rotate(roi, cv2.ROTATE_90_CLOCKWISE), "cw"),
        )

        for oriented, rotation in orientations:
            results = model.predict(
                source=oriented,
                conf=confidence_threshold,
                imgsz=image_size,
                verbose=False
            )
            orientation_detections = []

            for result in results:

                if result.boxes is None:
                    continue

                for box in result.boxes:

                    x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())

                    
                    oh, ow = roi.shape[:2]
                    if rotation == "ccw":
                        x1, y1, x2, y2 = ow - y2, x1, ow - y1, x2
                    elif rotation == "cw":
                        x1, y1, x2, y2 = y1, oh - x2, y2, oh - x1

                    x1 += offset_x
                    y1 += offset_y
                    x2 += offset_x
                    y2 += offset_y

                    x1 = max(0, min(x1, width - 1))
                    y1 = max(0, min(y1, height - 1))

                    x2 = max(x1 + 1, min(x2, width))
                    y2 = max(y1 + 1, min(y2, height))

                    crop = image[y1:y2, x1:x2]

                    if crop.size == 0:
                        continue

                    confidence = float(box.conf[0].cpu().item())

                    orientation_detections.append({

                        "box": [x1, y1, x2, y2],

                        "confidence": confidence,

                        "crop": crop

                    })

            if orientation_detections:
                detections = orientation_detections
                break

        return detections


plate_detector = PlateDetector()

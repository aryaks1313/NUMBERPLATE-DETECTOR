import threading
import time

from pathlib import Path

import cv2


class CameraMonitor:

    def __init__(self):

        self.running = False

        self.thread = None

        self.stop_event = threading.Event()

        self.lock = threading.Lock()

        self.last_error = None

        self.frames_processed = 0

        self.last_result = None

        self.latest_frame_url = None

        self.output_dir = (
            Path(__file__).resolve().parent.parent.parent
            / "uploads"
            / "monitor"
        )

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        self.latest_frame_path = (
            self.output_dir / "latest.jpg"
        )

    def start(
        self,
        camera_source,
        process_frame,
        interval=0.0
    ):

        with self.lock:

            if self.running:

                return {
                    "message": "Camera is already running",
                    "running": True
                }

            self.stop_event.clear()

            self.last_error = None

            self.frames_processed = 0

            self.last_result = None

            self.latest_frame_url = None

            self.running = True

            self.thread = threading.Thread(

                target=self._run,

                args=(
                    camera_source,
                    process_frame,
                    interval
                ),

                daemon=True

            )

            self.thread.start()

        return {
            "message": "Camera monitoring started",
            "running": True
        }

    def _run(
        self,
        camera_source,
        process_frame,
        interval
    ):

        camera = None

        try:

            camera = cv2.VideoCapture(camera_source)

            if not camera.isOpened():

                raise RuntimeError(
                    "Unable to open camera source."
                )

            while not self.stop_event.is_set():

                success, frame = camera.read()

                if not success:

                    self.last_error = (
                        "Could not read camera frame."
                    )

                    time.sleep(1)

                    continue

                try:

                    result = process_frame(frame)

                    result = result or {}

                    annotated = frame.copy()

                    box = result.get("box")

                    plate = result.get("plate_number")

                    status = result.get("status", "processing")

                    if box:

                        x1, y1, x2, y2 = box

                        cv2.rectangle(
                            annotated,
                            (x1, y1),
                            (x2, y2),
                            (0, 215, 255),
                            3
                        )

                    text = (
                        f"{plate or 'No plate'} "
                        f"| {status}"
                    )

                    cv2.putText(
                        annotated,
                        text,
                        (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 215, 255),
                        2
                    )

                    cv2.imwrite(
                        str(self.latest_frame_path),
                        annotated
                    )

                    with self.lock:

                        self.frames_processed += 1

                        self.last_result = result

                        self.latest_frame_url = (
                            "/uploads/monitor/latest.jpg"
                        )

                        self.last_error = None

                except Exception as exc:

                    self.last_error = str(exc)

                if interval > 0:
                    time.sleep(interval)

        except Exception as exc:

            self.last_error = str(exc)

        finally:

            if camera is not None:

                camera.release()

            with self.lock:

                self.running = False

    def stop(self):

        self.stop_event.set()

        thread = self.thread

        if thread and thread.is_alive():

            thread.join(timeout=5)

        with self.lock:

            self.running = False

        return {
            "message": "Camera monitoring stopped",
            "running": False
        }

    def status(self):

        with self.lock:

            return {

                "running": self.running,

                "frames_processed": (
                    self.frames_processed
                ),

                "last_error": self.last_error,

                "last_result": self.last_result,

                "latest_frame_url": (
                    self.latest_frame_url
                )

            }


camera_monitor = CameraMonitor()

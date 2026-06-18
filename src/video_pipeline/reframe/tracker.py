"""Subject tracking seam.

A ``SubjectTracker`` reads a video and returns, per sampled frame, the subject's
horizontal centre (and an optional bbox). Implementations sit behind the
``SubjectTracker`` Protocol so the reframe plan/command logic never depends on a
particular detector.

Two real implementations ship:

  - ``OpenCVFaceTracker`` (default) — OpenCV Haar-cascade face detection. The
    cascade ships *inside* the ``opencv-python`` wheel (no model download), so it
    runs anywhere OpenCV is installed and is immune to MediaPipe's API churn.

  - ``MediaPipeTracker`` — MediaPipe **Tasks API** FaceDetector (the current API;
    the legacy ``mp.solutions`` API was removed from recent wheels). Downloads a
    small model bundle on first use. Opt-in via ``--tracker mediapipe``.

Tests use ``FixedTracker`` and need no native build.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Protocol


@dataclass(frozen=True)
class FrameSubject:
    """Subject location for one sampled frame, in source-pixel coordinates."""

    t: float                 # timestamp (seconds)
    cx: float                # subject centre x
    cy: float                # subject centre y
    bbox: Optional[tuple] = None  # (x0, y0, x1, y1), optional
    confidence: float = 1.0


class SubjectTracker(Protocol):
    def track(self, video_path: str) -> List[FrameSubject]:
        ...


class FixedTracker:
    """Deterministic tracker for tests/fallback: replays a supplied path."""

    def __init__(self, subjects: List[FrameSubject]):
        self._subjects = list(subjects)

    def track(self, video_path: str) -> List[FrameSubject]:
        return list(self._subjects)


def _open_capture(video_path: str):
    import cv2

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"could not open video: {video_path}")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    return cap, src_fps


class OpenCVFaceTracker:
    """Subject tracking via OpenCV's bundled Haar-cascade face detector.

    The default tracker. Samples at ``sample_fps``, takes the largest detected
    face per sampled frame, and holds the last known centre (low confidence)
    when no face is found so the plan can still proceed. No model download.
    """

    def __init__(self, sample_fps: float = 5.0, min_size_frac: float = 0.05):
        self.sample_fps = sample_fps
        self.min_size_frac = min_size_frac

    def track(self, video_path: str) -> List[FrameSubject]:
        import cv2

        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        cascade = cv2.CascadeClassifier(cascade_path)
        if cascade.empty():
            raise RuntimeError(f"failed to load Haar cascade: {cascade_path}")

        cap, src_fps = _open_capture(video_path)
        step = max(1, int(round(src_fps / self.sample_fps)))

        subjects: List[FrameSubject] = []
        last_cx: Optional[float] = None
        frame_idx = 0
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                if frame_idx % step == 0:
                    h, w = frame.shape[:2]
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    min_size = (int(w * self.min_size_frac), int(h * self.min_size_frac))
                    faces = cascade.detectMultiScale(
                        gray, scaleFactor=1.1, minNeighbors=5, minSize=min_size
                    )
                    t = frame_idx / src_fps
                    if len(faces):
                        x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
                        cx, cy = x + fw / 2, y + fh / 2
                        subjects.append(
                            FrameSubject(t=t, cx=cx, cy=cy,
                                         bbox=(x, y, x + fw, y + fh), confidence=1.0)
                        )
                        last_cx = cx
                    else:
                        subjects.append(
                            FrameSubject(
                                t=t,
                                cx=last_cx if last_cx is not None else w / 2,
                                cy=h / 2,
                                confidence=0.0,
                            )
                        )
                frame_idx += 1
        finally:
            cap.release()
        return subjects


class MediaPipeTracker:
    """Subject tracking via the MediaPipe Tasks FaceDetector (opt-in).

    Uses the current Tasks API — the legacy ``mp.solutions`` API was removed from
    recent wheels. The model bundle is downloaded once and cached. Needs
    ``mediapipe`` and ``opencv-python`` (the ``[reframe]`` extra).
    """

    MODEL_URL = (
        "https://storage.googleapis.com/mediapipe-models/face_detector/"
        "blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
    )

    def __init__(self, sample_fps: float = 5.0, min_confidence: float = 0.5,
                 model_path: Optional[str] = None):
        self.sample_fps = sample_fps
        self.min_confidence = min_confidence
        self.model_path = model_path

    def _ensure_model(self) -> str:  # pragma: no cover - network + cache
        import os
        import urllib.request

        if self.model_path and os.path.exists(self.model_path):
            return self.model_path
        cache_dir = os.path.join(
            os.path.expanduser("~"), ".cache", "video-pipeline", "models"
        )
        os.makedirs(cache_dir, exist_ok=True)
        dest = os.path.join(cache_dir, "blaze_face_short_range.tflite")
        if not os.path.exists(dest):
            urllib.request.urlretrieve(self.MODEL_URL, dest)
        return dest

    def track(self, video_path: str) -> List[FrameSubject]:  # pragma: no cover - native deps + footage
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
        except ImportError as exc:
            raise RuntimeError(
                "MediaPipeTracker requires `mediapipe` and `opencv-python` "
                "(the `[reframe]` extra)."
            ) from exc

        model = self._ensure_model()
        options = vision.FaceDetectorOptions(
            base_options=mp_python.BaseOptions(model_asset_path=model),
            running_mode=vision.RunningMode.VIDEO,
            min_detection_confidence=self.min_confidence,
        )
        detector = vision.FaceDetector.create_from_options(options)

        cap, src_fps = _open_capture(video_path)
        step = max(1, int(round(src_fps / self.sample_fps)))
        subjects: List[FrameSubject] = []
        last_cx: Optional[float] = None
        frame_idx = 0
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                if frame_idx % step == 0:
                    h, w = frame.shape[:2]
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    t = frame_idx / src_fps
                    result = detector.detect_for_video(mp_image, int(t * 1000))
                    if result.detections:
                        det = max(
                            result.detections,
                            key=lambda d: d.bounding_box.width * d.bounding_box.height,
                        )
                        bb = det.bounding_box
                        cx, cy = bb.origin_x + bb.width / 2, bb.origin_y + bb.height / 2
                        subjects.append(
                            FrameSubject(
                                t=t, cx=cx, cy=cy,
                                bbox=(bb.origin_x, bb.origin_y,
                                      bb.origin_x + bb.width, bb.origin_y + bb.height),
                                confidence=1.0,
                            )
                        )
                        last_cx = cx
                    else:
                        subjects.append(
                            FrameSubject(
                                t=t, cx=last_cx if last_cx is not None else w / 2,
                                cy=h / 2, confidence=0.0,
                            )
                        )
                frame_idx += 1
        finally:
            cap.release()
            detector.close()
        return subjects

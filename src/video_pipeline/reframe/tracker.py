"""Subject tracking seam.

A ``SubjectTracker`` reads a video and returns, per sampled frame, the subject's
horizontal centre (and an optional bbox). The production implementation uses
MediaPipe; it is imported lazily so the rest of the package — and the test suite
— never depends on a native MediaPipe/OpenCV build. Tests use ``FixedTracker``.
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


class MediaPipeTracker:
    """Subject tracking via MediaPipe face/pose landmarks (daily-driver only).

    MediaPipe and OpenCV are imported lazily inside ``track`` so importing this
    module never requires them. Sampling at ``sample_fps`` keeps cost bounded;
    ``build_crop_plan`` interpolates/smooths between samples.
    """

    def __init__(self, sample_fps: float = 5.0, min_confidence: float = 0.5):
        self.sample_fps = sample_fps
        self.min_confidence = min_confidence

    def track(self, video_path: str) -> List[FrameSubject]:  # pragma: no cover - needs native deps + footage
        try:
            import cv2
            import mediapipe as mp
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "MediaPipeTracker requires `mediapipe` and `opencv-python`. "
                "Install them on the daily driver (Ono-Sendai); they are not "
                "available in the JasonOS sandbox."
            ) from exc

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"could not open video: {video_path}")
        src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        step = max(1, int(round(src_fps / self.sample_fps)))

        subjects: List[FrameSubject] = []
        detector = mp.solutions.face_detection.FaceDetection(
            min_detection_confidence=self.min_confidence
        )
        frame_idx = 0
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                if frame_idx % step == 0:
                    h, w = frame.shape[:2]
                    res = detector.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    t = frame_idx / src_fps
                    if res.detections:
                        det = max(
                            res.detections,
                            key=lambda d: d.score[0] if d.score else 0.0,
                        )
                        box = det.location_data.relative_bounding_box
                        x0 = box.xmin * w
                        y0 = box.ymin * h
                        bw = box.width * w
                        bh = box.height * h
                        subjects.append(
                            FrameSubject(
                                t=t,
                                cx=x0 + bw / 2,
                                cy=y0 + bh / 2,
                                bbox=(x0, y0, x0 + bw, y0 + bh),
                                confidence=det.score[0] if det.score else 1.0,
                            )
                        )
                    else:
                        # no detection: hold frame centre, low confidence
                        subjects.append(
                            FrameSubject(t=t, cx=w / 2, cy=h / 2, confidence=0.0)
                        )
                frame_idx += 1
        finally:
            cap.release()
            detector.close()
        return subjects

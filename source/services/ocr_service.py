from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    text: str
    confidence: Optional[float]
    engine_name: str


class OCRService:
    def __init__(self) -> None:
        self._rapid_engine = None
        self._paddle_engine = None

    def available(self) -> bool:
        return self._load_rapid() is not None or self._load_paddle() is not None

    def recognize(self, image_array: np.ndarray) -> OCRResult:
        rapid = self._load_rapid()
        if rapid is not None:
            result = self._recognize_by_rapid(rapid, image_array)
            if result.text.strip():
                return result

        paddle = self._load_paddle()
        if paddle is not None:
            result = self._recognize_by_paddle(paddle, image_array)
            if result.text.strip():
                return result

        raise RuntimeError("未找到可用的 OCR 引擎，请安装 rapidocr_onnxruntime 或 paddleocr。")

    @staticmethod
    def score_result(result: OCRResult) -> tuple[int, float]:
        return len(result.text.strip()), result.confidence or 0.0

    def _load_rapid(self):
        if self._rapid_engine is not None:
            return self._rapid_engine
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            return None

        self._rapid_engine = RapidOCR()
        logger.info("Loaded OCR engine: RapidOCR")
        return self._rapid_engine

    def _load_paddle(self):
        if self._paddle_engine is not None:
            return self._paddle_engine
        try:
            from paddleocr import PaddleOCR
        except ImportError:
            return None

        self._paddle_engine = PaddleOCR(
            use_angle_cls=True,
            lang="ch",
            show_log=False,
        )
        logger.info("Loaded OCR engine: PaddleOCR")
        return self._paddle_engine

    def _recognize_by_rapid(self, engine, image_array: np.ndarray) -> OCRResult:
        lines = []
        scores = []

        result, _ = engine(image_array)
        if result:
            for item in result:
                if len(item) < 3:
                    continue
                text = str(item[1]).strip()
                score = float(item[2]) if item[2] is not None else None
                if text:
                    lines.append(text)
                    if score is not None:
                        scores.append(score)

        confidence = round(sum(scores) / len(scores), 4) if scores else None
        return OCRResult(text="\n".join(lines), confidence=confidence, engine_name="RapidOCR")

    def _recognize_by_paddle(self, engine, image_array: np.ndarray) -> OCRResult:
        lines = []
        scores = []

        result = engine.ocr(image_array, cls=True)
        if result:
            for page in result:
                if not page:
                    continue
                for item in page:
                    if len(item) < 2:
                        continue
                    text = str(item[1][0]).strip()
                    score = float(item[1][1]) if len(item[1]) > 1 else None
                    if text:
                        lines.append(text)
                        if score is not None:
                            scores.append(score)

        confidence = round(sum(scores) / len(scores), 4) if scores else None
        return OCRResult(text="\n".join(lines), confidence=confidence, engine_name="PaddleOCR")

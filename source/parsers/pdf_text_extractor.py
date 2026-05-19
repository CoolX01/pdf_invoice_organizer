from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
from typing import Optional

import fitz
from PIL import Image

from services.ocr_service import OCRService
from utils.formatters import clean_text
from utils.image_utils import build_ocr_variants
from utils.logging_utils import safe_log_path

logger = logging.getLogger(__name__)


@dataclass
class TextExtractionResult:
    text: str = ""
    method: str = ""
    ocr_used: bool = False
    ocr_confidence: Optional[float] = None
    ocr_engine: str = ""
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return bool(clean_text(self.text))


class PDFTextExtractor:
    def __init__(
        self,
        ocr_service: OCRService,
        enable_ocr: bool = True,
        max_ocr_pages: int = 10,
        ocr_render_scale: float = 2.0,
        ocr_try_variants: bool = True,
    ) -> None:
        self.ocr_service = ocr_service
        self.enable_ocr = enable_ocr
        self.max_ocr_pages = max(1, int(max_ocr_pages))
        self.ocr_render_scale = max(1.0, float(ocr_render_scale))
        self.ocr_try_variants = ocr_try_variants

    def extract(self, file_path: Path) -> TextExtractionResult:
        errors: list[str] = []
        text = self._extract_with_pymupdf(file_path)
        if self._enough_text(text):
            return TextExtractionResult(text=text, method="PyMuPDF")

        fallback_text = self._extract_with_pdfplumber(file_path)
        if self._enough_text(fallback_text):
            return TextExtractionResult(text=fallback_text, method="pdfplumber")

        if not self.enable_ocr:
            errors.append("未启用 OCR，无法识别扫描版 PDF")
            return TextExtractionResult(text=text or fallback_text, method="none", errors=errors)

        try:
            ocr_text, confidence, engine_name = self._extract_with_ocr(file_path)
            if self._enough_text(ocr_text):
                return TextExtractionResult(
                    text=ocr_text,
                    method=f"OCR:{engine_name}",
                    ocr_used=True,
                    ocr_confidence=confidence,
                    ocr_engine=engine_name,
                )
            errors.append("OCR 未提取到有效文本")
        except Exception:
            logger.warning("OCR failed for %s", safe_log_path(file_path))
            errors.append("OCR 识别失败")

        return TextExtractionResult(
            text=text or fallback_text,
            method="failed",
            errors=errors,
        )

    def extract_ocr(self, file_path: Path) -> TextExtractionResult:
        if not self.enable_ocr:
            return TextExtractionResult(
                method="none",
                errors=["未启用 OCR，无法执行视觉复核"],
            )

        try:
            ocr_text, confidence, engine_name = self._extract_with_ocr(file_path)
        except Exception:
            logger.warning("OCR audit failed for %s", safe_log_path(file_path))
            return TextExtractionResult(
                method="failed",
                ocr_used=True,
                errors=["OCR 自动复核失败"],
            )

        if self._enough_text(ocr_text):
            return TextExtractionResult(
                text=ocr_text,
                method=f"OCR:{engine_name}",
                ocr_used=True,
                ocr_confidence=confidence,
                ocr_engine=engine_name,
            )

        return TextExtractionResult(
            text=ocr_text,
            method=f"OCR:{engine_name}" if engine_name else "OCR",
            ocr_used=True,
            ocr_confidence=confidence,
            ocr_engine=engine_name,
            errors=["OCR 自动复核未提取到有效文本"],
        )

    def _extract_with_pymupdf(self, file_path: Path) -> str:
        chunks: list[str] = []
        with fitz.open(file_path) as document:
            for page in document:
                page_text = page.get_text("text", sort=True)
                if page_text:
                    chunks.append(page_text)
        return "\n".join(chunks).strip()

    def _extract_with_pdfplumber(self, file_path: Path) -> str:
        try:
            import pdfplumber
        except ImportError:
            return ""

        chunks: list[str] = []
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    if page_text.strip():
                        chunks.append(page_text)
        except Exception:
            logger.warning("pdfplumber extraction failed for %s", safe_log_path(file_path))
            return ""
        return "\n".join(chunks).strip()

    def _extract_with_ocr(self, file_path: Path) -> tuple[str, Optional[float], str]:
        texts: list[str] = []
        confidences: list[float] = []
        engine_name = ""

        with fitz.open(file_path) as document:
            for page_index, page in enumerate(document, start=1):
                if page_index > self.max_ocr_pages:
                    logger.info(
                        "OCR page limit reached for %s at %s pages",
                        safe_log_path(file_path),
                        self.max_ocr_pages,
                    )
                    break

                matrix = fitz.Matrix(self.ocr_render_scale, self.ocr_render_scale)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                image = Image.frombytes(
                    "RGB",
                    [pixmap.width, pixmap.height],
                    pixmap.samples,
                )
                result = None
                variant_name = "original"
                variants = build_ocr_variants(image)
                if not self.ocr_try_variants:
                    variants = variants[:1]
                for variant in variants:
                    candidate = self.ocr_service.recognize(variant.data)
                    if (
                        result is None
                        or self.ocr_service.score_result(candidate)
                        > self.ocr_service.score_result(result)
                    ):
                        result = candidate
                        variant_name = variant.name
                    if self._is_good_ocr_result(candidate):
                        break

                if result is None:
                    continue

                engine_name = result.engine_name
                if result.text.strip():
                    texts.append(result.text)
                if result.confidence is not None:
                    confidences.append(result.confidence)
                logger.info(
                    "OCR page %s for %s with engine %s and variant %s",
                    page_index,
                    safe_log_path(file_path),
                    engine_name,
                    variant_name,
                )

        confidence = round(sum(confidences) / len(confidences), 4) if confidences else None
        return "\n".join(texts).strip(), confidence, engine_name

    def _enough_text(self, text: str) -> bool:
        normalized = clean_text(text)
        if len(normalized) >= 30:
            return True
        return "发票" in normalized and len(normalized) >= 12

    def _is_good_ocr_result(self, result) -> bool:
        text_length = len(clean_text(result.text))
        confidence = result.confidence or 0.0
        return text_length >= 80 and confidence >= 0.85

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps


@dataclass
class ImageVariant:
    name: str
    data: np.ndarray


def build_ocr_variants(image: Image.Image) -> list[ImageVariant]:
    base = image.convert("RGB")
    variants: list[ImageVariant] = [ImageVariant(name="original", data=np.array(base))]

    grayscale = ImageOps.grayscale(base)
    variants.append(ImageVariant(name="grayscale", data=np.array(grayscale)))

    normalized = _normalize_background(grayscale)
    variants.append(ImageVariant(name="normalized", data=np.array(normalized)))

    threshold = normalized.point(lambda value: 255 if value > 170 else 0)
    variants.append(ImageVariant(name="threshold", data=np.array(threshold)))

    return variants


def _normalize_background(image: Image.Image) -> Image.Image:
    normalized = image
    mean_value = float(np.array(image).mean())
    if mean_value < 120:
        normalized = ImageOps.invert(normalized)
    return ImageOps.autocontrast(normalized)

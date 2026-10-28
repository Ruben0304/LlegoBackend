"""OCR service for menu images: decoding, running RapidOCR, building indexed payloads."""

import asyncio
import json
import logging
from io import BytesIO
from typing import Optional

import numpy as np
from PIL import Image, ImageOps

from domain.models import BranchMenu
from repositories import branch_menus_repo
from services.menu_ocr_utils import (
    assess_quality,
    build_index_fields,
    limit_lines,
    normalize_box,
    ocr_metrics,
    photo_metrics,
)
from utils.s3 import get_s3_client
from core.config import settings

logger = logging.getLogger(__name__)

# Constants
MAX_OCR_SIDE = 1920
OCR_TIMEOUT_SECONDS = 90
MAX_LINES = 400

# Lazy-initialized RapidOCR engine
_ocr_engine = None
_ocr_semaphore: Optional[asyncio.Semaphore] = None


def _get_engine():
    """Lazy-initialize RapidOCR engine. Returns engine or raises RuntimeError."""
    global _ocr_engine
    if _ocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR

            _ocr_engine = RapidOCR()
        except ImportError as e:
            raise RuntimeError(
                f"RapidOCR engine not available (rapidocr_onnxruntime not installed): {e}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Failed to initialize RapidOCR engine: {e}") from e
    return _ocr_engine


async def _get_semaphore() -> asyncio.Semaphore:
    """Lazy-initialize semaphore for OCR concurrency control."""
    global _ocr_semaphore
    if _ocr_semaphore is None:
        _ocr_semaphore = asyncio.Semaphore(1)
    return _ocr_semaphore


async def fetch_image_bytes(key: str) -> bytes:
    """Fetch image bytes from S3.

    Args:
        key: S3 object key

    Returns:
        Raw image bytes

    Raises:
        Exception: If S3 fetch fails
    """

    def _fetch():
        s3_client = get_s3_client()
        response = s3_client.get_object(Bucket=settings.s3_bucket_name, Key=key)
        return response["Body"].read()

    return await asyncio.to_thread(_fetch)


def decode_image(data: bytes) -> np.ndarray:
    """Decode image bytes and resize if needed.

    Args:
        data: Raw image bytes (JPEG, PNG, etc.)

    Returns:
        ndarray HxWx3 uint8 in RGB format

    Raises:
        ValueError: If bytes are not a valid image
    """
    try:
        img = Image.open(BytesIO(data))
        img.load()
    except Exception as e:
        raise ValueError(f"Failed to open image: {e}") from e

    # Apply EXIF orientation
    img = ImageOps.exif_transpose(img)

    # Convert to RGB
    if img.mode != "RGB":
        img = img.convert("RGB")

    # Resize if needed
    w, h = img.size
    if max(w, h) > MAX_OCR_SIDE:
        img.thumbnail((MAX_OCR_SIDE, MAX_OCR_SIDE), Image.LANCZOS)

    return np.array(img, dtype=np.uint8)


def run_ocr(rgb: np.ndarray) -> list[dict]:
    """Run OCR on RGB image (SYNCHRONOUS, blocking).

    Args:
        rgb: HxWx3 uint8 ndarray in RGB format

    Returns:
        List of dicts with 'text', 'conf', 'box' (box in pixels)
    """
    engine = _get_engine()
    result, _ = engine(rgb)

    if result is None:
        return []

    lines = []
    for item in result:
        box, text, conf = item
        # conf can come as str: convert to float
        try:
            conf_float = float(conf)
        except (ValueError, TypeError):
            conf_float = 0.0

        lines.append(
            {
                "text": text,
                "conf": conf_float,
                "box": box,  # List of 4 points in pixels
            }
        )

    return lines


def build_payload(
    raw_lines: list[dict], width: int, height: int, photo: dict
) -> dict:
    """Build OCR result payload (pure function, no I/O).

    Args:
        raw_lines: Raw lines from OCR with boxes in pixels
        width: Image width in pixels
        height: Image height in pixels
        photo: Photo metrics dict (from photo_metrics)

    Returns:
        Dict with 'lines', 'tokens', 'trigrams', 'quality'
    """
    # 1. Calculate OCR metrics on pixel-based boxes
    ocr = ocr_metrics(raw_lines)

    # 2. Assess quality
    quality = assess_quality(photo, ocr)
    # Add metrics (float, rounded to 3 decimals, JSON-serializable)
    metrics = {**photo, **ocr}
    # Round floats to 3 decimals
    rounded_metrics = {}
    for k, v in metrics.items():
        if isinstance(v, float):
            rounded_metrics[k] = round(v, 3)
        elif isinstance(v, (int, str, bool)):
            rounded_metrics[k] = v
        # Exclude numpy types and other non-serializable types
    quality["metrics"] = rounded_metrics

    # 3. Limit lines and normalize boxes
    lines = limit_lines(raw_lines, MAX_LINES)
    normalized_lines = []
    for line in lines:
        box = line.get("box")
        conf = line.get("conf", 0.0)
        text = line.get("text", "")

        if box:
            normalized_box = normalize_box(box, width, height)
        else:
            normalized_box = []

        normalized_lines.append(
            {"text": text, "conf": round(conf, 3), "box": normalized_box}
        )

    # 4. Build index
    index = build_index_fields(normalized_lines)

    return {
        "lines": normalized_lines,
        "tokens": index["tokens"],
        "trigrams": index["trigrams"],
        "quality": quality,
    }


def analyze_image(data: bytes) -> dict:
    """Decode, measure, OCR and index one menu image (SYNCHRONOUS, CPU-bound).

    Returns the payload built by `build_payload`. Run it with `asyncio.to_thread`.
    """
    rgb = decode_image(data)
    height, width, _ = rgb.shape
    photo = photo_metrics(rgb)
    raw_lines = run_ocr(rgb)
    return build_payload(raw_lines, width, height, photo)


async def process_menu(menu: BranchMenu) -> bool:
    """Process a single menu: fetch, OCR, save results.

    Args:
        menu: BranchMenu object with id, image, etc.

    Returns:
        True if processed successfully (done), False if failed
    """
    try:
        # Fetch image from S3
        image_bytes = await fetch_image_bytes(menu.image)

        # All CPU-bound work (decode, OpenCV metrics, OCR, indexing) runs in ONE
        # worker thread so it never blocks the event loop that serves the API.
        # The semaphore keeps a single OCR running at a time. Note: wait_for cannot
        # kill the thread, it only stops waiting for it.
        sem = await _get_semaphore()
        async with sem:
            try:
                payload = await asyncio.wait_for(
                    asyncio.to_thread(analyze_image, image_bytes),
                    timeout=OCR_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError as e:
                raise TimeoutError(f"OCR timed out after {OCR_TIMEOUT_SECONDS}s") from e

        # Save to Mongo
        success = await branch_menus_repo.set_ocr_result(
            str(menu.id),
            menu.image,
            payload["lines"],
            payload["tokens"],
            payload["trigrams"],
            payload["quality"],
        )

        if success:
            logger.info(f"OCR processed menu {menu.id}: {len(payload['lines'])} lines")
            return True
        else:
            logger.warning(
                f"OCR result not saved (image may have changed): menu {menu.id}"
            )
            return False

    except Exception as e:
        logger.error(f"OCR processing failed for menu {menu.id}: {type(e).__name__}: {e}")
        # Save error to Mongo
        await branch_menus_repo.set_ocr_failed(
            str(menu.id), menu.image, f"{type(e).__name__}: {e}"
        )
        return False

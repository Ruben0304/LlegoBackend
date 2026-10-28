"""Tests for menu OCR service.

Covers:
  1. decode_image: opening bytes, EXIF handling, resizing, error handling
  2. build_payload: normalization, MAX_LINES, index fields, JSON serialization, incline calc
  3. process_menu: with mocks, error handling
  4. process_pending_menus: batch processing, error resilience

Run with:
    python3 -m pytest tests/test_menu_ocr_service.py -v
"""

import asyncio
import io
import json
import math
import os
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

# Set env vars BEFORE imports
os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "https://s3.amazonaws.com")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")
os.environ.setdefault("REDIS_URL", "redis://invalid-host-for-tests:6379")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-unit-tests-only")

from domain.models import BranchMenu
from services.menu_ocr_service import (
    decode_image,
    build_payload,
    process_menu,
    MAX_OCR_SIDE,
)
from services.menu_ocr_worker import process_pending_menus


class TestDecodeImage(unittest.TestCase):
    """Tests for decode_image function."""

    def test_decode_valid_png(self):
        """Test decoding a valid PNG image."""
        # Create a simple PNG in memory
        img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        result = decode_image(png_bytes)
        assert result.shape == (100, 100, 3)
        assert result.dtype == np.uint8

    def test_decode_valid_jpeg(self):
        """Test decoding a valid JPEG image."""
        img = Image.new("RGB", (200, 150), color=(0, 255, 0))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        jpeg_bytes = buf.getvalue()

        result = decode_image(jpeg_bytes)
        assert result.shape == (150, 200, 3)
        assert result.dtype == np.uint8

    def test_decode_converts_to_rgb(self):
        """Test that RGBA is converted to RGB."""
        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        result = decode_image(png_bytes)
        assert result.shape == (100, 100, 3)

    def test_decode_resizes_large_image(self):
        """Test that large images are resized to MAX_OCR_SIDE."""
        # Create a 4000x3000 image
        img = Image.new("RGB", (4000, 3000), color=(100, 100, 100))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        result = decode_image(png_bytes)
        # Should be resized to fit within MAX_OCR_SIDE x MAX_OCR_SIDE
        assert max(result.shape[0], result.shape[1]) <= MAX_OCR_SIDE
        assert result.dtype == np.uint8

    def test_decode_preserves_small_image(self):
        """Test that small images are not enlarged."""
        img = Image.new("RGB", (200, 150), color=(50, 50, 50))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        result = decode_image(png_bytes)
        assert result.shape == (150, 200, 3)

    def test_decode_invalid_bytes_raises_valueerror(self):
        """Test that invalid image data raises ValueError."""
        with pytest.raises(ValueError, match="Failed to open image"):
            decode_image(b"not an image")


class TestBuildPayload(unittest.TestCase):
    """Tests for build_payload function."""

    def test_build_payload_normalizes_boxes(self):
        """Test that boxes are normalized to 0-1 range."""
        raw_lines = [
            {
                "text": "PIZZA",
                "conf": 0.95,
                "box": [[100, 100], [300, 100], [300, 200], [100, 200]],
            }
        ]
        photo = {
            "nitidez": 100.0,
            "brillo": 120.0,
            "contraste": 50.0,
            "lado_corto": 1000,
            "reflejo_pct": 0.0,
        }

        result = build_payload(raw_lines, 1000, 2000, photo)

        # Check that first line's box is normalized
        assert result["lines"][0]["box"] == [
            [0.1, 0.05],
            [0.3, 0.05],
            [0.3, 0.1],
            [0.1, 0.1],
        ]

    def test_build_payload_respects_max_lines(self):
        """Test that MAX_LINES limit is respected."""
        from services.menu_ocr_service import MAX_LINES

        # Create more than MAX_LINES lines with varying confidence
        raw_lines = [
            {
                "text": f"LINE{i}",
                "conf": 0.9 if i % 2 == 0 else 0.5,
                "box": [[0, i * 10], [100, i * 10], [100, (i + 1) * 10], [0, (i + 1) * 10]],
            }
            for i in range(MAX_LINES + 50)
        ]
        photo = {
            "nitidez": 100.0,
            "brillo": 120.0,
            "contraste": 50.0,
            "lado_corto": 1000,
            "reflejo_pct": 0.0,
        }

        result = build_payload(raw_lines, 1000, 2000, photo)

        # Should have only MAX_LINES
        assert len(result["lines"]) <= MAX_LINES

    def test_build_payload_has_tokens_and_trigrams(self):
        """Test that tokens and trigrams are populated."""
        raw_lines = [
            {
                "text": "PIZZA MARGARITA",
                "conf": 0.95,
                "box": [[0, 0], [100, 0], [100, 50], [0, 50]],
            },
            {
                "text": "8.50",
                "conf": 0.90,
                "box": [[0, 50], [100, 50], [100, 100], [0, 100]],
            },
        ]
        photo = {
            "nitidez": 100.0,
            "brillo": 120.0,
            "contraste": 50.0,
            "lado_corto": 1000,
            "reflejo_pct": 0.0,
        }

        result = build_payload(raw_lines, 1000, 2000, photo)

        assert len(result["tokens"]) > 0
        assert len(result["trigrams"]) > 0
        # 'pizza' and 'margarita' should be tokenized
        assert "pizza" in result["tokens"]
        assert "margarita" in result["tokens"]

    def test_build_payload_quality_metrics_serializable(self):
        """Test that quality.metrics is JSON-serializable (no numpy types)."""
        raw_lines = [
            {
                "text": "TEST",
                "conf": 0.85,
                "box": [[10, 10], [50, 10], [50, 30], [10, 30]],
            }
        ]
        photo = {
            "nitidez": 150.5,
            "brillo": np.float32(110.0),
            "contraste": 45.0,
            "lado_corto": 800,
            "reflejo_pct": 1.5,
        }

        result = build_payload(raw_lines, 500, 1000, photo)

        # Should be JSON-serializable
        json_str = json.dumps(result["quality"]["metrics"])
        assert json_str is not None
        # All numeric values should be floats rounded to 3 decimals
        metrics = json.loads(json_str)
        for k, v in metrics.items():
            if isinstance(v, float):
                # Check it's rounded to 3 decimals (may have fewer if trailing zeros removed)
                assert len(str(v).split(".")[-1]) <= 3

    def test_build_payload_incline_calculated_in_pixels(self):
        """Test that incline is calculated on pixel-based boxes (before normalization).

        A box inclined ~5° should show incline ≈ 5±1 in quality.metrics.
        """
        # Create a line with ~5° angle
        # For a 2000x1000 image: top-left (100, 100), top-right (400, 115)
        # atan2(115-100, 400-100) = atan2(15, 300) ≈ 2.86° (small)
        # Let's use larger delta: atan2(50, 500) ≈ 5.7°
        angle_rad = math.atan2(50, 500)
        angle_deg = math.degrees(angle_rad)

        raw_lines = [
            {
                "text": "INCLINED",
                "conf": 0.95,
                "box": [
                    [100, 100],
                    [600, 150],  # 50px drop over 500px
                    [600, 200],
                    [100, 150],
                ],
            }
        ]
        photo = {
            "nitidez": 100.0,
            "brillo": 120.0,
            "contraste": 50.0,
            "lado_corto": 1000,
            "reflejo_pct": 0.0,
        }

        result = build_payload(raw_lines, 2000, 1000, photo)

        incline = result["quality"]["metrics"]["inclin"]
        # Should be approximately 5.7°
        assert abs(incline - angle_deg) < 1.0

    def test_build_payload_confidence_rounded(self):
        """Test that confidence values are rounded to 3 decimals."""
        raw_lines = [
            {
                "text": "ROUNDED",
                "conf": 0.123456789,
                "box": [[0, 0], [100, 0], [100, 50], [0, 50]],
            }
        ]
        photo = {
            "nitidez": 100.0,
            "brillo": 120.0,
            "contraste": 50.0,
            "lado_corto": 1000,
            "reflejo_pct": 0.0,
        }

        result = build_payload(raw_lines, 1000, 2000, photo)

        conf = result["lines"][0]["conf"]
        assert conf == 0.123


class TestProcessMenu(unittest.IsolatedAsyncioTestCase):
    """Tests for process_menu function."""

    @patch("services.menu_ocr_service.fetch_image_bytes")
    @patch("services.menu_ocr_service.decode_image")
    @patch("services.menu_ocr_service.run_ocr")
    @patch("services.menu_ocr_service.branch_menus_repo")
    async def test_process_menu_success(
        self,
        mock_repo,
        mock_ocr,
        mock_decode,
        mock_fetch,
    ):
        """Test successful menu processing."""
        # Mock image fetch
        mock_fetch.return_value = b"fake_image_data"

        # Mock decode
        mock_rgb = np.zeros((500, 800, 3), dtype=np.uint8)
        mock_decode.return_value = mock_rgb

        # Mock OCR
        mock_ocr.return_value = [
            {
                "text": "PIZZA",
                "conf": 0.95,
                "box": [[100, 100], [300, 100], [300, 200], [100, 200]],
            }
        ]

        # Mock repo
        mock_repo.set_ocr_result = AsyncMock(return_value=True)

        # Create test menu
        from bson import ObjectId

        menu = BranchMenu(
            id=ObjectId(),
            branchId=ObjectId(),
            image="s3://test-image.jpg",
            isActive=True,
            ocrStatus="processing",
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        )

        result = await process_menu(menu)

        assert result is True
        mock_fetch.assert_called_once_with("s3://test-image.jpg")
        mock_repo.set_ocr_result.assert_called_once()

    @patch("services.menu_ocr_service.fetch_image_bytes")
    @patch("services.menu_ocr_service.branch_menus_repo")
    async def test_process_menu_fetch_error(
        self,
        mock_repo,
        mock_fetch,
    ):
        """Test menu processing with S3 fetch error."""
        mock_fetch.side_effect = Exception("S3 error")
        mock_repo.set_ocr_failed = AsyncMock(return_value=True)

        from bson import ObjectId

        menu = BranchMenu(
            id=ObjectId(),
            branchId=ObjectId(),
            image="s3://missing.jpg",
            isActive=True,
            ocrStatus="processing",
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        )

        result = await process_menu(menu)

        assert result is False
        mock_repo.set_ocr_failed.assert_called_once()

    @patch("services.menu_ocr_service.fetch_image_bytes")
    @patch("services.menu_ocr_service.decode_image")
    @patch("services.menu_ocr_service.branch_menus_repo")
    async def test_process_menu_decode_error(
        self,
        mock_repo,
        mock_decode,
        mock_fetch,
    ):
        """Test menu processing with decode error."""
        mock_fetch.return_value = b"invalid_image"
        mock_decode.side_effect = ValueError("Invalid image format")
        mock_repo.set_ocr_failed = AsyncMock(return_value=True)

        from bson import ObjectId

        menu = BranchMenu(
            id=ObjectId(),
            branchId=ObjectId(),
            image="s3://bad-image.jpg",
            isActive=True,
            ocrStatus="processing",
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        )

        result = await process_menu(menu)

        assert result is False
        mock_repo.set_ocr_failed.assert_called_once()

    @patch("services.menu_ocr_service.OCR_TIMEOUT_SECONDS", 0.01)
    @patch("services.menu_ocr_service.fetch_image_bytes")
    @patch("services.menu_ocr_service.analyze_image")
    @patch("services.menu_ocr_service.branch_menus_repo")
    async def test_process_menu_ocr_timeout(self, mock_repo, mock_analyze, mock_fetch):
        """Test menu processing with OCR timeout."""
        mock_fetch.return_value = b"fake_image"
        # The real OCR is synchronous: delay its worker thread past the deadline.
        import time

        mock_analyze.side_effect = lambda data: time.sleep(0.05)

        mock_repo.set_ocr_failed = AsyncMock(return_value=True)

        from bson import ObjectId

        menu = BranchMenu(
            id=ObjectId(),
            branchId=ObjectId(),
            image="s3://timeout.jpg",
            isActive=True,
            ocrStatus="processing",
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        )

        result = await process_menu(menu)

        assert result is False
        mock_repo.set_ocr_failed.assert_awaited_once()
        assert "TimeoutError" in mock_repo.set_ocr_failed.await_args.args[2]


class TestProcessPendingMenus(unittest.IsolatedAsyncioTestCase):
    """Tests for process_pending_menus worker function."""

    @patch("services.menu_ocr_worker.branch_menus_repo")
    @patch("services.menu_ocr_worker.process_menu")
    async def test_process_pending_menus_batch_limit(
        self,
        mock_process_menu,
        mock_repo,
    ):
        """Test that batch limit is respected."""
        from bson import ObjectId

        # Create mock menus
        menus = [
            BranchMenu(
                id=ObjectId(),
                branchId=ObjectId(),
                image=f"s3://img{i}.jpg",
                isActive=True,
                ocrStatus="pending",
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow(),
            )
            for i in range(3)
        ]

        # claim_next_pending returns first 3 menus, then None
        mock_repo.claim_next_pending = AsyncMock(side_effect=menus + [None])
        mock_repo.requeue_stale_processing = AsyncMock(return_value=0)
        mock_process_menu.return_value = True

        result = await process_pending_menus(batch_limit=3)

        assert result == 3
        assert mock_repo.claim_next_pending.call_count == 3  # Exactly 3 claims (loop ends after batch_limit)

    @patch("services.menu_ocr_worker.branch_menus_repo")
    @patch("services.menu_ocr_worker.process_menu")
    async def test_process_pending_menus_no_pending(
        self,
        mock_process_menu,
        mock_repo,
    ):
        """Test when no menus are pending."""
        mock_repo.claim_next_pending = AsyncMock(return_value=None)
        mock_repo.requeue_stale_processing = AsyncMock(return_value=0)

        result = await process_pending_menus(batch_limit=5)

        assert result == 0

    @patch("services.menu_ocr_worker.branch_menus_repo")
    @patch("services.menu_ocr_worker.process_menu")
    async def test_process_pending_menus_continues_after_failure(
        self,
        mock_process_menu,
        mock_repo,
    ):
        """Test that batch continues even if one menu fails."""
        from bson import ObjectId

        menus = [
            BranchMenu(
                id=ObjectId(),
                branchId=ObjectId(),
                image=f"s3://img{i}.jpg",
                isActive=True,
                ocrStatus="pending",
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow(),
            )
            for i in range(4)
        ]

        mock_repo.claim_next_pending = AsyncMock(side_effect=menus + [None])
        mock_repo.requeue_stale_processing = AsyncMock(return_value=0)

        # Fail on second menu
        mock_process_menu.side_effect = [True, False, True, True]

        result = await process_pending_menus(batch_limit=4)

        # Should have processed 4 menus (3 successful + 1 failed)
        assert mock_process_menu.call_count == 4
        assert result == 3  # Count of successful ones


# Integration test with real RapidOCR
class TestOCRIntegration(unittest.TestCase):
    """Integration tests using real RapidOCR engine (if available)."""

    def test_ocr_real_text_detection(self):
        """Test real OCR on generated text image.

        Creates a simple image with text "PIZZA MARGARITA 8.50" and verifies
        that some detected text contains "pizza" (case-insensitive).
        """
        pytest.importorskip("rapidocr_onnxruntime")

        # Create image with text
        img = Image.new("RGB", (900, 500), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        # Use default font
        try:
            font = ImageFont.load_default(size=60)
        except TypeError:
            font = ImageFont.load_default()

        text = "PIZZA MARGARITA 8.50"
        draw.text((50, 100), text, fill=(0, 0, 0), font=font)

        # Convert to bytes
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        img_bytes = buf.getvalue()

        # Decode and run OCR
        rgb = decode_image(img_bytes)
        from services.menu_ocr_service import run_ocr

        lines = run_ocr(rgb)

        # Should have detected some text
        assert len(lines) > 0

        # At least one line should contain "pizza" (case-insensitive)
        all_text = " ".join(line["text"] for line in lines)
        assert "pizza" in all_text.lower()

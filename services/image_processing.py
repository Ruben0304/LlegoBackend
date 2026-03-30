"""Image processing service for resizing and compressing images."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import Tuple

from PIL import Image, ImageOps

# Shared thread pool for CPU-bound image processing (avoids blocking the event loop)
_image_thread_pool = ThreadPoolExecutor(max_workers=4)

# Image size configurations
IMAGE_CONFIGS = {
    "business_avatar": {"size": (400, 400), "fit": True},
    "business_cover": {"size": (1920, 1080), "fit": True},  # 16:9
    "branch_avatar": {"size": (400, 400), "fit": True},
    "branch_cover": {"size": (1920, 1080), "fit": True},  # 16:9
    "user_avatar": {"size": (400, 400), "fit": True},
}

# JPEG quality for compression (1-100)
JPEG_QUALITY = 85


def process_image_for_store(
    file_content: bytes, image_type: str, convert_to_jpg: bool = True
) -> Tuple[bytes, str]:
    """
    Process image for stores (businesses/branches).
    Converts to JPG, resizes, and compresses.

    Args:
        file_content: Raw image bytes
        image_type: One of 'business_avatar', 'business_cover', 'branch_avatar', 'branch_cover'
        convert_to_jpg: Whether to convert to JPEG format

    Returns:
        Tuple of (processed_bytes, extension)
    """
    img = Image.open(BytesIO(file_content))

    # Get target size and strategy
    config = IMAGE_CONFIGS.get(image_type, {"size": (800, 800), "fit": False})
    target_size = config["size"]
    fit_to_target = config["fit"]

    # Convert to RGB if needed (for JPEG conversion)
    if convert_to_jpg and img.mode in ("RGBA", "P", "LA"):
        # Create white background for transparent images
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        if img.mode in ("RGBA", "LA"):
            background.paste(img, mask=img.split()[-1])
            img = background
        else:
            img = img.convert("RGB")
    elif convert_to_jpg and img.mode != "RGB":
        img = img.convert("RGB")

    # Resize using center-crop fit for exact dimensions (e.g. avatars/covers).
    # This avoids white borders and guarantees the expected frontend aspect ratio.
    if fit_to_target:
        img = ImageOps.fit(
            img,
            target_size,
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
    else:
        img.thumbnail(target_size, Image.Resampling.LANCZOS)

    # Save to bytes
    output = BytesIO()
    if convert_to_jpg:
        img.save(output, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        extension = ".jpg"
    else:
        # Keep original format
        format_name = img.format or "PNG"
        img.save(output, format=format_name, optimize=True)
        extension = f".{format_name.lower()}"

    return output.getvalue(), extension


async def process_image_for_store_async(
    file_content: bytes,
    image_type: str,
    convert_to_jpg: bool = True,
) -> Tuple[bytes, str]:
    """Async wrapper — runs process_image_for_store in a thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _image_thread_pool,
        process_image_for_store,
        file_content,
        image_type,
        convert_to_jpg,
    )


async def process_product_image_async(
    file_content: bytes, original_extension: str
) -> Tuple[bytes, str]:
    """Async wrapper — runs process_product_image in a thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _image_thread_pool, process_product_image, file_content, original_extension
    )


def process_product_image(
    file_content: bytes, original_extension: str
) -> Tuple[bytes, str]:
    """
    Process product image - preserves transparency (no JPG conversion).
    Only optimizes and optionally resizes.

    Args:
        file_content: Raw image bytes
        original_extension: Original file extension (e.g., '.png')

    Returns:
        Tuple of (processed_bytes, extension)
    """
    img = Image.open(BytesIO(file_content))

    # Maximum size for product originals so alta can still be generated from source
    max_size = (1440, 1800)

    # Resize if too large
    if img.width > max_size[0] or img.height > max_size[1]:
        img.thumbnail(max_size, Image.Resampling.LANCZOS)

    # Determine output format - preserve transparency-supporting formats
    output = BytesIO()

    if original_extension.lower() in (".png", ".webp", ".gif"):
        # Preserve format that supports transparency
        if original_extension.lower() == ".png":
            img.save(output, format="PNG", optimize=True)
            extension = ".png"
        elif original_extension.lower() == ".webp":
            img.save(output, format="WEBP", quality=JPEG_QUALITY)
            extension = ".webp"
        elif original_extension.lower() == ".gif":
            img.save(output, format="GIF", optimize=True)
            extension = ".gif"
    else:
        # For other formats (jpg, etc), convert to PNG if has alpha, else keep as JPEG
        if img.mode in ("RGBA", "LA", "P"):
            img.save(output, format="PNG", optimize=True)
            extension = ".png"
        else:
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(output, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            extension = ".jpg"

    return output.getvalue(), extension

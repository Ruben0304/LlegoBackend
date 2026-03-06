"""Generate 100x100, 500x500, and 1000x1000 image variants for existing products."""

import argparse
import sys
from typing import Iterable
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clients.s3_client import get_s3_client
from core.config import settings
from utils.s3 import (
    PRODUCT_IMAGE_VARIANT_SIZES,
    SUPPORTED_IMAGE_EXTENSIONS,
    generate_image_variant,
    get_image_variant_path,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill product image variants in S3."
    )
    parser.add_argument(
        "--prefix",
        default="products/",
        help="S3 prefix to scan for product images.",
    )
    parser.add_argument(
        "--sizes",
        default="100,500,1000",
        help="Comma-separated list of variant sizes to generate.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite variants even if they already exist.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit of original images to process.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report what would be generated.",
    )
    return parser.parse_args()


def parse_sizes(raw_sizes: str) -> list[int]:
    return [int(size.strip()) for size in raw_sizes.split(",") if size.strip()]


def is_original_product_image(key: str) -> bool:
    lowered = key.lower()
    if "_thumbnail" in lowered:
        return False

    return any(lowered.endswith(extension) for extension in SUPPORTED_IMAGE_EXTENSIONS)


def object_exists(s3_client, key: str) -> bool:
    try:
        s3_client.head_object(Bucket=settings.s3_bucket_name, Key=key)
        return True
    except Exception:
        return False


def iter_original_images(s3_client, prefix: str) -> Iterable[str]:
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.s3_bucket_name, Prefix=prefix):
        for item in page.get("Contents", []):
            key = item["Key"]
            if is_original_product_image(key):
                yield key


def main() -> None:
    args = parse_args()
    sizes = parse_sizes(args.sizes) or list(PRODUCT_IMAGE_VARIANT_SIZES)
    s3_client = get_s3_client()

    processed = 0
    created = 0
    skipped = 0
    failures = 0

    print(
        f"Scanning bucket={settings.s3_bucket_name} prefix={args.prefix} sizes={sizes} force={args.force} dry_run={args.dry_run}"
    )

    for key in iter_original_images(s3_client, args.prefix):
        if args.limit is not None and processed >= args.limit:
            break

        processed += 1
        print(f"\n[{processed}] Processing {key}")

        try:
            response = s3_client.get_object(Bucket=settings.s3_bucket_name, Key=key)
            original_bytes = response["Body"].read()
        except Exception as exc:
            failures += 1
            print(f"  ✗ Failed to download original: {exc}")
            continue

        extension = "." + key.rsplit(".", 1)[-1].lower()

        for size in sizes:
            variant_key = get_image_variant_path(key, size)

            if not args.force and object_exists(s3_client, variant_key):
                skipped += 1
                print(f"  - Exists: {variant_key}")
                continue

            if args.dry_run:
                created += 1
                print(f"  · Would upload: {variant_key}")
                continue

            try:
                variant_bytes = generate_image_variant(
                    original_bytes, size=size, output_extension=extension
                )
                s3_client.put_object(
                    Bucket=settings.s3_bucket_name,
                    Key=variant_key,
                    Body=variant_bytes,
                )
                created += 1
                print(f"  ✓ Uploaded: {variant_key}")
            except Exception as exc:
                failures += 1
                print(f"  ✗ Failed for {variant_key}: {exc}")

    print(
        f"\nDone. originals={processed} uploaded={created} skipped={skipped} failures={failures}"
    )


if __name__ == "__main__":
    main()

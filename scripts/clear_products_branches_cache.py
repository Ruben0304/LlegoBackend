"""
Clear Redis cache keys for products and branches.

By default, this script targets only:
- cache:products:*
- cache:branches:*

Usage examples:
    python3 scripts/clear_products_branches_cache.py --dry-run
    python3 scripts/clear_products_branches_cache.py --yes
    REDIS_URL="redis://user:pass@host:6379/0" \
        python3 scripts/clear_products_branches_cache.py --yes
"""

import argparse
import os
import sys
from typing import Dict, List

import redis


DEFAULT_PATTERNS = ["cache:products:*", "cache:branches:*"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Delete Redis cache keys for products and branches."
    )
    parser.add_argument(
        "--redis-url",
        default=os.getenv("REDIS_URL", "redis://localhost:6379"),
        help="Redis connection URL (default: REDIS_URL env or redis://localhost:6379).",
    )
    parser.add_argument(
        "--pattern",
        action="append",
        dest="patterns",
        help="Optional key pattern to delete. Can be passed multiple times.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Delete batch size for DEL operations (default: 500).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show how many keys would be deleted without deleting them.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt.",
    )
    return parser


def scan_keys(client: redis.Redis, pattern: str) -> List[str]:
    keys: List[str] = []
    cursor = 0
    while True:
        cursor, chunk = client.scan(cursor=cursor, match=pattern, count=1000)
        if chunk:
            keys.extend(chunk)
        if cursor == 0:
            break
    return keys


def delete_in_batches(
    client: redis.Redis, keys: List[str], batch_size: int
) -> int:
    if not keys:
        return 0

    deleted = 0
    for idx in range(0, len(keys), batch_size):
        chunk = keys[idx : idx + batch_size]
        deleted += client.delete(*chunk)
    return deleted


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    patterns = args.patterns if args.patterns else DEFAULT_PATTERNS

    try:
        client = redis.from_url(args.redis_url, decode_responses=True)
        client.ping()
    except Exception as exc:
        print(f"ERROR: Could not connect to Redis: {exc}")
        return 1

    print("Redis cache cleanup")
    print(f"- Redis URL: {args.redis_url}")
    print(f"- Patterns: {patterns}")
    print(f"- Mode: {'dry-run' if args.dry_run else 'delete'}")

    all_keys: Dict[str, List[str]] = {}
    total = 0

    for pattern in patterns:
        keys = scan_keys(client, pattern)
        all_keys[pattern] = keys
        count = len(keys)
        total += count
        print(f"  {pattern}: {count} keys")

    if total == 0:
        print("No matching keys found.")
        return 0

    if args.dry_run:
        print(f"Dry-run completed. Total keys matched: {total}")
        return 0

    if not args.yes:
        confirm = input(f"Delete {total} keys? Type 'yes' to continue: ").strip()
        if confirm.lower() != "yes":
            print("Cancelled.")
            return 0

    deleted_total = 0
    for pattern, keys in all_keys.items():
        deleted = delete_in_batches(client, keys, args.batch_size)
        deleted_total += deleted
        print(f"Deleted {deleted} keys for pattern: {pattern}")

    print(f"Done. Total deleted keys: {deleted_total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

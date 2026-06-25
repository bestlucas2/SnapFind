"""Image hashing for duplicate detection.

We store a perceptual hash (phash) so near-identical re-uploads (resized,
re-compressed) are caught, plus expose an exact byte digest for callers that
want it. Duplicate checks are always scoped to a single user upstream.
"""
from __future__ import annotations

import hashlib

import imagehash
from PIL import Image


def perceptual_hash(image: Image.Image) -> str:
    """64-bit perceptual hash as a 16-char hex string."""
    return str(imagehash.phash(image))


def hamming_distance(a: str, b: str) -> int:
    """Distance between two phash hex strings (0 == identical)."""
    return imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

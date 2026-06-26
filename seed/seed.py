"""Seed a demo account with original mock screenshots.

Each image is generated with PIL (no copyright / personal data), then run through
the *real* OCR/hash/tag/categorise pipeline — exactly what a normal upload does.
A JSON manifest of precomputed text + tags is written alongside and used as a
fallback so the demo still populates if Tesseract isn't installed.

Run:  python -m seed.seed            (skips if the demo already has screenshots)
      python -m seed.seed --force    (wipe demo screenshots and reseed)
"""
from __future__ import annotations

import io
import json
import sys
from datetime import timedelta

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import func, select

from auth import hash_password
from config import BASE_DIR
from database import SessionLocal, init_db
from models import Collection, Screenshot, User
from services import processing
from services.hashing import perceptual_hash
from utils.files import dimensions_from_bytes, make_thumbnail, remove_relpath, save_upload
from utils.timeutils import utcnow

DEMO_EMAIL = "demo@snapfind.app"
DEMO_PASSWORD = "demo1234"
SEED_IMAGE_DIR = BASE_DIR / "seed" / "images"
MANIFEST_PATH = BASE_DIR / "seed" / "manifest.json"

DEFAULT_COLLECTIONS = ["School", "Projects", "Receipts", "Recipes", "Shopping"]

FONT_PATHS = [
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]

# Each spec renders to one mock screenshot. accent = top-bar colour.
SPECS = [
    {
        "slug": "grocery-receipt", "title": "Grocery receipt",
        "category": "Receipts", "collection": "Receipts",
        "accent": (22, 163, 74), "favorite": True, "days_ago": 1,
        "tags": ["receipt", "groceries", "food"],
        "lines": [
            "WHOLE FOODS MARKET", "123 Main Street",
            "Bananas          $1.29", "Almond Milk      $3.49",
            "Sourdough Bread  $4.99", "Eggs (dozen)     $5.29",
            "Subtotal         $15.06", "Tax              $1.20",
            "TOTAL            $16.26", "VISA ****1234  APPROVED",
        ],
    },
    {
        "slug": "python-traceback", "title": "Python traceback",
        "category": "Code", "collection": "Projects",
        "accent": (51, 65, 85), "days_ago": 2,
        "tags": ["python", "error", "bug"],
        "lines": [
            "Traceback (most recent call last):",
            '  File "app.py", line 42, in <module>',
            "    main()",
            '  File "app.py", line 30, in main',
            "    return user.id",
            "AttributeError: 'NoneType' object",
            "has no attribute 'id'",
        ],
    },
    {
        "slug": "react-component", "title": "React component",
        "category": "Code", "collection": "Projects",
        "accent": (79, 70, 229), "days_ago": 3,
        "tags": ["react", "javascript", "frontend"],
        "lines": [
            "import React, { useState } from 'react';",
            "export default function Card() {",
            "  const [open, setOpen] = useState(false);",
            "  return (",
            '    <div className="card">',
            "      <button onClick={() => setOpen(!open)}>",
            "    </div>",
            "  );",
            "}",
        ],
    },
    {
        "slug": "chat-with-alex", "title": "Chat with Alex",
        "category": "Chats", "collection": None,
        "accent": (37, 99, 235), "favorite": True, "days_ago": 0, "hours_ago": 3,
        "tags": ["chat", "lunch", "alex"],
        "lines": [
            "Alex             10:24 AM",
            "Are we still on for lunch today?",
            "",
            "You              10:25 AM",
            "Yes! Noon at the cafe on 5th",
            "Delivered",
            "",
            "Alex is typing...",
        ],
    },
    {
        "slug": "shopping-cart", "title": "Shopping cart",
        "category": "Shopping", "collection": "Shopping",
        "accent": (234, 88, 12), "days_ago": 4,
        "tags": ["shopping", "checkout", "electronics"],
        "lines": [
            "Your Cart (2 items)",
            "Wireless Headphones",
            "$79.99    Qty: 1",
            "USB-C Cable 2m",
            "$12.49    Qty: 2",
            "Subtotal: $104.97",
            "Free shipping on orders over $35",
            "Proceed to checkout",
        ],
    },
    {
        "slug": "lecture-notes", "title": "Lecture 5 notes",
        "category": "School", "collection": "School",
        "accent": (147, 51, 234), "days_ago": 6,
        "tags": ["school", "cs101", "notes"],
        "lines": [
            "CS 101 - Lecture 5",
            "Topic: Binary Search Trees",
            "- O(log n) average lookup time",
            "- Inorder traversal yields sorted order",
            "- Balancing keeps height logarithmic",
            "Assignment 3 due Friday",
            "Read chapter 7 before the exam",
        ],
    },
    {
        "slug": "pasta-recipe", "title": "Creamy garlic pasta",
        "category": "Miscellaneous", "collection": "Recipes",
        "accent": (220, 38, 38), "days_ago": 8,
        "tags": ["recipe", "pasta", "dinner"],
        "lines": [
            "Creamy Garlic Pasta",
            "Ingredients:",
            "- 400g spaghetti",
            "- 3 cloves garlic, minced",
            "- 1 cup heavy cream",
            "- Parmesan cheese",
            "Boil pasta for 9 minutes",
            "Serves 4 people",
        ],
    },
    {
        "slug": "flight-confirmation", "title": "Flight confirmation",
        "category": "Miscellaneous", "collection": None,
        "accent": (13, 148, 136), "days_ago": 12,
        "tags": ["flight", "travel", "booking"],
        "lines": [
            "Booking Confirmed",
            "Flight UA 482",
            "SFO  ->  JFK",
            "Dec 14, 2026   8:15 AM",
            "Seat 14C   Boarding Group 2",
            "Confirmation: XR7K9P",
        ],
    },
    {
        "slug": "wifi-password", "title": "Cafe WiFi details",
        "category": "Miscellaneous", "collection": None,
        "accent": (100, 116, 139), "days_ago": 20,
        "tags": ["wifi", "password", "cafe"],
        "lines": [
            "Guest WiFi Access",
            "Network: CafeGuest",
            "Password: latte2026",
            "Enjoy your stay!",
        ],
    },
    {
        "slug": "invoice-1042", "title": "Invoice #1042",
        "category": "Receipts", "collection": "Receipts",
        "accent": (22, 163, 74), "days_ago": 30,
        "tags": ["invoice", "work", "client"],
        "lines": [
            "INVOICE #1042",
            "Acme Design Co.",
            "Web design services",
            "Hours: 12 x $85.00",
            "Subtotal: $1020.00",
            "Tax (8%): $81.60",
            "Total Due: $1101.60",
            "Due: Jan 15, 2026",
        ],
    },
]


def get_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size)  # Pillow >= 10.1 scales the builtin
    except Exception:
        return ImageFont.load_default()


def render(spec: dict) -> Image.Image:
    width, height = 960, 640
    img = Image.new("RGB", (width, height), (250, 250, 250))
    draw = ImageDraw.Draw(img)

    # Window chrome / title bar.
    draw.rectangle([0, 0, width, 70], fill=spec["accent"])
    for i, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        draw.ellipse([24 + i * 26, 28, 40 + i * 26, 44], fill=color)
    draw.text((110, 24), spec["title"], font=get_font(28), fill=(255, 255, 255))

    # Body text.
    body = get_font(26)
    y = 104
    for line in spec["lines"]:
        draw.text((40, y), line, font=body, fill=(23, 23, 23))
        y += 42
    return img


def main() -> None:
    force = "--force" in sys.argv
    init_db()
    SEED_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        user = db.execute(
            select(User).where(User.email == DEMO_EMAIL)
        ).scalar_one_or_none()
        if user is None:
            user = User(
                email=DEMO_EMAIL,
                password_hash=hash_password(DEMO_PASSWORD),
                display_name="Demo User",
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        existing_names = {
            c.name
            for c in db.execute(
                select(Collection).where(Collection.user_id == user.id)
            ).scalars()
        }
        for name in DEFAULT_COLLECTIONS:
            if name not in existing_names:
                db.add(Collection(user_id=user.id, name=name))
        db.commit()
        collections = {
            c.name: c
            for c in db.execute(
                select(Collection).where(Collection.user_id == user.id)
            ).scalars()
        }

        count = db.scalar(
            select(func.count(Screenshot.id)).where(Screenshot.user_id == user.id)
        )
        if count and not force:
            print(f"Demo user already has {count} screenshots. Use --force to reseed.")
            return
        if count and force:
            for shot in db.execute(
                select(Screenshot).where(Screenshot.user_id == user.id)
            ).scalars():
                remove_relpath(shot.storage_relpath)
                remove_relpath(shot.thumb_relpath)
                db.delete(shot)
            db.commit()

        manifest: dict[str, dict] = {}
        for spec in SPECS:
            image = render(spec)
            image.save(SEED_IMAGE_DIR / f"{spec['slug']}.png", "PNG")

            buf = io.BytesIO()
            image.save(buf, "PNG")
            data = buf.getvalue()

            stored = save_upload(user.id, data, ".png")
            width, height = dimensions_from_bytes(data)
            thumb = make_thumbnail(user.id, stored, data)

            shot = Screenshot(
                user_id=user.id,
                filename=spec["title"],
                original_filename=f"{spec['slug']}.png",
                stored_filename=stored,
                thumb_filename=thumb,
                content_type="image/png",
                file_size=len(data),
                width=width,
                height=height,
                image_hash=perceptual_hash(image),
                favorite=spec.get("favorite", False),
            )
            coll = collections.get(spec.get("collection"))
            if coll is not None:
                shot.collection_id = coll.id
            shot.created_at = utcnow() - timedelta(
                days=spec.get("days_ago", 0), hours=spec.get("hours_ago", 0)
            )
            db.add(shot)
            db.flush()

            fallback = {
                "text": "\n".join(spec["lines"]),
                "category": spec["category"],
            }
            manifest[spec["slug"]] = {**fallback, "tags": spec["tags"]}
            # Attach the demo's specified tags (capped at MAX_TAGS). Tags are no
            # longer auto-generated by the OCR pipeline.
            processing.attach_tags(db, shot, spec["tags"], auto=True)
            # Real pipeline first; manifest text is used only if OCR is unavailable.
            processing.process_screenshot(db, shot, fallback=fallback, commit=False)

        db.commit()
        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        print("-" * 52)
        print(f"  Seeded {len(SPECS)} screenshots for the demo account.")
        print(f"  Email:    {DEMO_EMAIL}")
        print(f"  Password: {DEMO_PASSWORD}")
        print("-" * 52)
    finally:
        db.close()


if __name__ == "__main__":
    main()

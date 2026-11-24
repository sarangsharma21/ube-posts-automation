"""
Automatic Content-Based Caption & Hashtag Generator for Ube Culture

Generates human-sounding Instagram captions, alt text, and 4-5 targeted hashtags
from the actual image content:
1. If GEMINI_API_KEY is set (free Google AI Studio tier), uses Gemini Vision REST API
   to inspect the image pixels & on-image text directly.
2. Otherwise (zero-key 100% free default), extracts printed text from the image via
   Tesseract OCR (if installed) + analyzes filename/topic cues to craft a tailored,
   content-matched caption and hashtags.
"""

import base64
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import requests

GEMINI_MODEL = os.getenv("GEMINI_VISION_MODEL", "gemini-2.5-flash")

TOPIC_RULES = [
    (["latte", "espresso", "coffee", "barista", "pour", "foam", "cloud"],
     "latte", ["#UbeLatte", "#IcedUbeLatte", "#BaristaIndia", "#CafeMenu"]),
    (["matcha"],
     "matcha", ["#UbeMatcha", "#MatchaLatte", "#CafeDrinks", "#SpecialtyDrinks"]),
    (["boba", "tapioca", "milkshake", "shake", "smoothie", "protein"],
     "beverage", ["#UbeMilkTea", "#UbeDrinks", "#CafeBeverages", "#PurpleDrink"]),
    (["pancake", "waffle", "french toast", "oats", "bowl", "breakfast", "brunch"],
     "brunch", ["#UbeBrunch", "#BrunchMenu", "#CafeFood", "#HealthyBreakfast"]),
    (["cheesecake", "tiramisu", "croissant", "brownie", "macaron", "chiffon", "cinnamon", "cookie", "parfait", "bak", "pastry", "gelato", "popsicle", "cream"],
     "pastry", ["#UbeDessert", "#BakeryIndia", "#PastryChef", "#BakingWithUbe"]),
    (["wholesale", "b2b", "horeca", "cafe", "starter", "shipping", "pincode", "vault", "flight"],
     "b2b", ["#B2BCafe", "#CafeSupplyIndia", "#HoReCaIndia", "#SpecialtyCoffeeIndia"]),
    (["myth", "vs", "taro", "sweet potato", "gluten", "nutrient", "antioxidant", "immunity", "caffeine", "dosage", "ratio", "storage", "dye", "synthetic", "faq", "history", "eco", "farming", "philippine"],
     "education", ["#WhatIsUbe", "#RealUbe", "#PhilippineUbe", "#CleanIngredients"]),
]


def extract_ocr_text(image_path: Path) -> str:
    """Extract on-image text using local tesseract binary if available."""
    tesseract_bin = shutil.which("tesseract")
    if not tesseract_bin:
        return ""
    try:
        proc = subprocess.run(
            [tesseract_bin, str(image_path), "stdout", "--psm", "6"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if proc.returncode == 0:
            lines = [ln.strip() for ln in proc.stdout.splitlines() if len(ln.strip()) > 2]
            return " ".join(lines)[:600]
    except Exception:
        pass
    return ""


def clean_topic_from_filename(image_path: Path) -> str:
    stem = re.sub(r"^UbeCulture_Post_\d+_", "", image_path.stem)
    words = re.sub(r"([a-z])([A-Z])", r"\1 \2", stem).replace("_", " ")
    return words.strip()


def generate_with_gemini(image_path: Path, api_key: str) -> Optional[dict[str, str]]:
    """Use Gemini Vision REST API (free AI Studio key) to caption directly from image pixels."""
    img_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    prompt = (
        "You are writing an Instagram feed caption for @ubeculture (India's direct importer of "
        "100% pure Philippine purple yam / ube powder for cafes, bakeries, and home kitchens).\n"
        "Look closely at this post image (its headline, recipe/facts, and visuals) and return JSON ONLY "
        'with keys "caption" and "alt_text".\n'
        "Rules for caption:\n"
        "- Line 1: crisp hook under 120 chars based on what is shown in the image (no greeting, no starting emoji).\n"
        "- Body: 1-2 short paragraphs referencing specific details/ingredients/tips visible in the image.\n"
        "- End with ONE clear ask (e.g. Save this post, Comment SAMPLE, or DM CAFE).\n"
        "- Finish with 4 specific hashtags on their own line (include #UbeCulture, never #viral or #fyp).\n"
        "- Never use em dashes or buzzwords like delve, elevate, game-changer, unlock, unleash.\n"
        "- Never include URLs in the caption."
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    resp = requests.post(
        url,
        params={"key": api_key},
        json={
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}},
                ]
            }],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.6},
        },
        timeout=45,
    )
    if not resp.ok:
        print(f"[auto_caption] Gemini API warning ({resp.status_code}): {resp.text[:200]}")
        return None
    try:
        raw_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(raw_text)
        if parsed.get("caption"):
            return {
                "caption": parsed["caption"].strip(),
                "alt_text": parsed.get("alt_text", "").strip(),
            }
    except Exception as exc:
        print(f"[auto_caption] Gemini parse warning: {exc}")
    return None


def generate_with_ocr_rules(image_path: Path) -> dict[str, str]:
    """Zero-key fallback: reads text inside the image via OCR + filename topic rules."""
    topic_label = clean_topic_from_filename(image_path)
    ocr_text = extract_ocr_text(image_path)
    combined = f"{topic_label} {ocr_text}".lower()

    matched_category = "general"
    extra_tags = ["#UbePowder", "#PhilippineUbe", "#RealUbe"]
    for keywords, category, tags in TOPIC_RULES:
        if any(kw in combined for kw in keywords):
            matched_category = category
            extra_tags = tags
            break

    hashtags = ["#UbeCulture"]
    for t in extra_tags:
        if t not in hashtags:
            hashtags.append(t)
        if len(hashtags) == 4:
            break

    snippet = ""
    if ocr_text:
        clean_ocr = re.sub(r"\s+", " ", ocr_text).strip()
        # Keep a concise readable line from OCR if it looks clean
        words = [w for w in clean_ocr.split() if len(w) <= 22]
        if len(words) >= 4:
            snippet = " ".join(words[:18]).rstrip(".,;:") + "."

    if matched_category == "b2b":
        hook = f"{topic_label} built for cafes, bakeries, and cloud kitchens."
        body = (
            "100% pure stone-milled Philippine ube powder dissolves smoothly in hot or cold bases "
            "with zero artificial dyes or added sugar."
        )
        cta = "Comment CATALOGUE or DM us CAFE for wholesale pricing and sample packs."
    elif matched_category == "education":
        hook = f"{topic_label}: what actually goes into real Philippine ube."
        body = (
            f"{snippet} " if snippet else ""
        ) + "Pure Dioscorea alata gets its deep violet colour from natural plant anthocyanins with a warm vanilla-nut finish."
        cta = "Save this post for your kitchen and ingredient reference."
    elif matched_category in ("latte", "matcha", "beverage"):
        hook = f"{topic_label} made with 100% pure Philippine ube powder."
        body = (
            f"{snippet} " if snippet else ""
        ) + "Whisk 1 tsp Ube Culture powder in warm water first, then pour over milk or espresso for clean colour and creamy depth."
        cta = "Save this drink idea for your next bar prep."
    elif matched_category in ("pastry", "brunch"):
        hook = f"{topic_label} with real purple yam flavour and zero food dye."
        body = (
            f"{snippet} " if snippet else ""
        ) + "Stone-milled Philippine ube blends smoothly into batters, creams, and frostings while holding its natural violet hue."
        cta = "Save this recipe inspiration for your next bake."
    else:
        hook = f"{topic_label} with 100% pure Philippine ube powder."
        body = (
            "Single-origin purple yam milled fine for lattes, pastries, gelato, and everyday kitchen pours with zero artificial colours."
        )
        cta = "Comment SAMPLE if you want to try our 100g or B2B barista packs."

    caption = f"{hook}\n\n{body}\n\n{cta}\n\n{' '.join(hashtags)}"
    alt_text = f"Ube Culture Instagram graphic featuring {topic_label} made with pure Philippine ube powder."
    return {"caption": caption, "alt_text": alt_text}


def generate_caption_for_image(image_path: Path) -> dict[str, str]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if api_key:
        result = generate_with_gemini(image_path, api_key)
        if result:
            return result
    return generate_with_ocr_rules(image_path)

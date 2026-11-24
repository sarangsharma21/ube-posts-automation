"""
Prepare raw post images in posts/raw/ into Instagram Graph API-compliant JPEGs in posts/ready/.

Meta's Instagram Graph API requires:
- Format: JPEG (PNG/WebP are rejected with HTTP 400)
- Color space: sRGB (RGB)
- File size: <= 8 MB
- Width: 320 px to 1440 px
- Aspect ratio (width / height): between 0.8 (4:5) and 1.91 (1.91:1)
"""

from pathlib import Path
from PIL import Image, ImageOps

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "posts" / "raw"
READY_DIR = BASE_DIR / "posts" / "ready"

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
MIN_ASPECT = 0.80
MAX_ASPECT = 1.91
MAX_WIDTH = 1440
MIN_WIDTH = 320
MAX_BYTES = 8 * 1024 * 1024
BRAND_PURPLE = (62, 30, 90)  # #3E1E5A


def to_rgb(img: Image.Image) -> Image.Image:
    """Flatten transparency onto brand purple and convert to sRGB."""
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, BRAND_PURPLE)
        bg.paste(rgba, mask=rgba.split()[3])
        return bg
    return img.convert("RGB")


def enforce_aspect_and_size(img: Image.Image) -> Image.Image:
    """Pad to valid Instagram aspect ratio [0.8, 1.91] if needed, and clamp width."""
    w, h = img.size
    ratio = w / h

    if ratio < MIN_ASPECT:
        target_w = int(round(h * MIN_ASPECT))
        canvas = Image.new("RGB", (target_w, h), BRAND_PURPLE)
        canvas.paste(img, ((target_w - w) // 2, 0))
        img = canvas
    elif ratio > MAX_ASPECT:
        target_h = int(round(w / MAX_ASPECT))
        canvas = Image.new("RGB", (w, target_h), BRAND_PURPLE)
        canvas.paste(img, (0, (target_h - h) // 2))
        img = canvas

    w, h = img.size
    if w > MAX_WIDTH:
        new_h = int(round(h * (MAX_WIDTH / w)))
        img = img.resize((MAX_WIDTH, new_h), Image.Resampling.LANCZOS)
    elif w < MIN_WIDTH:
        new_h = int(round(h * (MIN_WIDTH / w)))
        img = img.resize((MIN_WIDTH, new_h), Image.Resampling.LANCZOS)

    return img


def save_compliant_jpeg(src_path: Path, dst_path: Path) -> tuple[tuple[int, int], int]:
    """Convert src_path to a compliant JPEG at dst_path and return (size, bytes)."""
    with Image.open(src_path) as raw:
        img = enforce_aspect_and_size(to_rgb(raw))

    quality = 92
    while quality >= 70:
        img.save(dst_path, format="JPEG", quality=quality, optimize=True, progressive=False)
        size_bytes = dst_path.stat().st_size
        if size_bytes <= MAX_BYTES:
            return img.size, size_bytes
        quality -= 5

    raise ValueError(f"{src_path.name} exceeds 8 MB even at quality=70")


def main() -> None:
    READY_DIR.mkdir(parents=True, exist_ok=True)
    raw_files = sorted(
        p for p in RAW_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    )
    if not raw_files:
        print(f"No supported images found in {RAW_DIR}")
        return

    for src in raw_files:
        dst = READY_DIR / f"{src.stem}.jpg"
        dims, size_bytes = save_compliant_jpeg(src, dst)
        print(f"[OK] {src.name} -> {dst.name} ({dims[0]}x{dims[1]}, {size_bytes // 1024} KB)")


if __name__ == "__main__":
    main()

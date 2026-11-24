"""
Ube Culture 100% Free Autonomous Instagram Posting Agent

Publishes the next scheduled/pending post from queue.json to an Instagram
Professional (Business/Creator) account using the official Instagram Graph API
and GitHub Actions (free tier).

Image hosting options (both 100% free):
1. GitHub Raw URL (default when repository is public - zero extra accounts)
2. Cloudinary Free Tier (set CLOUDINARY_CLOUD_NAME + CLOUDINARY_UPLOAD_PRESET
   if you prefer to keep your GitHub repository private)
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent
QUEUE_FILE = BASE_DIR / os.getenv("QUEUE_FILE", "queue.json")
API_VERSION = os.getenv("IG_API_VERSION", "v21.0")
CONTAINER_POLL_SECONDS = 5
CONTAINER_MAX_WAIT_SECONDS = 90


def load_queue(queue_path: Path) -> list[dict[str, Any]]:
    if not queue_path.exists():
        raise FileNotFoundError(f"Queue file not found: {queue_path}")
    with open(queue_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_queue(queue_path: Path, queue: list[dict[str, Any]]) -> None:
    with open(queue_path, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2, ensure_ascii=False)
        f.write("\n")


def resolve_api_host(access_token: str) -> str:
    explicit = os.getenv("IG_API_HOST", "").strip()
    if explicit:
        return explicit.rstrip("/")
    # Facebook Page / System User tokens start with "EAA..." and use graph.facebook.com;
    # Instagram Business Login tokens start with "IG..." and use graph.instagram.com.
    if access_token.startswith("EAA"):
        return "https://graph.facebook.com"
    return "https://graph.instagram.com"


def validate_jpeg(image_path: Path) -> tuple[int, int, int]:
    if not image_path.exists():
        raise FileNotFoundError(f"Post image missing: {image_path}")
    size_bytes = image_path.stat().st_size
    if size_bytes > 8 * 1024 * 1024:
        raise ValueError(f"{image_path.name} is {size_bytes} bytes (max 8 MB)")

    with Image.open(image_path) as img:
        if img.format != "JPEG":
            raise ValueError(
                f"{image_path.name} has format {img.format}, but Instagram Graph API requires JPEG. "
                "Run `python prepare_images.py` first."
            )
        w, h = img.size
        ratio = w / h
        if not (0.80 <= ratio <= 1.91):
            raise ValueError(
                f"{image_path.name} aspect ratio {ratio:.2f} is outside [0.80, 1.91]. "
                "Run `python prepare_images.py` first."
            )
    return w, h, size_bytes


def is_due(item: dict[str, Any], now_utc: datetime) -> bool:
    if item.get("status") != "pending":
        return False
    sched = (item.get("scheduled_for") or "").strip()
    if not sched:
        return True
    parsed = datetime.fromisoformat(sched.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed <= now_utc


def select_next_post(
    queue: list[dict[str, Any]], post_id: Optional[str] = None
) -> Optional[dict[str, Any]]:
    if post_id:
        for item in queue:
            if item.get("id") == post_id:
                return item
        raise ValueError(f"Post id '{post_id}' not found in queue.json")

    now_utc = datetime.now(timezone.utc)
    for item in queue:
        if is_due(item, now_utc):
            return item
    return None


def upload_to_cloudinary(image_path: Path, cloud_name: str, upload_preset: str) -> str:
    url = f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"
    with open(image_path, "rb") as f:
        resp = requests.post(
            url,
            data={"upload_preset": upload_preset},
            files={"file": (image_path.name, f, "image/jpeg")},
            timeout=60,
        )
    resp.raise_for_status()
    data = resp.json()
    return data["secure_url"]


def build_public_image_url(rel_path: str, abs_path: Path) -> str:
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
    upload_preset = os.getenv("CLOUDINARY_UPLOAD_PRESET", "").strip()
    if cloud_name and upload_preset:
        print(f"Uploading {abs_path.name} to Cloudinary free tier...")
        return upload_to_cloudinary(abs_path, cloud_name, upload_preset)

    base_url = os.getenv("PUBLIC_MEDIA_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        gh_repo = os.getenv("GITHUB_REPOSITORY", "").strip()
        gh_branch = os.getenv("GITHUB_REF_NAME", "main").strip() or "main"
        if gh_repo:
            base_url = f"https://raw.githubusercontent.com/{gh_repo}/{gh_branch}"

    if not base_url:
        raise RuntimeError(
            "Cannot build public HTTPS image URL. Set GITHUB_REPOSITORY (automatic in GitHub Actions), "
            "PUBLIC_MEDIA_BASE_URL, or CLOUDINARY_CLOUD_NAME + CLOUDINARY_UPLOAD_PRESET."
        )

    clean_rel = rel_path.replace("\\", "/").lstrip("/")
    public_url = f"{base_url}/{clean_rel}"

    probe = requests.head(public_url, allow_redirects=True, timeout=20)
    if probe.status_code != 200:
        raise RuntimeError(
            f"Public image URL returned HTTP {probe.status_code}: {public_url}\n"
            "If your GitHub repo is PRIVATE, raw.githubusercontent.com is blocked for Meta's servers. "
            "Either make the repository Public (tokens remain hidden in GitHub Secrets) or configure "
            "free Cloudinary secrets (CLOUDINARY_CLOUD_NAME + CLOUDINARY_UPLOAD_PRESET)."
        )
    return public_url


def wait_for_container(
    api_host: str, creation_id: str, access_token: str
) -> None:
    deadline = time.time() + CONTAINER_MAX_WAIT_SECONDS
    url = f"{api_host}/{API_VERSION}/{creation_id}"
    while time.time() < deadline:
        resp = requests.get(
            url,
            params={"fields": "status_code,status", "access_token": access_token},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        status_code = payload.get("status_code", "")
        if status_code == "FINISHED":
            return
        if status_code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Media container failed: {payload}")
        time.sleep(CONTAINER_POLL_SECONDS)
    raise TimeoutError(f"Timed out waiting for container {creation_id} to finish.")


def publish_to_instagram(
    ig_user_id: str,
    access_token: str,
    image_url: str,
    caption: str,
    alt_text: str = "",
) -> str:
    api_host = resolve_api_host(access_token)

    create_params: dict[str, str] = {
        "image_url": image_url,
        "caption": caption,
        "access_token": access_token,
    }
    if alt_text:
        create_params["alt_text"] = alt_text

    print(f"Creating Instagram media container via {api_host}/{API_VERSION}...")
    create_resp = requests.post(
        f"{api_host}/{API_VERSION}/{ig_user_id}/media",
        data=create_params,
        timeout=45,
    )
    if not create_resp.ok:
        raise RuntimeError(f"Container creation failed ({create_resp.status_code}): {create_resp.text}")

    creation_id = create_resp.json()["id"]
    print(f"Container created: {creation_id}. Waiting for Meta processing...")
    wait_for_container(api_host, creation_id, access_token)

    print("Publishing container to feed...")
    publish_resp = requests.post(
        f"{api_host}/{API_VERSION}/{ig_user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": access_token},
        timeout=45,
    )
    if not publish_resp.ok:
        raise RuntimeError(f"Media publish failed ({publish_resp.status_code}): {publish_resp.text}")

    media_id = publish_resp.json()["id"]
    print(f"[SUCCESS] Published Instagram post ID: {media_id}")
    return media_id


def refresh_ig_login_token(access_token: str) -> None:
    """Refresh a long-lived graph.instagram.com token (valid 60 days)."""
    if access_token.startswith("EAA"):
        print("Facebook Login tokens (EAA...) cannot be refreshed via ig_refresh_token.")
        return
    resp = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": access_token},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    expires_days = int(data.get("expires_in", 0)) // 86400
    print(f"Token refreshed successfully. Valid for ~{expires_days} days.")


def verify_credentials(ig_user_id: str, access_token: str) -> None:
    api_host = resolve_api_host(access_token)
    resp = requests.get(
        f"{api_host}/{API_VERSION}/{ig_user_id}",
        params={"fields": "id,username", "access_token": access_token},
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"Credential check failed ({resp.status_code}): {resp.text}")
    info = resp.json()
    print(f"Verified Instagram account: @{info.get('username', '?')} (id={info.get('id', ig_user_id)}) via {api_host}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Ube Culture Instagram Auto-Publisher")
    parser.add_argument("--dry-run", action="store_true", help="Validate queue and image without posting")
    parser.add_argument("--post-id", default="", help="Optional specific post id from queue.json")
    parser.add_argument("--refresh-token", action="store_true", help="Refresh long-lived Instagram token")
    args = parser.parse_args()

    access_token = os.getenv("IG_ACCESS_TOKEN", "").strip()
    ig_user_id = os.getenv("IG_USER_ID", "").strip()

    if args.refresh_token:
        if not access_token:
            print("ERROR: IG_ACCESS_TOKEN is required for --refresh-token", file=sys.stderr)
            return 1
        refresh_ig_login_token(access_token)
        return 0

    queue = load_queue(QUEUE_FILE)
    post = select_next_post(queue, args.post_id or None)
    if not post:
        print("No pending due posts in queue.json. Nothing to publish today.")
        return 0

    rel_image = post["image"]
    abs_image = BASE_DIR / rel_image
    w, h, size_bytes = validate_jpeg(abs_image)

    print("=" * 64)
    print(f"Selected post : {post['id']}")
    print(f"Image file    : {rel_image} ({w}x{h}, {size_bytes // 1024} KB, JPEG)")
    print(f"Caption preview:\n{post['caption']}\n")
    print("=" * 64)

    if args.dry_run:
        if os.getenv("GITHUB_REPOSITORY") or os.getenv("PUBLIC_MEDIA_BASE_URL"):
            url = build_public_image_url(rel_image, abs_image)
            print(f"Verified public image URL: {url}")
        if ig_user_id and access_token:
            verify_credentials(ig_user_id, access_token)
        print("[DRY RUN] Validation passed. No post was published and queue.json was not modified.")
        return 0

    if not ig_user_id or not access_token:
        print(
            "ERROR: Missing IG_USER_ID or IG_ACCESS_TOKEN environment variables / GitHub Secrets.",
            file=sys.stderr,
        )
        return 1

    image_url = build_public_image_url(rel_image, abs_image)
    media_id = publish_to_instagram(
        ig_user_id=ig_user_id,
        access_token=access_token,
        image_url=image_url,
        caption=post["caption"],
        alt_text=post.get("alt_text", ""),
    )

    post["status"] = "published"
    post["published_at"] = datetime.now(timezone.utc).isoformat()
    post["ig_media_id"] = media_id
    save_queue(QUEUE_FILE, queue)
    print("Updated queue.json with published status.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

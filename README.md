# Ube Culture — 100% Free Automated Instagram Posting Agent

Publishes scheduled posts from `queue.json` to **@ubeculture** automatically using **100% free** tools:
- **GitHub Actions** (2,000 free cloud runner minutes/month — runs even when your PC is off)
- **Official Instagram Graph API** (Meta's official API — zero ban/bot risk)
- **Pillow JPEG Converter** (`prepare_images.py` converts PNGs to compliant sRGB JPEGs automatically)
- **Free Image Hosting** via either:
  - **Public GitHub Repo** (`raw.githubusercontent.com` — zero extra accounts; your tokens stay hidden in GitHub Secrets), **or**
  - **Cloudinary Free Tier** (optional, if you want to keep your GitHub repo Private)

---

## Project Structure

- `posts/raw/` — Drop your raw `.png` / `.jpg` designs here (already loaded with all 50 Ube Culture posts).
- `posts/ready/` — Auto-generated Instagram-compliant JPEGs (`prepare_images.py`).
- `queue.json` — Ordered queue of posts, captions, alt text, optional `scheduled_for` ISO dates, and publish status.
- `auto_caption.py` — Automatically reads the content inside any newly dropped post image (via Gemini Vision if `GEMINI_API_KEY` is set, or free Tesseract OCR + topic rules otherwise) to generate tailored captions, alt text, and hashtags.
- `publish_agent.py` — Auto-discovers new images, generates missing captions/hashtags, validates JPEGs, publishes via Instagram Graph API, and updates `queue.json`.
- `.github/workflows/autopost.yml` — Runs daily at **7:00 PM IST (13:30 UTC)** and supports 1-click manual runs & dry-runs.

---

## 100% Free Setup Guide

### Step 1: Make Sure Your Instagram Account is Professional
1. On Instagram, switch `@ubeculture` to a **Business** or **Creator** account (free).
2. Link it to a Facebook Page (recommended if you want a **never-expiring** token via Meta Business Portfolio, or use Instagram Business Login directly for a 60-day token).

### Step 2: Get Your Free `IG_USER_ID` & `IG_ACCESS_TOKEN`
1. Go to [Meta for Developers](https://developers.facebook.com/) (free) and click **Create App** → choose **Other** → **Business** (or **Instagram** API setup).
2. Add the **Instagram** product (**API setup with Instagram login** or **Instagram Graph API**).
3. Grant permissions:
   - `instagram_business_basic`
   - `instagram_business_content_publish`
   *(If using Facebook Login: `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`)*
4. Generate a **User Access Token** and note your **Instagram Account ID** (`IG_USER_ID`).
   - *Tip:* In Meta Business Settings → System Users, you can generate a **never-expiring System User token** for free so you don't have to refresh every 60 days.

### Step 3: Push This Folder to GitHub
1. Create a new GitHub repository (e.g., `ube-posts-automation`).
   - **Easiest free option:** Make the repository **Public** so `raw.githubusercontent.com` serves your `posts/ready/*.jpg` images directly to Meta for free. *(Your `IG_ACCESS_TOKEN` and `IG_USER_ID` are stored in encrypted GitHub Secrets — never in the code.)*
   - **Private repo option:** Keep the repo **Private**, create a free [Cloudinary](https://cloudinary.com/) account, create an **Unsigned Upload Preset**, and add `CLOUDINARY_CLOUD_NAME` and `CLOUDINARY_UPLOAD_PRESET` to GitHub Secrets.
2. Upload/push all files in this folder (including `.github/workflows/autopost.yml`).

### Step 4: Add GitHub Secrets
In your GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**:
- `IG_USER_ID` — your numeric Instagram Business/Creator User ID
- `IG_ACCESS_TOKEN` — your long-lived Instagram or System User Access Token
- *(Optional, free)* `GEMINI_API_KEY` — free Google AI Studio key for AI vision captioning of future newly added images (if omitted, built-in Tesseract OCR auto-captioning runs for free)
- *(Optional, only for Private repos)* `CLOUDINARY_CLOUD_NAME` and `CLOUDINARY_UPLOAD_PRESET`

### Step 5: Test Before Going Live
1. Open the **Actions** tab in your GitHub repository → **Ube Culture Instagram Auto-Poster** → **Run workflow**.
2. Leave `dry_run = true` first to verify everything passes.
3. Run once with `dry_run = false` to publish your first post, then let the daily `7:00 PM IST` schedule handle the rest automatically!

---

## Local Commands

```powershell
# Convert any new PNG/JPG files in posts/raw/ into posts/ready/
python prepare_images.py

# Validate the next post without calling Instagram
python publish_agent.py --dry-run

# Validate a specific post ID
python publish_agent.py --dry-run --post-id post_06
```

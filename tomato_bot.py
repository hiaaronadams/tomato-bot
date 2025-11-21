# tomato_bot.py — FINAL VERSION

import os
import json
import random
import textwrap
from typing import Optional, Tuple, Set

import requests
from atproto import Client
from dotenv import load_dotenv

load_dotenv()

# --- Environment / Config ---
BSKY_HANDLE = os.getenv("BSKY_HANDLE")
BSKY_APP_PASSWORD = os.getenv("BSKY_APP_PASSWORD")
COOPER_API_KEY = os.getenv("COOPER_API_KEY")

# URLs for museum APIs
MET_SEARCH_URL = "https://collectionapi.metmuseum.org/public/collection/v1/search"
MET_OBJECT_URL = "https://collectionapi.metmuseum.org/public/collection/v1/objects"
CMA_SEARCH_URL = "https://openaccess-api.clevelandart.org/api/artworks"

# Cooper Hewitt website search JSON endpoint
CH_SEARCH_URL = "https://collection.cooperhewitt.org/search/objects/"  # but DO add &format=json in params.

SEEN_IDS_PATH = "posted_ids.json"
MAX_TEXT_LEN = 300
HASHTAGS_SUFFIX = "\n\n#tomato #art"

# --- Utility: seen IDs ---
def load_seen_ids() -> Set[str]:
    try:
        with open(SEEN_IDS_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_seen_ids(seen: Set[str]) -> None:
    try:
        with open(SEEN_IDS_PATH, "w", encoding="utf-8") as f:
            json.dump(sorted(list(seen)), f, indent=2)
    except Exception as e:
        print("Warning: failing to save seen IDs:", e)

def add_hashtags(base_text: str) -> str:
    base = base_text.strip()
    suffix = HASHTAGS_SUFFIX
    full = base + suffix
    if len(full) <= MAX_TEXT_LEN:
        return full
    allowed = MAX_TEXT_LEN - len(suffix)
    if allowed <= 0:
        return suffix.strip()
    truncated = base[:allowed].rstrip() + "…"
    return truncated + suffix

# --- Bluesky Posting ---
def post_to_bluesky(text: str, image_url: Optional[str]) -> None:
    if not BSKY_HANDLE or not BSKY_APP_PASSWORD:
        raise RuntimeError("Missing Bluesky app credentials")
    final_text = add_hashtags(text)
    print(f"Logging into Bluesky as {BSKY_HANDLE} …")
    client = Client()
    client.login(BSKY_HANDLE, BSKY_APP_PASSWORD)
    embed = None
    if image_url:
        print("  → Downloading image:", image_url)
        r = requests.get(image_url, timeout=60)
        r.raise_for_status()
        blob = client.upload_blob(r.content)
        embed = {
            "$type": "app.bsky.embed.images",
            "images": [
                {
                    "alt": final_text[:300],
                    "image": blob.blob,
                }
            ],
        }
    record = {
        "$type": "app.bsky.feed.post",
        "text": final_text,
        "createdAt": client.get_current_time_iso(),
    }
    if embed:
        record["embed"] = embed
    print("  → Posting to Bluesky …")
    client.app.bsky.feed.post.create(repo=client.me.did, record=record)

# --- Museum pickers ---

def is_tomato_related(obj: dict) -> bool:
    """Check if an object is actually tomato-related by checking relevant fields."""
    search_fields = [
        obj.get("title", ""),
        obj.get("objectName", ""),
        obj.get("medium", ""),
        obj.get("culture", ""),
        obj.get("classification", ""),
    ]

    # Check tags
    tags = obj.get("tags") or []
    for tag in tags:
        search_fields.append(tag.get("term", ""))

    # Combine all fields and search for tomato
    combined = " ".join(search_fields).lower()
    return "tomato" in combined

def pick_met_tomato(seen: Set[str]) -> Optional[Tuple[str, str, str]]:
    params = {
        "q": "tomato",
        "hasImages": "true",
    }
    print("Requesting Met search with params:", params)
    r = requests.get(MET_SEARCH_URL, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    ids = data.get("objectIDs") or []
    print(f"Met search returned {len(ids)} IDs")
    random.shuffle(ids)
    for oid in ids:
        key = f"met:{oid}"
        if key in seen:
            continue
        print("Considering Met object:", oid)
        r2 = requests.get(f"{MET_OBJECT_URL}/{oid}", timeout=30)
        r2.raise_for_status()
        obj = r2.json()

        # Validate it's actually tomato-related
        if not is_tomato_related(obj):
            print(f"  → Skipping {oid}: not tomato-related")
            continue

        if not obj.get("isPublicDomain"):
            continue
        img = obj.get("primaryImageSmall") or obj.get("primaryImage")
        if not img:
            continue
        title = obj.get("title", "Untitled")
        artist = obj.get("artistDisplayName","")
        date = obj.get("objectDate","")
        credit = obj.get("creditLine","")
        dept = obj.get("department","")
        lines=[title]
        if artist: lines.append(artist)
        if date: lines.append(date)
        if credit: lines.append(credit)
        if dept: lines.append(f"Source: {dept}, The Met Open Access")
        caption = "\n".join(lines)
        return caption, img, key
    print("No usable Met tomato found.")
    return None

def pick_cma_tomato(seen: Set[str]) -> Optional[Tuple[str, str, str]]:
    params = {
        "q": "tomato",
        "has_image": 1,
        "cc0": 1,
        "limit": 40,
    }
    print("Requesting CMA search with params:", params)
    r = requests.get(CMA_SEARCH_URL, params=params, timeout=30)
    r.raise_for_status()
    objs = r.json().get("data",[]) or []
    print(f"CMA search returned {len(objs)} objects")
    random.shuffle(objs)
    for obj in objs:
        oid = str(obj.get("id"))
        key = f"cma:{oid}"
        if key in seen:
            continue
        img = (obj.get("images") or {}).get("web",{}).get("url")
        if not img:
            continue
        title = obj.get("title","Untitled")
        creators = obj.get("creators") or []
        creator = creators[0].get("description") if creators else ""
        date = obj.get("creation_date","")
        credit = obj.get("creditline","")
        lines=[title]
        if creator: lines.append(creator)
        if date: lines.append(date)
        if credit: lines.append(credit)
        lines.append("Source: The Cleveland Museum of Art (CC0)")
        caption = "\n".join(lines)
        return caption, img, key
    print("No usable CMA tomato found.")
    return None

def pick_cooperhewitt_tomato(seen_ids):
    """
    Uses Cooper Hewitt's official REST API with proper authentication.
    API Docs: https://collection.cooperhewitt.org/api/methods/cooperhewitt.search.objects
    """
    if not COOPER_API_KEY:
        print("Cooper Hewitt API key not found in environment")
        return None

    # Search for tomato objects with images
    search_url = "https://api.collection.cooperhewitt.org/rest/"
    search_params = {
        "method": "cooperhewitt.search.objects",
        "access_token": COOPER_API_KEY,
        "query": "tomato",
        "has_images": "1",
        "per_page": "100",
        "page": "1"
    }

    print("Requesting Cooper Hewitt API search for tomato…")
    try:
        r = requests.get(search_url, params=search_params, timeout=30)
        if r.status_code != 200:
            print(f"Cooper Hewitt API returned {r.status_code}")
            print(f"Response: {r.text[:500]}")
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"Cooper Hewitt API error: {e}")
        return None

    # Get objects from the results
    objects = data.get("objects", [])
    if not objects:
        print("No Cooper Hewitt objects found.")
        return None

    random.shuffle(objects)

    for obj in objects:
        oid = str(obj.get("id"))
        key = f"cooper:{oid}"

        if key in seen_ids:
            continue

        # Get images from the object
        images = obj.get("images") or []
        if not images:
            continue

        img_data = images[0]

        # Try different image sizes (b = large, z = medium, n = small)
        img_url = (
            img_data.get("b", {}).get("url") or
            img_data.get("z", {}).get("url") or
            img_data.get("n", {}).get("url")
        )
        if not img_url:
            continue

        # Build caption from object metadata
        title = obj.get("title", "Untitled")
        date = obj.get("date", "")
        desc = obj.get("description", "")

        lines = [title]
        if date:
            lines.append(date)
        if desc and len(desc) < 200:  # Only include short descriptions
            lines.append(desc)
        lines.append("Source: Cooper Hewitt Smithsonian Design Museum")

        caption = "\n".join(lines)
        print(f"  → Selected Cooper Hewitt object {oid}")
        return caption, img_url, key

    print("No suitable Cooper Hewitt item found.")
    return None



# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():
    seen = load_seen_ids()
    print(f"Loaded {len(seen)} previous posted IDs.")
    pickers = [
        ("Cooper Hewitt", pick_cooperhewitt_tomato),
        ("Cleveland Museum of Art", pick_cma_tomato),
        ("The Met", pick_met_tomato),
    ]

    random.shuffle(pickers)
    for label, picker in pickers:
        print(f"\n=== Trying source: {label} ===")
        result = picker(seen)
        if result:
            caption, image_url, key = result
            print(f"Posting from source: {label}")
            post_to_bluesky(caption, image_url)
            seen.add(key)
            save_seen_ids(seen)
            print("Done.")
            return
        else:
            print(f"No usable tomato from {label}.")
    print("No tomato artwork found from any source.")

if __name__ == "__main__":
    main()

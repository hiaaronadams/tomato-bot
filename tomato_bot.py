# tomato_bot.py — FINAL VERSION

import os
import json
import random
import textwrap
from typing import Optional, Tuple, Set

import requests
from atproto import Client
from dotenv import load_dotenv

COOPER_API_KEY = os.getenv("COOPER_API_KEY")

load_dotenv()

# --- Environment / Config ---
BSKY_HANDLE = os.getenv("BSKY_HANDLE")
BSKY_APP_PASSWORD = os.getenv("BSKY_APP_PASSWORD")

# URLs for museum APIs
MET_SEARCH_URL = "https://collectionapi.metmuseum.org/public/collection/v1/search"
MET_OBJECT_URL = "https://collectionapi.metmuseum.org/public/collection/v1/objects"
CMA_SEARCH_URL = "https://openaccess-api.clevelandart.org/api/artworks"
SMITHSONIAN_SEARCH_URL = "https://api.si.edu/openaccess/api/v1.0/search"

# Cooper Hewitt website search JSON endpoint
CH_SEARCH_URL = "https://collection.cooperhewitt.org/search/objects/"  # but DO add &format=json in params.

SMITH_API_KEY = os.getenv("SMITH_API_KEY")

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

def pick_met_tomato(seen: Set[str]) -> Optional[Tuple[str, str, str]]:
    # Try multiple search terms to find more results
    search_terms = ["tomato", "tomatoes", "lycopersicon"]
    all_ids = []

    for term in search_terms:
        params = {
            "q": term,
            "hasImages": "true",
        }
        print(f"Requesting Met search for '{term}'...")
        try:
            r = requests.get(MET_SEARCH_URL, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            ids = data.get("objectIDs") or []
            all_ids.extend(ids)
            print(f"  Found {len(ids)} IDs for '{term}'")
        except Exception as e:
            print(f"  Met API error for '{term}': {e}")

    all_ids = list(set(all_ids))  # Remove duplicates
    print(f"Total Met IDs after dedup: {len(all_ids)}")
    random.shuffle(all_ids)
    for oid in all_ids:
        key = f"met:{oid}"
        if key in seen:
            continue
        print("Considering Met object:", oid)
        try:
            r2 = requests.get(f"{MET_OBJECT_URL}/{oid}", timeout=30)
            r2.raise_for_status()
            obj = r2.json()
        except Exception:
            continue

        if not obj.get("isPublicDomain"):
            print(f"  Skipping - not public domain")
            continue

        img = obj.get("primaryImageSmall") or obj.get("primaryImage")
        if not img:
            print(f"  Skipping - no image")
            continue

        # Basic validation: just check it's not obviously unrelated
        # Trust the Met's search mostly - they matched it for a reason
        title_str = obj.get("title", "Untitled")

        # Skip known false positives
        false_positive_titles = ["charity", "madonna", "virgin", "saint"]
        if any(fp in title_str.lower() for fp in false_positive_titles):
            print(f"  Skipping {oid} - '{title_str[:50]}' - likely false positive")
            continue

        print(f"  ✓ Selected Met tomato: {title_str[:50]}")
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
    # Try multiple search terms
    search_terms = ["tomato", "tomatoes"]
    all_objs = []

    for term in search_terms:
        params = {
            "q": term,
            "has_image": 1,
            "cc0": 1,
            "limit": 100,
        }
        print(f"Requesting CMA search for '{term}'...")
        try:
            r = requests.get(CMA_SEARCH_URL, params=params, timeout=30)
            r.raise_for_status()
            objs = r.json().get("data",[]) or []
            all_objs.extend(objs)
            print(f"  Found {len(objs)} objects for '{term}'")
        except Exception as e:
            print(f"  CMA API error for '{term}': {e}")

    # Remove duplicates based on ID
    seen_obj_ids = set()
    unique_objs = []
    for obj in all_objs:
        obj_id = obj.get("id")
        if obj_id not in seen_obj_ids:
            seen_obj_ids.add(obj_id)
            unique_objs.append(obj)

    print(f"Total CMA objects after dedup: {len(unique_objs)}")
    random.shuffle(unique_objs)
    for obj in unique_objs:
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
    Uses Cooper Hewitt's public JSON search (same used by the website).
    """
    url = "https://collection.cooperhewitt.org/search/"

    # Try multiple search terms
    search_terms = ["tomato", "tomatoes"]
    all_objs = []

    for term in search_terms:
        params = {
            "q": term,
            "format": "json",
            "with_images": "1",
        }

        print(f"Requesting Cooper Hewitt search for '{term}'...")
        try:
            r = requests.get(url, params=params, timeout=30)
            data = r.json()
            objs = data.get("objects", [])
            all_objs.extend(objs)
            print(f"  Found {len(objs)} objects for '{term}'")
        except Exception as e:
            print(f"  Cooper Hewitt API error for '{term}': {e}")

    # Remove duplicates based on ID
    seen_obj_ids = set()
    unique_objs = []
    for obj in all_objs:
        obj_id = obj.get("id")
        if obj_id not in seen_obj_ids:
            seen_obj_ids.add(obj_id)
            unique_objs.append(obj)

    print(f"Total Cooper Hewitt objects after dedup: {len(unique_objs)}")
    objs = unique_objs
    if not objs:
        print("No Cooper Hewitt objects found.")
        return None

    random.shuffle(objs)

    for obj in objs:
        oid = str(obj.get("id"))
        key = f"cooper:{oid}"

        if key in seen_ids:
            continue

        images = obj.get("images") or []
        if not images:
            continue

        img_data = images[0]

        img_url = (
            img_data.get("b", {}).get("url") or
            img_data.get("z", {}).get("url") or
            img_data.get("n", {}).get("url")
        )
        if not img_url:
            continue

        title = obj.get("title", "Untitled")
        date = obj.get("date", "")
        desc = obj.get("description", "")

        lines = [title]
        if date: lines.append(date)
        if desc: lines.append(desc)
        lines.append("Source: Cooper Hewitt Smithsonian Design Museum")

        caption = add_hashtags("\n".join(lines))
        print("  → Selected Cooper Hewitt tomato")
        return caption, img_url, key

    print("No suitable Cooper Hewitt item found.")
    return None

def pick_smithsonian_tomato(seen: Set[str]) -> Optional[Tuple[str, str, str]]:
    """
    Search Smithsonian Open Access API for tomato artwork
    """
    if not SMITH_API_KEY:
        print("No Smithsonian API key configured")
        return None

    search_terms = ["tomato", "tomatoes"]
    all_rows = []

    for term in search_terms:
        params = {
            "q": term,
            "api_key": SMITH_API_KEY,
            "rows": 100,
        }
        print(f"Requesting Smithsonian search for '{term}'...")
        try:
            r = requests.get(SMITHSONIAN_SEARCH_URL, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            rows = data.get("response", {}).get("rows", [])
            all_rows.extend(rows)
            print(f"  Found {len(rows)} objects for '{term}'")
        except Exception as e:
            print(f"  Smithsonian API error for '{term}': {e}")

    # Remove duplicates based on ID
    seen_obj_ids = set()
    unique_objs = []
    for obj in all_rows:
        obj_id = obj.get("id")
        if obj_id not in seen_obj_ids:
            seen_obj_ids.add(obj_id)
            unique_objs.append(obj)

    print(f"Total Smithsonian objects after dedup: {len(unique_objs)}")
    random.shuffle(unique_objs)

    for obj in unique_objs:
        oid = str(obj.get("id", ""))
        key = f"smithsonian:{oid}"

        if key in seen:
            continue

        # Get image
        content = obj.get("content", {})
        descriptive_non_repeating = content.get("descriptiveNonRepeating", {})
        online_media = descriptive_non_repeating.get("online_media", {})
        media_list = online_media.get("media", [])

        img_url = None
        for media in media_list:
            if media.get("type") == "Images":
                resources = media.get("resources", [])
                if resources:
                    img_url = resources[0].get("url")
                    break

        if not img_url:
            continue

        # Get metadata
        title = obj.get("title", "Untitled")
        unit_code = obj.get("unitCode", "")
        date = content.get("freetext", {}).get("date", [{}])[0].get("content", "")

        lines = [title]
        if date:
            lines.append(date)
        lines.append(f"Source: Smithsonian Institution ({unit_code})")

        caption = "\n".join(lines)
        print(f"  ✓ Selected Smithsonian tomato: {title[:50]}")
        return caption, img_url, key

    print("No suitable Smithsonian item found.")
    return None


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():
    seen = load_seen_ids()
    print(f"Loaded {len(seen)} previous posted IDs.")
    pickers = [
        ("Smithsonian", pick_smithsonian_tomato),
        ("The Met", pick_met_tomato),
        ("Cleveland Museum of Art", pick_cma_tomato),
        ("Cooper Hewitt", pick_cooperhewitt_tomato),
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

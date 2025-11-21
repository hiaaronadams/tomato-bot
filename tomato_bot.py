# tomato_bot.py — FINAL VERSION

import os
import json
import random
import textwrap
import re
from typing import Optional, Tuple, Set
from io import BytesIO

import requests
from atproto import Client
from dotenv import load_dotenv
from PIL import Image
from bs4 import BeautifulSoup

load_dotenv()

# --- Environment / Config ---
BSKY_HANDLE = os.getenv("BSKY_HANDLE")
BSKY_APP_PASSWORD = os.getenv("BSKY_APP_PASSWORD")
COOPER_API_KEY = os.getenv("COOPER_API_KEY")

# URLs for museum APIs
MET_SEARCH_URL = "https://collectionapi.metmuseum.org/public/collection/v1/search"
MET_OBJECT_URL = "https://collectionapi.metmuseum.org/public/collection/v1/objects"
CMA_SEARCH_URL = "https://openaccess-api.clevelandart.org/api/artworks"
ARTIC_SEARCH_URL = "https://api.artic.edu/api/v1/artworks/search"
ARTIC_IMAGE_BASE = "https://www.artic.edu/iiif/2"
RIJKS_SEARCH_URL = "https://www.rijksmuseum.nl/api/en/collection"
LOC_SEARCH_URL = "https://www.loc.gov/search/"

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
        image_data = r.content

        # Bluesky limit is ~976KB, resize if needed
        MAX_SIZE = 950 * 1024  # 950KB to be safe
        if len(image_data) > MAX_SIZE:
            print(f"  → Image too large ({len(image_data)/1024:.0f}KB), resizing...")
            img = Image.open(BytesIO(image_data))

            # Resize to 80% of original dimensions
            new_size = (int(img.width * 0.8), int(img.height * 0.8))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

            # Save as JPEG with quality adjustment
            output = BytesIO()
            img.convert('RGB').save(output, format='JPEG', quality=85, optimize=True)
            image_data = output.getvalue()
            print(f"  → Resized to {len(image_data)/1024:.0f}KB")

        blob = client.upload_blob(image_data)
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

def is_tomato_related(obj: dict, debug: bool = False) -> bool:
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

    if debug and "tomato" not in combined:
        print(f"    DEBUG: Title={obj.get('title', 'N/A')[:50]}")
        print(f"    DEBUG: Tags={[t.get('term') for t in tags[:3]]}")

    return "tomato" in combined

def pick_met_tomato(seen: Set[str]) -> Optional[Tuple[str, str, str]]:
    """
    Scrape Met website search results since their API search is broken.
    Website search: https://www.metmuseum.org/art/collection/search?showOnly=withImage&q=tomato
    """
    print("Scraping Met website search for tomato...")

    # Scrape the Met website search page
    search_url = "https://www.metmuseum.org/art/collection/search"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    try:
        r = requests.get(search_url, params={'showOnly': 'withImage', 'q': 'tomato'},
                        headers=headers, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"Failed to scrape Met website: {e}")
        return None

    # Parse HTML and extract object IDs
    soup = BeautifulSoup(r.text, 'html.parser')

    # Look for object IDs in links like /art/collection/search/12345
    object_ids = []
    for link in soup.find_all('a', href=True):
        match = re.search(r'/art/collection/search/(\d+)', link['href'])
        if match:
            object_ids.append(match.group(1))

    # Remove duplicates
    object_ids = list(set(object_ids))
    print(f"Found {len(object_ids)} tomato items from Met website")

    if not object_ids:
        print("No Met objects found via scraping")
        return None

    random.shuffle(object_ids)

    # Try each object until we find a usable one
    for oid in object_ids:
        key = f"met:{oid}"
        if key in seen:
            continue

        print(f"Considering Met object: {oid}")
        try:
            r2 = requests.get(f"{MET_OBJECT_URL}/{oid}", timeout=30)
            r2.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print(f"  → Skipping {oid}: object not found")
                continue
            raise

        obj = r2.json()

        if not obj.get("isPublicDomain"):
            continue
        img = obj.get("primaryImageSmall") or obj.get("primaryImage")
        if not img:
            continue

        title = obj.get("title", "Untitled")
        artist = obj.get("artistDisplayName", "")
        date = obj.get("objectDate", "")
        credit = obj.get("creditLine", "")
        dept = obj.get("department", "")

        lines = [title]
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

def pick_artic_tomato(seen: Set[str]) -> Optional[Tuple[str, str, str]]:
    """
    Art Institute of Chicago - scrape website search since API is broken
    Website search: https://www.artic.edu/collection?q="tomato"
    """
    print("Scraping Art Institute website search for tomato...")

    # Scrape the Art Institute website search page with quoted search
    search_url = "https://www.artic.edu/collection"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    try:
        r = requests.get(search_url, params={'q': '"tomato"'},
                        headers=headers, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"Failed to scrape Art Institute website: {e}")
        return None

    # Parse HTML and extract object IDs
    soup = BeautifulSoup(r.text, 'html.parser')

    # Look for artwork links - they're usually /artworks/12345/title-slug
    object_ids = []
    for link in soup.find_all('a', href=True):
        match = re.search(r'/artworks/(\d+)/', link['href'])
        if match:
            object_ids.append(match.group(1))

    # Remove duplicates
    object_ids = list(set(object_ids))
    print(f"Found {len(object_ids)} tomato artworks from Art Institute website")

    if not object_ids:
        print("No Art Institute objects found via scraping")
        return None

    random.shuffle(object_ids)

    # Try each object - now use their API to get details
    for oid in object_ids:
        key = f"artic:{oid}"
        if key in seen:
            continue

        print(f"Considering Art Institute object: {oid}")
        try:
            # Use API to get object details
            r2 = requests.get(f"https://api.artic.edu/api/v1/artworks/{oid}",
                            params={'fields': 'id,title,artist_display,date_display,image_id,is_public_domain,credit_line'},
                            timeout=30)
            r2.raise_for_status()
            data = r2.json()
            artwork = data.get('data', {})
        except Exception as e:
            print(f"  → Skipping {oid}: {e}")
            continue

        title = artwork.get("title", "Untitled")
        is_pd = artwork.get("is_public_domain")
        has_image = bool(artwork.get("image_id"))

        print(f"  Title: {title[:50]}")
        print(f"  Public domain: {is_pd}, Has image: {has_image}")

        # Must be public domain and have an image
        if not is_pd:
            print(f"  → Skipping {oid}: not public domain")
            continue

        image_id = artwork.get("image_id")
        if not image_id:
            print(f"  → Skipping {oid}: no image")
            continue

        # Construct IIIF image URL (full quality, max 843px width)
        img_url = f"{ARTIC_IMAGE_BASE}/{image_id}/full/843,/0/default.jpg"

        artist = artwork.get("artist_display", "")
        date = artwork.get("date_display", "")
        credit = artwork.get("credit_line", "")

        lines = [title]
        if artist: lines.append(artist)
        if date: lines.append(date)
        if credit: lines.append(credit)
        lines.append("Source: Art Institute of Chicago (CC0)")

        caption = "\n".join(lines)
        print(f"  → Selected Art Institute object {oid}")
        return caption, img_url, key

    print("No usable Art Institute tomato found.")
    return None

def pick_rijks_tomato(seen: Set[str]) -> Optional[Tuple[str, str, str]]:
    """
    Rijksmuseum API - requires API key but registration is free
    API Docs: https://data.rijksmuseum.nl/
    Note: Set RIJKS_API_KEY in .env if you want to use this source
    """
    api_key = os.getenv("RIJKS_API_KEY")

    if not api_key:
        print("Rijksmuseum API key not found (set RIJKS_API_KEY in .env)")
        return None

    print("Requesting Rijksmuseum search for tomato...")

    params = {
        "key": api_key,
        "q": "tomato",
        "imgonly": "true",
        "ps": 40
    }

    try:
        r = requests.get(RIJKS_SEARCH_URL, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"Rijksmuseum API error: {e}")
        return None

    artworks = data.get("artObjects", [])
    print(f"Found {len(artworks)} artworks from Rijksmuseum")

    if not artworks:
        return None

    random.shuffle(artworks)

    for artwork in artworks:
        oid = artwork.get("objectNumber", "")
        key = f"rijks:{oid}"

        if key in seen:
            continue

        # Check if it allows download (CC0/public domain)
        if not artwork.get("permitDownload", False):
            continue

        img_url = artwork.get("webImage", {}).get("url")
        if not img_url:
            continue

        title = artwork.get("title", "Untitled")
        artist = artwork.get("principalOrFirstMaker", "")

        lines = [title]
        if artist: lines.append(artist)
        lines.append("Source: Rijksmuseum (CC0)")

        caption = "\n".join(lines)
        print(f"  → Selected Rijksmuseum object {oid}")
        return caption, img_url, key

    print("No usable Rijksmuseum tomato found.")
    return None

def pick_loc_tomato(seen: Set[str]) -> Optional[Tuple[str, str, str]]:
    """
    Library of Congress - all public domain!
    API Docs: https://www.loc.gov/apis/
    """
    print("Requesting Library of Congress search for tomato...")

    params = {
        "q": "tomato",
        "fo": "json",  # Format: JSON
        "at": "results",  # API type
        "c": 50,  # Count
        "sp": 1  # Start page
    }

    try:
        r = requests.get(LOC_SEARCH_URL, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"Library of Congress API error: {e}")
        return None

    results = data.get("results", [])
    print(f"Found {len(results)} items from Library of Congress")

    if not results:
        return None

    # Filter to only items with images
    items_with_images = [r for r in results if r.get("image_url")]
    print(f"  {len(items_with_images)} have images")

    if not items_with_images:
        return None

    random.shuffle(items_with_images)

    for item in items_with_images:
        # Generate unique ID from the item's URL or ID
        item_url = item.get("url", "")
        item_id = item.get("id", "")
        if not item_id and item_url:
            # Extract ID from URL if possible
            match = re.search(r'/(\d+)/?$', item_url)
            if match:
                item_id = match.group(1)

        if not item_id:
            continue

        key = f"loc:{item_id}"
        if key in seen:
            continue

        # Get image URL - upgrade to larger size
        img_url = item.get("image_url", [])
        if isinstance(img_url, list) and img_url:
            img_url = img_url[0]
        elif not img_url:
            img_url = None

        if not img_url:
            continue

        # Skip placeholder SVGs and non-image files
        if (img_url.endswith('.svg') or
            '/original-format/' in img_url or
            '/static/images/' in img_url):
            continue

        # Only accept JPEG/PNG images
        if not any(ext in img_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.tif', '.tiff']):
            continue

        # LOC uses IIIF - convert to full or larger size
        # tile.loc.gov URLs: change /pct:25/ to /pct:100/ or /full/
        # Or change /512,/ to /2048,/ for larger dimensions
        if "tile.loc.gov" in img_url:
            # Replace small percentages with full size
            img_url = re.sub(r'/pct:\d+/', '/pct:100/', img_url)
            # Or replace pixel dimensions with larger size
            img_url = re.sub(r'/\d+,/', '/2048,/', img_url)
        # For other LOC image servers, try to upgrade size parameter
        elif "size=" in img_url:
            img_url = re.sub(r'size=\d+', 'size=2048', img_url)

        title = item.get("title", "Untitled")
        date = item.get("date", "")
        creator = ""
        if item.get("contributor"):
            creators = item.get("contributor", [])
            if isinstance(creators, list) and creators:
                creator = creators[0]

        lines = [title]
        if creator: lines.append(creator)
        if date: lines.append(date)
        lines.append("Source: Library of Congress (Public Domain)")

        caption = "\n".join(lines)
        print(f"  → Selected LOC item {item_id}")
        return caption, img_url, key

    print("No usable Library of Congress tomato found.")
    return None


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():
    seen = load_seen_ids()
    print(f"Loaded {len(seen)} previous posted IDs.")
    pickers = [
        # TESTING - Library of Congress (all public domain!)
        ("Library of Congress", pick_loc_tomato),
        # WORKING SOURCES
        ("Cooper Hewitt", pick_cooperhewitt_tomato),
        ("Cleveland Museum of Art", pick_cma_tomato),
        ("The Met", pick_met_tomato),
        # DISABLED - has 3 tomato items but all copyrighted, not public domain
        # ("Art Institute of Chicago", pick_artic_tomato),
    ]

    # random.shuffle(pickers)  # Disabled for testing - LOC first
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

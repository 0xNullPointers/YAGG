import os, json, re, concurrent.futures
from bs4 import BeautifulSoup, Tag
from typing import List, Dict, Set, Optional
from src.core.cf_bypass import CF_Scraper
from src.core.network import create_session, download_file
from src.core.logger import log_operation

# Steam CDN image hash: 40 hex chars + extension
_ICON_HASH_RE = re.compile(r'^[0-9a-f]{40}\.(?:jpe?g|png|gif|webp)$', re.IGNORECASE)

def _image_name(img: Optional[Tag]) -> str:
    """Extract the CDN file name from an <img>: data-name attribute first,
    then fall back to the basename of the src URL."""
    if img is None:
        return ""
    name = (img.get('data-name') or "").strip()
    if not _ICON_HASH_RE.match(name):
        src = img.get('src') or ""
        name = src.rstrip('/').split('/')[-1]
    return name if _ICON_HASH_RE.match(name) else ""

def _block_text(block: Optional[Tag]) -> str:
    if block is None:
        return ""
    return block.get_text(" ", strip=True)

def _set_if_missing(target: Dict, key: str, value):
    if key not in target:
        target[key] = value

@log_operation()
def download_images(appid: str, achievements: List[Dict], output_dir: str, silent: bool = False):
    image_folder = os.path.join(output_dir, "images")
    os.makedirs(image_folder, exist_ok=True)

    download_tasks = []
    downloaded_images: Set[str] = set()

    for achievement in achievements:
        for key in ['icon', 'icongray']:
            icon_name = achievement.get(key)
            if not icon_name: continue

            # Remove 'images/' prefix if it exists in the dictionary value
            actual_icon_name = icon_name.replace("images/", "")
            image_file_name = actual_icon_name.split('/')[-1]
            if image_file_name in downloaded_images: continue

            image_url = f"https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/{appid}/{image_file_name}"
            image_path = os.path.join(image_folder, image_file_name)

            download_tasks.append((image_url, image_path))
            downloaded_images.add(image_file_name)

    if not download_tasks:
        return

    if not silent:
        print(f"Downloading {len(download_tasks)} images...")

    session = create_session()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            future_to_url = {executor.submit(download_file, url, path, session): url for url, path in download_tasks}

            completed = 0
            for future in concurrent.futures.as_completed(future_to_url):
                completed += 1
                if not silent:
                    dots = "." * ((completed - 1) % 3 + 1)
                    print(f"  - Download Image ({completed}/{len(download_tasks)}) {dots}")

        if not silent:
            # Re-calculating successful results if needed, though as_completed loop already finished
            successful = sum(1 for f in future_to_url if f.result())
            print(f"Downloaded {successful}/{len(download_tasks)} images successfully")
    finally:
        session.close()

@log_operation()
def fetch_from_steamdb(appid: str, output_dir: str, silent: bool = False) -> List[Dict]:
    if not silent: print("Fetching achievements from SteamDB...")

    if not silent: print("  - Capturing HTML")
    with CF_Scraper(hide_window=True) as scraper:
        html_content = scraper.scrape(f"https://steamdb.info/app/{appid}/stats/", page_load_wait=2)

    if not html_content:
        raise RuntimeError("Failed to fetch HTML from SteamDB")

    soup = BeautifulSoup(html_content, 'html.parser')

    # SteamDB renders achievement rows as div.achievement. If that selector ever
    # stops matching (site restructure), fall back to any element carrying a
    # spoiler/name/api marker so extraction keeps working.
    achievement_divs = soup.select('div.achievement')
    if not achievement_divs:
        achievement_divs = soup.select('[id^="achievement-"]')
        if not achievement_divs:
            achievement_divs = [
                el for el in soup.select('[class*="achievement"]')
                if el.select_one('.achievement_api, .achievement_name, .achievement_desc, .achievement_spoiler')
            ]

    if not achievement_divs:
        return []

    if not silent:
        print("  - Extracting achievements")
        print(f"Found {len(achievement_divs)} achievement blocks")

    achievements = []

    for achievement_div in achievement_divs:
        entry: Dict = {}

        # Description
        desc_div = achievement_div.select_one('.achievement_desc')
        if desc_div is None:
            desc_div = achievement_div.select_one('[class*="desc"], [class*="detail"]')
        description = ""
        if desc_div is not None:
            spoiler = desc_div.select_one('.achievement_spoiler, .spoiler')
            if spoiler is not None:
                description = _block_text(spoiler)
            else:
                # Fallback: hidden marker is stable prose ("Hidden achievement:")
                match = re.search(r'Hidden achievement:\s*(.*)', desc_div.get_text(" ", strip=True), flags=re.I)
                if match and match.group(1).strip():
                    description = match.group(1).strip()
                else:
                    description = re.sub(r'^Hidden achievement:\s*', '', desc_div.get_text(" ", strip=True), flags=re.I)
        entry['description'] = description

        # Display name
        display_div = achievement_div.select_one('.achievement_name')
        _set_if_missing(entry, 'displayName', _block_text(display_div))

        # Hidden
        hidden = 0
        if desc_div is not None:
            if desc_div.select_one('.achievement_spoiler, .spoiler') is not None:
                hidden = 1
            elif re.search(r'Hidden achievement:\s*\S', desc_div.get_text(" ", strip=True), flags=re.I):
                hidden = 1
        entry['hidden'] = hidden

        # Icons: prefer explicit classes, else fall back to any seeded image
        # carrying a valid CDN hash (document order = small thumb, then big art).
        icon_img = achievement_div.select_one('img.achievement_image')
        lock_img = achievement_div.select_one('img.achievement_image_small')
        icon = _image_name(icon_img)
        icongray = _image_name(lock_img)

        if not (icon or icongray):
            seeded = [img for img in achievement_div.select('img[data-name]') if _image_name(img)]
            hashes = [_image_name(img) for img in seeded]
            if len(hashes) >= 2:
                icongray, icon = hashes[0], hashes[1]
            elif hashes:
                icon = hashes[0]

        _set_if_missing(entry, 'icon', f"images/{icon}" if icon else "")
        _set_if_missing(entry, 'icongray', f"images/{icongray}" if icongray else "")

        # API name (e.g. ACH39, PLAY_CS2) — the goldberg "name" key.
        # Fallback: derive from stable id anchor (achievement-ACH39 -> ACH39).
        name_div = achievement_div.select_one('.achievement_api')
        name = name_div.get_text(" ", strip=True) if name_div else ""
        if not name:
            m = re.match(r'^achievement-(.+)$', achievement_div.get('id') or '')
            if m:
                name = m.group(1)
        entry['name'] = name

        # Skip elements that yielded zero identity (fallback probe noise)
        if not (entry.get('name') or entry.get('displayName') or icon or icongray):
            continue

        achievements.append(entry)

    achievement_file = os.path.join(output_dir, "achievements.json")
    with open(achievement_file, "w", encoding='utf-8') as f:
        json.dump(achievements, f, indent=2, ensure_ascii=False)

    download_images(appid, achievements, output_dir, silent)
    return achievements

@log_operation()
def fetch_from_steamcommunity(appid: str, output_dir: str, silent: bool = False) -> List[Dict]:
    url = f"https://steamcommunity.com/stats/{appid}/achievements/"
    if not silent: print("Fetching achievements from Steam Community...")
    if not silent: print("  - Capturing HTML")
    with create_session() as session:
        response = session.get(url, timeout=30)
        soup = BeautifulSoup(response.content, 'html.parser')
        achievement_rows = soup.select('.achieveRow')

        if not achievement_rows:
            return []

        if not silent:
            print("  - Extracting achievements")
            print(f"Found {len(achievement_rows)} achievements")

        achievements = []
        for idx, achievement in enumerate(achievement_rows):
            img_tag = achievement.select_one('.achieveImgHolder img')
            icon = img_tag['src'].split('/')[-1] if img_tag and img_tag.get('src') else ""

            name_tag = achievement.select_one('.achieveTxt h3')
            displayName = name_tag.text.strip() if name_tag else ""

            description_tag = achievement.select_one('.achieveTxt h5')
            description = description_tag.text.strip() if description_tag else ""

            achievements.append({
                "description": description,
                "displayName": displayName,
                "hidden": 1 if description == "" else 0,
                "icon": f"images/{icon}",
                "icongray": f"images/{icon}",
                "name": f"ach{idx + 1}"
            })

        achievement_file = os.path.join(output_dir, "achievements.json")
        with open(achievement_file, 'w', encoding='utf-8') as f:
            json.dump(achievements, f, indent=2, ensure_ascii=False)

        download_images(appid, achievements, output_dir, silent)

    return achievements

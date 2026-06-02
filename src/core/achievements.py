import os
import json
import concurrent.futures
from bs4 import BeautifulSoup
from typing import List, Dict, Set, Optional
from src.core.cf_bypass import CF_Scraper
from src.core.network import create_session, download_file

def download_images(appid: str, achievements: List[Dict], silent: bool = False):
    image_folder = "images"
    os.makedirs(image_folder, exist_ok=True)

    download_tasks = []
    downloaded_images: Set[str] = set()

    for achievement in achievements:
        for key in ['icon', 'icongray']:
            icon_name = achievement.get(key)
            if not icon_name: continue

            image_file_name = icon_name.split('/')[-1]
            if image_file_name in downloaded_images: continue

            image_url = f"https://cdn.fastly.steamstatic.com/steamcommunity/public/images/apps/{appid}/{image_file_name}"
            image_path = os.path.join(image_folder, image_file_name)

            download_tasks.append((image_url, image_path))
            downloaded_images.add(image_file_name)

    if not silent:
        print(f"Downloading {len(download_tasks)} images...")

    session = create_session()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(download_file, url, path, session) for url, path in download_tasks]
            concurrent.futures.wait(futures)

        if not silent:
            successful = sum(1 for f in futures if f.result())
            print(f"Downloaded {successful}/{len(download_tasks)} images successfully")
    finally:
        session.close()

def fetch_from_steamdb(appid: str, silent: bool = False) -> List[Dict]:
    if not silent: print("Fetching achievements from SteamDB...")

    with CF_Scraper(hide_window=True) as scraper:
        html_content = scraper.scrape(f"https://steamdb.info/app/{appid}/stats/", page_load_wait=2)

    if not html_content:
        raise RuntimeError("Failed to fetch HTML from SteamDB")

    soup = BeautifulSoup(html_content, 'html.parser')
    achievements = []

    for achievement_div in soup.select('div.achievement'):
        name_div = achievement_div.select_one('div.achievement_api')
        if not name_div: continue

        name = name_div.text.strip()
        display_name_div = achievement_div.select_one('div.achievement_name')
        display_name = display_name_div.text.strip() if display_name_div else ""

        desc_div = achievement_div.select_one('div.achievement_desc')
        hidden, description = 0, ""
        if desc_div:
            hidden_span = desc_div.select_one('span.achievement_spoiler')
            if hidden_span:
                hidden, description = 1, hidden_span.text.strip()
            else:
                description = desc_div.text.strip()

        icon_imgs = achievement_div.select('img')
        icon = icon_imgs[0].get('data-name', '') if len(icon_imgs) >= 1 else ""
        icongray = icon_imgs[1].get('data-name', '') if len(icon_imgs) >= 2 else ""

        achievements.append({
            "description": description,
            "displayName": display_name,
            "hidden": hidden,
            "icon": f"images/{icon}",
            "icongray": f"images/{icongray}",
            "name": name
        })

    with open("achievements.json", "w", encoding='utf-8') as f:
        json.dump(achievements, f, indent=2, ensure_ascii=False)

    download_images(appid, achievements, silent)
    return achievements

def fetch_from_steamcommunity(appid: str, silent: bool = False) -> List[Dict]:
    url = f"https://steamcommunity.com/stats/{appid}/achievements/"
    if not silent: print("Fetching achievements from Steam Community...")

    with create_session() as session:
        response = session.get(url, timeout=30)
        soup = BeautifulSoup(response.content, 'html.parser')

        achievements = []
        achievement_rows = soup.select('.achieveRow')

        if not silent: print(f"Found {len(achievement_rows)} achievements")

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

        with open('achievements.json', 'w', encoding='utf-8') as f:
            json.dump(achievements, f, indent=2, ensure_ascii=False)

        download_images(appid, achievements, silent)

    return achievements

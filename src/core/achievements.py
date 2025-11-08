import os
import json
import concurrent.futures
from bs4 import BeautifulSoup
from curl_cffi import requests
from typing import List, Dict, Set, Optional
from src.core.cf_bypass import CF_Scraper

def create_session(session_type: str = "steam", appid: Optional[str] = None) -> requests.Session:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.5 Safari/605.1.15",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
    }
    session = requests.Session(impersonate="safari15_5", headers=headers, timeout=30)
    return session

def mk_request(url: str, session: requests.Session) -> requests.Response:
    try:
        return session.get(url, timeout=30)
    except Exception as e:
        raise RuntimeError(f"Failed to fetch URL {url}: {str(e)}")

def download_one_image(image_url: str, image_path: str, session: requests.Session) -> bool:
    try:
        response = session.get(image_url, timeout=30)
        if response.status_code == 200:
            with open(image_path, 'wb') as img_file:
                img_file.write(response.content)
            return True
    except Exception:
        pass
    return False

def download_images(appid: str, achievements: List[Dict], session: requests.Session, silent: bool = False):
    image_folder = "images"
    os.makedirs(image_folder, exist_ok=True)
    
    download_tasks = []
    downloaded_images: Set[str] = set()
    
    # Collect images to download
    for achievement in achievements:
        for key in ['icon', 'icongray']:
            icon_name = achievement.get(key)
            if not icon_name:
                continue

            image_file_name = icon_name.split('/')[-1]
            if image_file_name in downloaded_images:
                continue

            image_url = f"https://cdn.fastly.steamstatic.com/steamcommunity/public/images/apps/{appid}/{image_file_name}"
            image_path = os.path.join(image_folder, image_file_name)
            
            download_tasks.append((image_url, image_path))
            downloaded_images.add(image_file_name)
    
    if not silent:
        print(f"Downloading {len(download_tasks)} images...")
    
    # Download images concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(download_one_image, url, path, session) for url, path in download_tasks]
        concurrent.futures.wait(futures)
    
    if not silent:
        successful = sum(1 for f in futures if f.result())
        print(f"Downloaded {successful}/{len(download_tasks)} images successfully")

def fetch_from_steamdb(appid: str, silent: bool = False) -> List[Dict]:
    if not silent:
        print("Fetching achievements from SteamDB...")
    
    # Use the scraper to get HTML
    with CF_Scraper(hide_window=True) as scraper:
        html_content = scraper.scrape(
            f"https://steamdb.info/app/{appid}/stats/", 
            page_load_wait=2
        )
    
    if not html_content:
        raise RuntimeError("Failed to fetch HTML from SteamDB")
    
    soup = BeautifulSoup(html_content, 'html.parser')
    achievements = []
    
    achievement_divs = soup.select('div.achievement')
    
    for achievement_div in achievement_divs:
        name_div = achievement_div.select_one('div.achievement_api')
        if not name_div:
            continue
        name = name_div.text.strip()

        display_name_div = achievement_div.select_one('div.achievement_name')
        display_name = display_name_div.text.strip() if display_name_div else ""
        desc_div = achievement_div.select_one('div.achievement_desc')
        hidden = 0
        description = ""
        if desc_div:
            hidden_span = desc_div.select_one('span.achievement_spoiler')
            if hidden_span:
                hidden = 1
                description = hidden_span.text.strip()
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

    with open("achievements.json", "w", encoding='utf-8') as json_file:
        json.dump(achievements, json_file, indent=2, ensure_ascii=False)
    
    # Download images using a single session
    steam_session = create_session("steam")
    try:
        download_images(appid, achievements, steam_session, silent)
    finally:
        steam_session.close()
    
    return achievements

def fetch_from_steamcommunity(appid: str, silent: bool = False) -> List[Dict]:
    session = create_session("steam")
    
    try:
        url = f"https://steamcommunity.com/stats/{appid}/achievements/"
        if not silent:
            print("Fetching achievements from Steam Community...")
        
        response = mk_request(url, session)
        soup = BeautifulSoup(response.content, 'html.parser')

        achievements = []
        achievement_rows = soup.select('.achieveRow')
        
        if not silent:
            print(f"Found {len(achievement_rows)} achievements")

        for idx, achievement in enumerate(achievement_rows):
            img_tag = achievement.select_one('.achieveImgHolder img')
            icon = ""
            if img_tag and img_tag.get('src'):
                icon_src = str(img_tag['src'])
                icon = icon_src.split('/')[-1]
            
            name_tag = achievement.select_one('.achieveTxt h3')
            displayName = name_tag.text.strip() if name_tag else ""
            
            description_tag = achievement.select_one('.achieveTxt h5')
            description = description_tag.text.strip() if description_tag else ""
            hidden = 1 if description == "" else 0

            achievements.append({
                "description": description,
                "displayName": displayName,
                "hidden": hidden,
                "icon": f"images/{icon}",
                "icongray": f"images/{icon}",
                "name": f"ach{idx + 1}"
            })

        with open('achievements.json', 'w', encoding='utf-8') as json_file:
            json.dump(achievements, json_file, indent=2, ensure_ascii=False)
        
        # Download images using the same session
        download_images(appid, achievements, session, silent)
        
    finally:
        session.close()
    
    return achievements

# def main():
#     try:
#         appid = "730"
#         fetch_from_steamdb(appid)
#     except FileNotFoundError:
#         print("Error: Headers not found.")
#     except Exception as e:
#         print(f"Error: {e}")

# if __name__ == "__main__":
#     main()
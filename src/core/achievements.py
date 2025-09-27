import os
import json
import concurrent.futures
from bs4 import BeautifulSoup
from curl_cffi import requests
from typing import List, Dict, Set, Optional

def load_headers() -> Dict[str, Dict[str, str]]:
    enc_text = None
    try:
        headers_url = "https://raw.githubusercontent.com/0xNullPointers/YAGG/main/assets/headers.dat"
        response = requests.get(headers_url, timeout=10)
        response.raise_for_status()
        enc_text = response.text.strip()
    except:
        try:
            headers_path = os.path.abspath(os.path.join(os.getcwd(), "..", "..", "assets", "headers.dat"))
            with open(headers_path, 'r', encoding='utf-8') as f:
                enc_text = f.read().strip()
        except:
            raise FileNotFoundError("Headers not found")

    try:
        output_chars = []
        token = "GetHeaders"
        sk_len = len(token)
        for idx in range(0, len(enc_text), 2):
            if idx + 1 >= len(enc_text):
                break
            try:
                num_val = int(enc_text[idx:idx+2], 16)
                char_pos = idx // 2
                xor_val = (num_val - char_pos - 13) % 256
                orig_char = xor_val ^ ord(token[char_pos % sk_len])
                if 0 <= orig_char <= 255:
                    output_chars.append(chr(orig_char))
            except ValueError:
                continue
        
        return json.loads(''.join(output_chars))
    
    except json.JSONDecodeError:
        raise ValueError("Failed to parse headers")
    except Exception as err:
        raise ValueError(f"Failed to decrypt headers: {err}")

def create_session(session_type: str = "steam", appid: Optional[str] = None) -> requests.Session:
    headers_data = load_headers()
    
    if session_type == "steamdb":
        headers = headers_data["steamdb"].copy()
        if appid and "referer" in headers:
            headers["referer"] = headers["referer"].format(appid=appid)
        
        session = requests.Session(impersonate="chrome110", headers=headers, timeout=30)
    else:  # steam
        headers = headers_data["steam"]
        session = requests.Session(impersonate="safari15_5", headers=headers, timeout=30)
    
    return session

def mk_request(url: str, session: requests.Session) -> requests.Response:
    try:
        return session.get(url, timeout=30)
    except Exception as e:
        raise RuntimeError(f"Failed to fetch URL {url}: {str(e)}")

def download_one_image(args) -> bool:
    image_url, image_path, headers = args
    try:
        session = create_session("steam")
        response = mk_request(image_url, session)
        if response.status_code == 200:
            with open(image_path, 'wb') as img_file:
                img_file.write(response.content)
            session.close()
            return True
        session.close()
    except Exception:
        return False
    return False

def download_images(appid: str, achievements: List[Dict], session: requests.Session, silent: bool = False):
    image_folder = "images"
    os.makedirs(image_folder, exist_ok=True)
    
    download_tasks = []
    downloaded_images: Set[str] = set()
    headers = session.headers
    
    total_images = 0
    for achievement in achievements:
        for key in ['icon', 'icongray']:
            icon_name = achievement.get(key)
            if icon_name and icon_name.split('/')[-1] not in downloaded_images:
                total_images += 1
                downloaded_images.add(icon_name.split('/')[-1])
    
    downloaded_images.clear()
    
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
            
            download_tasks.append((image_url, image_path, headers))
            downloaded_images.add(image_file_name)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        list(executor.map(download_one_image, download_tasks))

def fetch_from_steamdb(appid: str, silent: bool = False) -> List[Dict]:
    session = create_session("steamdb", appid)
    url = f"https://steamdb.info/api/RenderAppSection/?section=stats&appid={appid}"
    if not silent:
        print("Fetching achievements from SteamDB...")
    response = mk_request(url, session)
    soup = BeautifulSoup(response.text, 'html.parser')
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
        icon = ""
        icongray = ""
        if len(icon_imgs) >= 1:
            icon = icon_imgs[0].get('data-name', '')
        if len(icon_imgs) >= 2:
            icongray = icon_imgs[1].get('data-name', '')
        
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
    
    steam_session = create_session("steam")
    download_images(appid, achievements, steam_session, silent)
    steam_session.close()
    session.close()
    return achievements

def fetch_from_steamcommunity(appid: str, silent: bool = False):
    session = create_session("steam")
    url = f"https://steamcommunity.com/stats/{appid}/achievements/"
    if not silent:
        print("Fetching achievements from Steam Community...")
    response = mk_request(url, session)
    soup = BeautifulSoup(response.content, 'html.parser')

    achievements = []
    achievement_rows = soup.select('.achieveRow')
    if not silent:
        print(f"Found {len(achievement_rows)} achievements...")

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
    
    download_images(appid, achievements, session, silent)
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
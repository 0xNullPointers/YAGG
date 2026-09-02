import os, concurrent.futures
from bs4 import BeautifulSoup
from src.core.network import create_session
from src.core.logger import log_operation

@log_operation()
def fetch_steam_dlcs(session, app_id):
    url = f"https://store.steampowered.com/api/appdetails/?filters=basic&appids={app_id}"
    try:
        response = session.get(url, timeout=5)
        response.raise_for_status()
        dlc_ids = response.json().get(str(app_id), {}).get('data', {}).get('dlc', [])
        if not dlc_ids: return {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            @log_operation()
            def fetch_dlc_details(dlc_id):
                try:
                    res = session.get(f"https://store.steampowered.com/api/appdetails/?filters=basic&appids={dlc_id}", timeout=3)
                    data = res.json().get(str(dlc_id), {})
                    if data.get('success'):
                        return (dlc_id, data['data'].get('name', f'DLC {dlc_id}'))
                except: pass
                return None
            return dict(filter(None, executor.map(fetch_dlc_details, dlc_ids)))
    except: return {}

@log_operation()
def fetch_steamdb_dlcs(app_id):
    try:
        from src.core.cf_bypass import get_cf_session
        session = get_cf_session()
        response = session.get(f"https://steamdb.info/app/{app_id}/dlc/", timeout=10)
        if response.status_code != 200:
            return {}
        soup = BeautifulSoup(response.content, 'html.parser')
        rows = soup.select("#dlc table.table tbody tr.app, table.table tbody tr.app")
        dlcs = {}
        for row in rows:
            try:
                tds = row.find_all("td")
                if len(tds) >= 2:
                    dlc_id = int(tds[0].text.strip())
                    dlc_name = tds[1].text.strip()
                    dlcs[dlc_id] = dlc_name
            except Exception:
                pass
        return dlcs
    except Exception:
        return {}

@log_operation()
def fetch_dlc(app_id):
    with create_session() as session:
        steam_dlcs = fetch_steam_dlcs(session, app_id)
    steamdb_dlcs = fetch_steamdb_dlcs(app_id)
    return {**steamdb_dlcs, **steam_dlcs}

@log_operation()
def create_dlc_config(game_dir, dlc_details):
    if not dlc_details: return
    settings_dir = os.path.join(game_dir, "steam_settings")
    os.makedirs(settings_dir, exist_ok=True)
    try:
        with open(os.path.join(settings_dir, "configs.app.ini"), 'w', encoding='utf-8') as f:
            f.write("[app::dlcs]\nunlock_all=0\n")
            for dlc_id, dlc_name in dlc_details.items():
                f.write(f"{dlc_id} = {dlc_name}\n")
    except: pass

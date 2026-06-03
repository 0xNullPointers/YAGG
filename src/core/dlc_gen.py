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
def fetch_steamdb_dlcs(session, app_id):
    try:
        response = session.get(f"https://steamdb.info/app/{app_id}/dlc/", timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        rows = soup.select("#dlc.tab-pane.selected table.table tbody tr.app")
        dlcs = {}
        for row in rows:
            try:
                dlc_id = int(row.select_one("td:nth-child(1)").text.strip())
                dlc_name = row.select_one("td:nth-child(2)").text.strip()
                dlcs[dlc_id] = dlc_name
            except: pass
        return dlcs
    except: return {}

@log_operation()
def fetch_dlc(app_id):
    with create_session() as session:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(fetch_steam_dlcs, session, app_id)
            f2 = executor.submit(fetch_steamdb_dlcs, session, app_id)
            d1, d2 = f1.result(), f2.result()

    unq_dlcs = {**d2, **d1}
    return unq_dlcs

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

import os, sqlite3
from src.core.network import create_session
from src.core.logger import log_operation

@log_operation()
def get_steam_data(output_dir='assets'):
    os.makedirs(output_dir, exist_ok=True)
    db_file = os.path.join(output_dir, 'steam_data.db')

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS apps (appid INTEGER PRIMARY KEY, name TEXT, type TEXT)''')

    cursor.execute('SELECT COUNT(*) FROM apps')
    if cursor.fetchone()[0] == 0:
        app_list = None
        with create_session() as session:
            try:
                res = session.get("https://raw.githubusercontent.com/0xNullPointers/SteamGamesList/main/AppIDList.json")
                app_list = res.json()
            except:
                try:
                    res = session.get("https://api.steampowered.com/ISteamApps/GetAppList/v2/")
                    app_list = res.json()['applist']['apps']
                except:
                    print("Warning: No data fetched")

        if app_list:
            cursor.executescript('''
                PRAGMA synchronous  = OFF;
                PRAGMA journal_mode = MEMORY;
                PRAGMA cache_size   = -64000;
            ''')
            cursor.executemany(
                'INSERT OR IGNORE INTO apps (appid, name, type) VALUES (?, ?, ?)',
                ((app['appid'], app['name'], app.get('type')) for app in app_list)
            )
            conn.commit()
            cursor.executescript('''
                PRAGMA synchronous  = FULL;
                PRAGMA journal_mode = DELETE;
            ''')

    return conn

@log_operation()
def get_steam_app_by_name(app_name):
    conn = get_steam_data()
    try:
        cursor = conn.cursor()
        cursor.execute('''SELECT appid, name, type FROM apps WHERE LOWER(name) = LOWER(?)''', (app_name,))
        result = cursor.fetchone()
        if result: return {'appid': result[0], 'name': result[1], 'type': result[2]}

        with create_session() as session:
            try:
                res = session.get(f"https://steamcommunity.com/actions/SearchApps/{app_name}")
                for result in res.json():
                    if result['name'].lower() == app_name.lower():
                        cursor.execute(
                            '''INSERT OR IGNORE INTO apps (appid, name, type) VALUES (?, ?, ?)''',
                            (result['appid'], result['name'], None)
                        )
                        conn.commit()
                        return {'appid': result['appid'], 'name': result['name'], 'type': None}
            except: pass
        return None
    finally:
        conn.close()

@log_operation()
def get_steam_app_by_id(appid):
    conn = get_steam_data()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT name, type FROM apps WHERE appid = ?', (int(appid),))
        result = cursor.fetchone()
        if result: return {'appid': int(appid), 'name': result[0], 'type': result[1]}

        with create_session() as session:
            try:
                res = session.get(f"https://store.steampowered.com/api/appdetails?appids={appid}")
                data = res.json()
                if str(appid) in data and data[str(appid)]['success']:
                    name = data[str(appid)]['data'].get('name', 'Unknown')
                    cursor.execute(
                        '''INSERT OR IGNORE INTO apps (appid, name, type) VALUES (?, ?, ?)''',
                        (int(appid), name, None)
                    )
                    conn.commit()
                    return {'appid': int(appid), 'name': name, 'type': None}
            except: pass
        return None
    finally:
        conn.close()

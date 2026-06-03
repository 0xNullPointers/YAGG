import os
from src.core.network import download_file
from src.core.logger import log_operation

SEVENZIP_PATH = os.path.join("assets", "7zip", "7za.exe")
GOLDBERG_URL = "https://github.com/0xNullPointers/gbe_fork/releases/latest/download/emu-win-release.7z"
EMU_FOLDER = os.path.join("assets", "goldberg_emu")
ARCHIVE_NAME = "emu-win-release.7z"

@log_operation()
def download_goldberg():
    os.makedirs(EMU_FOLDER, exist_ok=True)
    archive_path = os.path.join(EMU_FOLDER, ARCHIVE_NAME)
    if os.path.exists(archive_path): return archive_path

    if download_file(GOLDBERG_URL, archive_path):
        print("Download completed.")
        return archive_path
    raise RuntimeError("Failed to download Goldberg emulator")

@log_operation()
def extract_archive(archive_path):
    import subprocess
    try:
        cmd = [SEVENZIP_PATH, 'x', f'-o{EMU_FOLDER}', '-y', archive_path]
        subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        os.remove(archive_path)
        print("Extraction completed.")
    except Exception as e:
        raise RuntimeError(f"Failed to extract archive: {str(e)}")

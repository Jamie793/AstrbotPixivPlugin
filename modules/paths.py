from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PLUGIN_DIR / "data"
DEFAULT_DOWNLOAD_DIR = DATA_DIR / "cache"
CACHE_IMAGE_DIR = DEFAULT_DOWNLOAD_DIR / "images"
CACHE_IMAGE_TEMP_DIR = CACHE_IMAGE_DIR / "temp"
CACHE_IMAGE_FILE_DIR = CACHE_IMAGE_DIR / "files"
CACHE_NOVEL_DIR = DEFAULT_DOWNLOAD_DIR / "novels"
CACHE_NOVEL_TEMP_DIR = CACHE_NOVEL_DIR / "temp"
CACHE_NOVEL_FILE_DIR = CACHE_NOVEL_DIR / "files"
STATE_FILE = DATA_DIR / "state.json"
R18_WHITELIST_FILE = DATA_DIR / "r18_whitelist.json"
LAST_ZIP_FILE = DATA_DIR / "last_zip.json"
LAST_ITEMS_FILE = DATA_DIR / "last_items.json"
TOKEN_STATE_FILE = DATA_DIR / "token_state.json"
OAUTH_STATE_FILE = DATA_DIR / "oauth_state.json"

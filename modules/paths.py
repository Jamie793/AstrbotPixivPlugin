from pathlib import Path
from astrbot.api.star import StarTools

PLUGIN_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = StarTools.get_data_dir("astrbot_plugin_pixivs_crawler")
DEFAULT_DOWNLOAD_DIR = DATA_DIR / "downloads"
R18_WHITELIST_FILE = DATA_DIR / "r18_whitelist.json"
LAST_ZIP_FILE = DATA_DIR / "last_zip.json"
LAST_ITEMS_FILE = DATA_DIR / "last_items.json"
TOKEN_STATE_FILE = DATA_DIR / "token_state.json"
OAUTH_STATE_FILE = DATA_DIR / "oauth_state.json"

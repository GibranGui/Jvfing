import os
import logging
from dotenv import load_dotenv # Hanya jika menggunakan python-dotenv untuk lokal

# Muat .env file jika ada (untuk pengembangan lokal)
load_dotenv()
log = logging.getLogger(__name__)

# --- Helper untuk mendapatkan env var ---
def get_env_var(var_name: str, required: bool = True, default=None) -> str | None:
    """Mendapatkan environment variable, log jika tidak ditemukan."""
    value = os.getenv(var_name)
    if value is None and required and default is None:
        log.error(f"Environment variable '{var_name}' tidak ditemukan!")
        raise ValueError(f"Environment variable '{var_name}' wajib diatur.")
    elif value is None:
        log.info(f"Environment variable '{var_name}' tidak ditemukan, menggunakan default: {default}")
        return default
    return value

def get_env_var_int(var_name: str, required: bool = True, default: int | None = None) -> int | None:
    """Mendapatkan environment variable sebagai integer."""
    str_val = get_env_var(var_name, required, str(default) if default is not None else None)
    if str_val is None:
        return None
    try:
        return int(str_val)
    except ValueError:
        log.error(f"Environment variable '{var_name}' harus berupa angka integer.")
        raise ValueError(f"Environment variable '{var_name}' harus berupa angka integer.")

# --- Konfigurasi Bot ---
TOKEN = get_env_var("TOKEN")
COMMAND_PREFIX = get_env_var("COMMAND_PREFIX", required=False, default="!")

# --- Konfigurasi Database ---
SUPABASE_DB_URL = get_env_var("SUPABASE_DB_URL")

# --- Konfigurasi Discord IDs (WAJIB PAKAI ID!) ---
# Cara mendapatkan ID: https://support.discord.com/hc/en-us/articles/206346498-Where-can-I-find-my-User-Server-Message-ID
ADMIN_ROLE_ID = get_env_var_int("ADMIN_ROLE_ID")         # Ganti dengan ID peran Owner/Admin
SALES_ROLE_ID = get_env_var_int("SALES_ROLE_ID")         # Ganti dengan ID peran Sales Man
SCRIPT_CHANNEL_ID = get_env_var_int("SCRIPT_CHANNEL_ID") # Channel file .lua
PURCHASE_LOG_CHANNEL_ID = get_env_var_int("PURCHASE_LOG_CHANNEL_ID") # Channel log pembelian baru

# --- Konfigurasi Lain ---
from datetime import timezone, timedelta
UTC_PLUS_7 = timezone(timedelta(hours=7))
LICENSE_DURATION_DAYS = 30 # Durasi lisensi dalam hari

# --- Konfigurasi Webserver ---
WEB_SERVER_PORT = int(os.environ.get('PORT', 5000)) # Port dari Koyeb atau default

log.info("Konfigurasi dimuat.")

import logging
import sys

def setup_logging():
    """Konfigurasi logging dasar."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout # Log ke console
        # Jika ingin log ke file juga:
        # handlers=[
        #     logging.FileHandler("bot.log"),
        #     logging.StreamHandler(sys.stdout)
        # ]
    )
    # Mengurangi log dari library pihak ketiga yang terlalu 'cerewet'
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

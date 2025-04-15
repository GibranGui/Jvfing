import discord
from discord.ext import commands
import asyncio
import logging
import os

# Impor dari file proyek
from utils.logger import setup_logging
import config # Impor config untuk akses variabel
from database import get_db_pool, close_db_pool

# Setup logging di awal
setup_logging()
log = logging.getLogger(__name__)

# --- Kelas Bot Utama (Lebih Ringkas) ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix=config.COMMAND_PREFIX, intents=intents)
        self.db_pool = None # Akan diinisialisasi di setup_hook

    async def setup_hook(self):
        """Inisialisasi database pool dan load Cogs."""
        log.info("Menjalankan setup_hook...")

        # 1. Inisialisasi Database Pool
        log.info("Menginisialisasi koneksi database pool...")
        self.db_pool = await get_db_pool(config.SUPABASE_DB_URL)
        if not self.db_pool:
            log.critical("Gagal membuat database pool. Bot akan dimatikan.")
            await self.close() # Hentikan bot jika DB gagal konek
            return

        # 2. Load Cogs
        log.info("Memuat Cogs...")
        initial_extensions = [
            'cogs.license_cog',
            'cogs.webserver_cog',
            # Tambahkan cog lain di sini jika ada
        ]
        for extension in initial_extensions:
            try:
                await self.load_extension(extension)
                log.info(f"Cog '{extension}' berhasil dimuat.")
            except Exception as e:
                log.exception(f"Gagal memuat Cog '{extension}': {e}")
                # Pertimbangkan untuk menghentikan bot jika cog penting gagal dimuat

        log.info("Setup hook selesai.")


    async def on_ready(self):
        """Dipanggil ketika bot sepenuhnya siap."""
        log.info(f'Bot terhubung sebagai {self.user} (ID: {self.user.id})')
        log.info(f'Prefix: {config.COMMAND_PREFIX}')
        log.info('Siap menerima perintah dan request API.')

    async def close(self):
        """Membersihkan resource saat bot dimatikan."""
        log.info("Memulai proses shutdown bot...")
        # Pertama, unload cogs (ini akan memanggil cog_unload, termasuk stop webserver)
        log.info("Unloading Cogs...")
        for extension in list(self.extensions): # iterasi di copy list
             try:
                 await self.unload_extension(extension)
                 log.info(f"Cog '{extension}' berhasil di-unload.")
             except Exception as e:
                 log.error(f"Error unloading Cog '{extension}': {e}")

        # Kedua, tutup pool database
        log.info("Menutup database pool...")
        if self.db_pool:
            await close_db_pool(self.db_pool)

        # Terakhir, panggil metode close bawaan
        log.info("Memanggil super().close()...")
        await super().close()
        log.info("Bot shutdown selesai.")

# --- Menjalankan Bot ---
if __name__ == "__main__":
    log.info("Memulai bot...")
    if not config.TOKEN:
        log.critical("Environment variable TOKEN tidak ditemukan!")
    elif not config.SUPABASE_DB_URL:
         log.critical("Environment variable SUPABASE_DB_URL tidak ditemukan!")
    # Tambahkan pengecekan env var penting lainnya dari config.py
    elif not all([config.ADMIN_ROLE_ID, config.SALES_ROLE_ID, config.SCRIPT_CHANNEL_ID, config.PURCHASE_LOG_CHANNEL_ID]):
         log.critical("Satu atau lebih ID Role/Channel penting tidak diatur di environment variables!")
    else:
        bot = MyBot()
        try:
            # Jalankan bot
            bot.run(config.TOKEN, log_handler=None) # Gunakan logger yang sudah disetup
        except discord.LoginFailure:
            log.critical("Gagal login ke Discord. Token salah atau tidak valid.")
        except Exception as e:
            log.exception(f"FATAL: Error tidak tertangani saat menjalankan bot: {e}")
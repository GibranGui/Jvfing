import discord
from discord.ext import commands
from aiohttp import web
import json
import logging
from datetime import datetime

# Impor dari file lain
from config import SCRIPT_CHANNEL_ID, UTC_PLUS_7, WEB_SERVER_PORT
from database import fetch_license

log = logging.getLogger(__name__)

class WebserverCog(commands.Cog):
    def __init__(self, bot: commands.Bot, db_pool):
        self.bot = bot
        self.db_pool = db_pool
        self.runner = None
        self.site = None
        self.web_server_task = None
        log.info("Webserver Cog loaded.")

    async def start_webserver(self):
        """Menjalankan webserver aiohttp untuk API."""
        if not self.db_pool:
            log.error("Tidak bisa start webserver, database pool tidak tersedia.")
            return

        app = web.Application()
        # Simpan state yang diperlukan (pool DB, instance bot) di app
        app["bot"] = self.bot
        app["db_pool"] = self.db_pool
        app.router.add_post("/get_script", self.handle_request_route) # Endpoint API

        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "0.0.0.0", WEB_SERVER_PORT)
        try:
            await self.site.start()
            log.info(f"🌐 Webserver API berjalan di http://0.0.0.0:{WEB_SERVER_PORT}...")
        except Exception as e:
            log.error(f"❌ Gagal menjalankan webserver di port {WEB_SERVER_PORT}: {e}")
            await self.cleanup_webserver() # Coba cleanup jika start gagal

    async def stop_webserver(self):
        """Menghentikan webserver aiohttp."""
        if self.site:
            try:
                await self.site.stop()
                log.info("Webserver site stopped.")
            except Exception as e:
                log.error(f"Error stopping webserver site: {e}")
            self.site = None
        if self.runner:
            try:
                await self.runner.cleanup()
                log.info("Webserver runner cleaned up.")
            except Exception as e:
                log.error(f"Error cleaning up webserver runner: {e}")
            self.runner = None
        log.info("Webserver dihentikan.")

    async def handle_request_route(self, request: web.Request):
        """Router aiohttp yang memanggil handler logic."""
        # Ambil pool DB dan bot dari app context
        db_pool = request.app["db_pool"]
        bot_instance = request.app["bot"]
        remote_ip = request.remote

        # 1. Parse Request Body
        try:
            data = await request.json()
            user_id = str(data.get("user_id"))
            license_key_from_request = data.get("license_key")

            if not user_id or not license_key_from_request:
                log.warning(f"API Req Warning: user_id/license_key kosong. IP: {remote_ip}")
                return web.Response(text="INVALID", status=400)
        except json.JSONDecodeError:
            log.warning(f"API Req Warning: Payload JSON tidak valid. IP: {remote_ip}")
            return web.Response(text="INVALID", status=400)
        except Exception as e:
            log.error(f"API Req Error: Gagal parse request body: {e}. IP: {remote_ip}")
            return web.Response(text="INVALID", status=500)

        # 2. Validasi Lisensi via Database
        license_data = await fetch_license(db_pool, user_id)

        if license_data is None:
            log.info(f"API Req Info: Lisensi tidak ditemukan untuk user {user_id}. IP: {remote_ip}")
            return web.Response(text="INVALID", status=403)

        db_key = license_data.get('key')
        db_expiry = license_data.get('expiry') # Objek datetime aware

        if license_key_from_request != db_key:
            log.info(f"API Req Info: Kunci lisensi salah untuk user {user_id}. IP: {remote_ip}")
            return web.Response(text="INVALID", status=403)

        if db_expiry is None:
             log.error(f"API DB Error: Tanggal expiry NULL untuk user {user_id}. IP: {remote_ip}")
             return web.Response(text="INVALID", status=500) # Data error

        now_aware = datetime.now(UTC_PLUS_7)
        if db_expiry < now_aware:
            log.info(f"API Req Info: Lisensi kedaluwarsa untuk user {user_id} (Expiry: {db_expiry}). IP: {remote_ip}")
            # Pertimbangkan menghapus lisensi expired di sini jika diinginkan
            return web.Response(text="INVALID", status=403)

        # 3. Lisensi Valid -> Ambil URL Script dari Channel Discord
        log.info(f"API Req Info: Lisensi valid untuk user {user_id}. IP: {remote_ip}")
        try:
            script_channel = bot_instance.get_channel(SCRIPT_CHANNEL_ID)
            if not script_channel:
                script_channel = await bot_instance.fetch_channel(SCRIPT_CHANNEL_ID)

            if not isinstance(script_channel, discord.TextChannel):
                 log.error(f"API Discord Error: Script channel {SCRIPT_CHANNEL_ID} bukan text channel.")
                 return web.Response(text="INVALID", status=500)

            # Ambil pesan terbaru yang ada attachment .lua
            async for message in script_channel.history(limit=20):
                if message.attachments:
                    for attachment in message.attachments:
                        # Pastikan nama file benar-benar .lua (case insensitive)
                        if attachment.filename.lower().endswith(".lua"):
                            log.info(f"API Req Info: Script URL ditemukan: {attachment.url}")
                            return web.Response(text=attachment.url) # Kirim URL

            log.warning(f"API Req Warning: Tidak ada file .lua ditemukan di channel {SCRIPT_CHANNEL_ID}.")
            return web.Response(text="INVALID", status=404)

        except discord.NotFound:
            log.error(f"API Discord Error: Script channel {SCRIPT_CHANNEL_ID} tidak ditemukan.")
            return web.Response(text="INVALID", status=500)
        except discord.Forbidden:
            log.error(f"API Discord Error: Bot tidak punya izin akses script channel {SCRIPT_CHANNEL_ID}.")
            return web.Response(text="INVALID", status=500)
        except Exception as e:
            log.error(f"API Discord Error: Gagal mengambil script URL: {e}")
            return web.Response(text="INVALID", status=500)

    # --- Lifecycle Methods ---
    async def cog_load(self):
        """Dipanggil saat Cog dimuat."""
        # Start web server dalam task terpisah
        self.web_server_task = asyncio.create_task(self.start_webserver())

    async def cog_unload(self):
        """Dipanggil saat Cog di-unload (misalnya saat bot dimatikan)."""
        log.info("Mencoba menghentikan webserver...")
        if self.web_server_task and not self.web_server_task.done():
            # Beri kesempatan task selesai, tapi jangan blok selamanya
            try:
                 await asyncio.wait_for(self.stop_webserver(), timeout=10.0)
            except asyncio.TimeoutError:
                 log.warning("Timeout saat menunggu webserver berhenti.")
            except Exception as e:
                 log.error(f"Error saat stop_webserver: {e}")
            # Batalkan task jika masih berjalan setelah stop (safety net)
            self.web_server_task.cancel()
            try:
                await self.web_server_task # Tunggu pembatalan
            except asyncio.CancelledError:
                log.info("Task webserver dibatalkan.")
            except Exception as e:
                log.error(f"Error setelah membatalkan task webserver: {e}")
        else:
             await self.stop_webserver() # Panggil stop jika task sudah selesai atau tidak ada

# Fungsi setup untuk Cog
async def setup(bot: commands.Bot):
    # Ambil pool dari bot jika sudah diinisialisasi di bot utama
    # Ini asumsi pool dibuat di bot utama sebelum cogs di-load
    db_pool = getattr(bot, 'db_pool', None)
    if not db_pool:
        log.error("Database pool tidak tersedia saat mencoba memuat WebserverCog.")
        return
    await bot.add_cog(WebserverCog(bot, db_pool))
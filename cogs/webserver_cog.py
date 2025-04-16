import discord
from discord.ext import commands
from aiohttp import web
import json
import logging
import asyncio
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

    async def fetch_script_url(self, bot_instance: commands.Bot, script_name: str):
        """Mencari URL script Lua berdasarkan nama file di channel."""
        try:
            script_channel = bot_instance.get_channel(SCRIPT_CHANNEL_ID)
            if not script_channel:
                script_channel = await bot_instance.fetch_channel(SCRIPT_CHANNEL_ID)

            if not isinstance(script_channel, discord.TextChannel):
                log.error(f"API Discord Error: Script channel {SCRIPT_CHANNEL_ID} bukan text channel.")
                return None

            async for message in script_channel.history(limit=50): # Tingkatkan limit jika perlu
                if message.attachments:
                    for attachment in message.attachments:
                        if attachment.filename.lower() == script_name.lower():
                            log.info(f"API Req Info: Script URL ditemukan untuk '{script_name}': {attachment.url}")
                            return attachment.url
            log.warning(f"API Req Warning: File '{script_name}' tidak ditemukan di channel {SCRIPT_CHANNEL_ID}.")
            return None

        except discord.NotFound:
            log.error(f"API Discord Error: Script channel {SCRIPT_CHANNEL_ID} tidak ditemukan.")
            return None
        except discord.Forbidden:
            log.error(f"API Discord Error: Bot tidak punya izin akses script channel {SCRIPT_CHANNEL_ID}.")
            return None
        except Exception as e:
            log.error(f"API Discord Error: Gagal mengambil script URL: {e}")
            return None

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
            script_request = data.get("script_request") # Nama file script yang diminta

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
        allowed_script = license_data.get('script_name') # Ambil nama script yang diizinkan dari DB

        if license_key_from_request != db_key:
            log.info(f"API Req Info: Kunci lisensi salah untuk user {user_id}. IP: {remote_ip}")
            return web.Response(text="INVALID", status=403)

        if db_expiry is None or db_expiry < datetime.now(UTC_PLUS_7):
            log.info(f"API Req Info: Lisensi tidak valid/kedaluwarsa untuk user {user_id}. IP: {remote_ip}")
            return web.Response(text="INVALID", status=403)

        # 3. Ambil URL Script berdasarkan permintaan dan izin
        if script_request:
            if allowed_script and allowed_script.lower() == script_request.lower():
                script_url = await self.fetch_script_url(bot_instance, script_request)
                if script_url:
                    return web.Response(text=script_url)
                else:
                    return web.Response(text="SCRIPT_NOT_FOUND", status=404)
            else:
                log.info(f"API Req Info: Script '{script_request}' tidak diizinkan untuk user {user_id} (diizinkan: '{allowed_script}'). IP: {remote_ip}")
                return web.Response(text="UNAUTHORIZED_SCRIPT", status=403)
        else:
            # Jika tidak ada script yang diminta, kembalikan script yang diizinkan (jika ada)
            if allowed_script:
                script_url = await self.fetch_script_url(bot_instance, allowed_script)
                if script_url:
                    return web.Response(text=script_url)
                else:
                    return web.Response(text="DEFAULT_SCRIPT_NOT_FOUND", status=404)
            else:
                return web.Response(text="NO_SCRIPT_SPECIFIED", status=400)

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
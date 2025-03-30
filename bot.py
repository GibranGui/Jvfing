import discord
from discord.ext import commands
from aiohttp import web
import json
import random
import string
import datetime
import asyncio
import os

TOKEN = os.getenv("TOKEN")
ADMIN_ROLE_NAME = "Admin"
SCRIPT_CHANNEL_ID = 1355918124238770288
LICENSE_CHANNEL_ID = 1355275302116397138
DATABASE_CHANNEL_ID = 1355918237178528009

# Timezone UTC+7
UTC7 = datetime.timezone(datetime.timedelta(hours=7))

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

licenses = {}

async def restore_licenses():
    """Memuat lisensi dari database channel."""
    await bot.wait_until_ready()
    database_channel = bot.get_channel(DATABASE_CHANNEL_ID)
    
    if database_channel is None:
        print(f"❌ Gagal menemukan channel database dengan ID {DATABASE_CHANNEL_ID}")
        return

    async for message in database_channel.history(oldest_first=True):  # Ambil semua pesan
        try:
            user_id, license_key, expiry_date = message.content.split("|")
            licenses[user_id] = {"key": license_key, "expiry": expiry_date}
        except ValueError:
            print(f"⚠️ Format pesan salah: {message.content}")

async def remove_expired_licenses():
    """Menghapus lisensi yang sudah kadaluarsa dari database."""
    await bot.wait_until_ready()
    database_channel = bot.get_channel(DATABASE_CHANNEL_ID)

    if database_channel is None:
        print(f"❌ Gagal menemukan channel database dengan ID {DATABASE_CHANNEL_ID}")
        return

    now = datetime.datetime.now(UTC7)
    expired_users = []

    async for message in database_channel.history(oldest_first=True):
        try:
            user_id, license_key, expiry_date = message.content.split("|")
            expiry_date = datetime.datetime.strptime(expiry_date, "%Y-%m-%d").replace(tzinfo=UTC7)

            if expiry_date < now:
                expired_users.append(user_id)
                await message.delete()  # Hapus lisensi dari database
                print(f"🗑️ Lisensi {license_key} untuk {user_id} telah dihapus.")

        except ValueError:
            print(f"⚠️ Format pesan salah: {message.content}")

    # Hapus lisensi yang sudah expired dari dictionary
    for user_id in expired_users:
        licenses.pop(user_id, None)

async def schedule_license_check():
    """Menjalankan pengecekan lisensi expired setiap 24 jam."""
    while True:
        await remove_expired_licenses()
        await asyncio.sleep(86400)  # 24 jam

class MyBot(commands.Bot):
    async def setup_hook(self):
        self.loop.create_task(start_webserver())  # Jalankan webserver
        await restore_licenses()  # Load semua lisensi
        self.loop.create_task(schedule_license_check())  # Jalankan loop cek lisensi

bot = MyBot(command_prefix="!", intents=discord.Intents.all())

@bot.command()
async def generate_license(ctx, member: discord.Member):
    """Membuat lisensi baru untuk member."""
    if ADMIN_ROLE_NAME in [role.name for role in ctx.author.roles]:
        license_key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
        expiry_date = (datetime.datetime.now(UTC7) + datetime.timedelta(days=30)).strftime("%Y-%m-%d")

        licenses[str(member.id)] = {"key": license_key, "expiry": expiry_date}

        database_channel = bot.get_channel(DATABASE_CHANNEL_ID)
        await database_channel.send(f"{member.id}|{license_key}|{expiry_date}")

        await member.send(f"🔑 **Lisensi Anda**: `{license_key}`\n📅 **Berlaku hingga**: {expiry_date}")
        await ctx.send(f"✅ Lisensi untuk {member.mention} berhasil dibuat!", delete_after=5)
    else:
        await ctx.send("❌ Anda tidak memiliki izin!", delete_after=5)

async def handle_request(request):
    """Handle permintaan API untuk mendapatkan script jika lisensi valid."""
    try:
        data = await request.json()
        user_id = str(data.get("user_id"))
        license_key = data.get("license_key")

        license_channel = bot.get_channel(LICENSE_CHANNEL_ID)

        if user_id in licenses:
            stored_key = licenses[user_id]["key"]
            expiry_date = datetime.datetime.strptime(licenses[user_id]["expiry"], "%Y-%m-%d").replace(tzinfo=UTC7)

            if license_key == stored_key and expiry_date > datetime.datetime.now(UTC7):
                script_channel = bot.get_channel(SCRIPT_CHANNEL_ID)
                async for message in script_channel.history(limit=10):
                    if message.attachments:
                        for attachment in message.attachments:
                            if attachment.filename.endswith(".lua"):
                                script_content = await attachment.read()
                                script_content = script_content.decode("utf-8")

                                await license_channel.send(
                                    f"✅ **Lisensi Digunakan** oleh <@{user_id}>\n"
                                    f"📅 **Tanggal**: {datetime.datetime.now(UTC7).strftime('%Y-%m-%d %H:%M:%S UTC+7')}"
                                )

                                return web.json_response({"valid": True, "script": script_content})

                return web.json_response({"valid": False, "error": "File script tidak ditemukan!"})
            else:
                await license_channel.send(f"❌ **Lisensi Tidak Valid** untuk <@{user_id}>")
                return web.json_response({"valid": False, "error": "Lisensi sudah kadaluarsa!"})
        else:
            await license_channel.send(f"❌ **Lisensi Tidak Terdaftar** untuk <@{user_id}>")
            return web.json_response({"valid": False, "error": "Lisensi tidak valid!"})

    except json.JSONDecodeError:
        return web.json_response({"valid": False, "error": "Invalid JSON format!"})
    except Exception as e:
        return web.json_response({"valid": False, "error": f"Internal Server Error: {e}"})

app = web.Application()
app.router.add_post("/get_script", handle_request)

async def start_webserver():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 5000)
    await site.start()

bot.run(TOKEN)

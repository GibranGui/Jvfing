import discord
from discord.ext import commands
from aiohttp import web
import json
import random
import string
import datetime
import os

TOKEN = os.getenv("TOKEN")  # Ambil token dari environment variable
ADMIN_ROLE_NAME = "Admin"
SCRIPT_CHANNEL_ID = 1355918124238770288  # ID channel tempat menyimpan script
LICENSE_CHANNEL_ID = 1355275302116397138  # ID channel untuk log lisensi
DATABASE_CHANNEL_ID = 1355918237178528009  # ID channel database lisensi

class MyBot(commands.Bot):
    async def setup_hook(self):
        self.loop.create_task(start_webserver())  # Jalankan webserver
        await restore_licenses()  # Ambil lisensi dari database channel

bot = MyBot(command_prefix="!", intents=discord.Intents.all())

licenses = {}

async def restore_licenses():
    """Mengambil data lisensi dari channel database dan menyimpannya ke dictionary."""
    global licenses
    licenses = {}

    database_channel = bot.get_channel(DATABASE_CHANNEL_ID)
    async for message in database_channel.history(limit=100):  # Ambil 100 pesan terakhir
        try:
            user_id, license_key, expiry_date = message.content.split("|")
            licenses[user_id] = {"key": license_key, "expiry": expiry_date}
        except ValueError:
            continue  # Lewati jika format tidak sesuai

@bot.event
async def on_ready():
    print(f"{bot.user} siap!")

@bot.command()
async def generate_license(ctx, member: discord.Member):
    if ADMIN_ROLE_NAME in [role.name for role in ctx.author.roles]:
        license_key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
        expiry_date = (datetime.datetime.utcnow() + datetime.timedelta(days=30)).strftime("%Y-%m-%d")

        licenses[str(member.id)] = {"key": license_key, "expiry": expiry_date}

        database_channel = bot.get_channel(DATABASE_CHANNEL_ID)
        await database_channel.send(f"{member.id}|{license_key}|{expiry_date}")

        await member.send(f"🔑 **Lisensi Anda**: `{license_key}`\n📅 **Berlaku hingga**: {expiry_date}")
        await ctx.send(f"✅ Lisensi untuk {member.mention} berhasil dibuat!", delete_after=5)
    else:
        await ctx.send("❌ Anda tidak memiliki izin!", delete_after=5)

async def handle_request(request):
    data = await request.json()
    user_id = str(data.get("user_id"))
    license_key = data.get("license_key")

    license_channel = bot.get_channel(LICENSE_CHANNEL_ID)

    if user_id in licenses:
        stored_key = licenses[user_id]["key"]
        expiry_date = datetime.datetime.strptime(licenses[user_id]["expiry"], "%Y-%m-%d")

        if license_key == stored_key and expiry_date > datetime.datetime.utcnow():
            script_channel = bot.get_channel(SCRIPT_CHANNEL_ID)
            async for message in script_channel.history(limit=10):
                if message.attachments:
                    for attachment in message.attachments:
                        if attachment.filename.endswith(".lua"):
                            script_content = await attachment.read()
                            script_content = script_content.decode("utf-8")

                            await license_channel.send(f"✅ **Lisensi Digunakan** oleh <@{user_id}>\n📅 **Tanggal**: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")

                            return web.json_response({"valid": True, "script": script_content})

            return web.json_response({"valid": False, "error": "File script tidak ditemukan!"})
        else:
            await license_channel.send(f"❌ **Lisensi Tidak Valid** untuk <@{user_id}>")
            return web.json_response({"valid": False, "error": "Lisensi sudah kadaluarsa!"})
    else:
        await license_channel.send(f"❌ **Lisensi Tidak Terdaftar** untuk <@{user_id}>")
        return web.json_response({"valid": False, "error": "Lisensi tidak valid!"})

app = web.Application()
app.router.add_post("/get_script", handle_request)

async def start_webserver():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 5000)
    await site.start()

bot.run(TOKEN)

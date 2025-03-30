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
LICENSE_CHANNEL_ID = 1355918237178528009  # ID channel untuk log lisensi

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

# Simpan lisensi dalam file JSON
licenses = {}

async def load_licenses():
    global licenses
    try:
        with open("licenses.json", "r") as f:
            licenses = json.load(f)
    except FileNotFoundError:
        licenses = {}

async def save_licenses():
    with open("licenses.json", "w") as f:
        json.dump(licenses, f, indent=4)

@bot.event
async def on_ready():
    await load_licenses()
    print(f"{bot.user} siap!")

@bot.command()
async def generate_license(ctx, member: discord.Member):
    if ADMIN_ROLE_NAME in [role.name for role in ctx.author.roles]:
        license_key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
        expiry_date = (datetime.datetime.utcnow() + datetime.timedelta(days=30)).strftime("%Y-%m-%d")

        licenses[str(member.id)] = {"key": license_key, "expiry": expiry_date}
        await save_licenses()

        license_channel = bot.get_channel(LICENSE_CHANNEL_ID)
        await license_channel.send(f"🎟 **Lisensi Dibuat** untuk {member.mention}\n🔑 **Kode**: `{license_key}`\n📅 **Berlaku hingga**: {expiry_date}")

        # Kirim lisensi melalui DM ke user yang disebutkan
        try:
            await member.send(f"🔑 **Lisensi Anda**: `{license_key}`\n📅 **Berlaku hingga**: {expiry_date}")
        except:
            await ctx.send(f"⚠️ Tidak bisa mengirim DM ke {member.mention}, pastikan DM terbuka!")

        # Hapus pesan perintah admin setelah 3 detik
        await ctx.message.delete(delay=3)

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
            # 🔹 Ambil file .lua terbaru dari channel script
            script_channel = bot.get_channel(SCRIPT_CHANNEL_ID)
            async for message in script_channel.history(limit=10):  # Ambil hingga 10 pesan terakhir
                if message.attachments:
                    for attachment in message.attachments:
                        if attachment.filename.endswith(".lua"):  # Pastikan file Lua
                            script_content = await attachment.read()
                            script_content = script_content.decode("utf-8")  # Konversi ke teks

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

bot.loop.create_task(start_webserver())
bot.run(TOKEN)

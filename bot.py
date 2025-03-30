import discord
from discord.ext import commands
from aiohttp import web
import json
import random
import string
from datetime import datetime, timedelta, timezone
import os
import asyncio

TOKEN = os.getenv("TOKEN")
ADMIN_ROLE_NAME = "Admin"
SCRIPT_CHANNEL_ID = 1355918124238770288
LICENSE_CHANNEL_ID = 1355918237178528009
DATABASE_CHANNEL_ID = 1355918237178528009  # Ganti dengan ID channel database

# Gunakan zona waktu UTC+7
UTC_PLUS_7 = timezone(timedelta(hours=7))

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
licenses = {}

async def load_licenses():
    """Muat lisensi dari channel database."""
    global licenses
    licenses = {}
    database_channel = bot.get_channel(DATABASE_CHANNEL_ID)
    if not database_channel:
        print("⚠️ Database channel tidak ditemukan!")
        return
    
    async for message in database_channel.history(oldest_first=True):
        try:
            content = message.content.strip("```json\n").strip("\n```")
            data = json.loads(content)
            licenses[data["user_id"]] = {
                "key": data["key"],
                "expiry": data["expiry"]
            }
        except (json.JSONDecodeError, KeyError):
            print(f"⚠️ Format salah di database: {message.content}")

async def save_licenses():
    """Simpan lisensi ke channel database."""
    database_channel = bot.get_channel(DATABASE_CHANNEL_ID)
    if not database_channel:
        print("⚠️ Database channel tidak ditemukan!")
        return

    await database_channel.purge()
    for user_id, data in licenses.items():
        license_data = json.dumps({
            "user_id": user_id,
            "key": data["key"],
            "expiry": data["expiry"]
        })
        await database_channel.send(f"```json\n{license_data}\n```")

@bot.event
async def on_ready():
    await load_licenses()
    print(f"{bot.user} siap! Lisensi dimuat dari database Discord.")

@bot.command()
async def generate_license(ctx, member: discord.Member):
    """Generate lisensi untuk member."""
    if ADMIN_ROLE_NAME not in [role.name for role in ctx.author.roles]:
        await ctx.send("❌ Anda tidak memiliki izin!", delete_after=5)
        return

    license_key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
    expiry_date = (datetime.now(UTC_PLUS_7) + timedelta(days=30)).strftime("%Y-%m-%d")

    licenses[str(member.id)] = {"key": license_key, "expiry": expiry_date}
    await save_licenses()

    embed = discord.Embed(title="🎟 Lisensi Dibuat", color=discord.Color.green())
    embed.add_field(name="🔑 Kode", value=f"`{license_key}`", inline=False)
    embed.add_field(name="📅 Berlaku hingga", value=expiry_date, inline=False)
    embed.set_footer(text=f"Dibuat untuk {member.name}")

    license_channel = bot.get_channel(LICENSE_CHANNEL_ID)
    if license_channel:
        await license_channel.send(embed=embed)

    try:
        await member.send(embed=embed)
    except:
        await ctx.send(f"⚠️ Tidak bisa mengirim DM ke {member.mention}, pastikan DM terbuka!")

    await ctx.message.delete(delay=3)
    await ctx.send(f"✅ Lisensi untuk {member.mention} berhasil dibuat!", delete_after=5)

async def handle_request(request):
    """API untuk mendapatkan script berdasarkan lisensi."""
    data = await request.json()
    user_id = str(data.get("user_id"))
    license_key = data.get("license_key")

    if user_id not in licenses:
        return web.json_response({"valid": False, "error": "Lisensi tidak valid!"})

    stored_key = licenses[user_id]["key"]
    expiry_date = datetime.strptime(licenses[user_id]["expiry"], "%Y-%m-%d").replace(tzinfo=UTC_PLUS_7)

    if license_key != stored_key or expiry_date < datetime.now(UTC_PLUS_7):
        return web.json_response({"valid": False, "error": "Lisensi sudah kadaluarsa!"})

    script_channel = bot.get_channel(SCRIPT_CHANNEL_ID)
    if not script_channel:
        return web.json_response({"valid": False, "error": "Channel script tidak ditemukan!"})

    async for message in script_channel.history(limit=10):
        if message.attachments:
            for attachment in message.attachments:
                if attachment.filename.endswith(".lua"):
                    script_content = await attachment.read()
                    return web.json_response({"valid": True, "script": script_content.decode("utf-8")})

    return web.json_response({"valid": False, "error": "File script tidak ditemukan!"})

app = web.Application()
app.router.add_post("/get_script", handle_request)

async def start_webserver():
    """Menjalankan webserver untuk API."""
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 5000)
    await site.start()

async def main():
    """Menjalankan bot dan webserver."""
    async with bot:
        bot.loop.create_task(start_webserver())
        await bot.start(TOKEN)

asyncio.run(main())

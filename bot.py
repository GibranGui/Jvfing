import discord
from discord.ext import commands
from aiohttp import web
import random
import string
import datetime
import os
import asyncio

TOKEN = os.getenv("TOKEN")
ADMIN_ROLE_NAME = "Admin"
SCRIPT_CHANNEL_ID = 1355918124238770288
LICENSE_CHANNEL_ID = 1355918237178528009
DATABASE_CHANNEL_ID = 1355918237178528009  # Ganti dengan ID channel database

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
licenses = {}

async def load_licenses():
    """Muat lisensi dari channel database."""
    global licenses
    licenses = {}
    database_channel = bot.get_channel(DATABASE_CHANNEL_ID)
    if database_channel:
        async for message in database_channel.history(oldest_first=True):
            try:
                user_id, license_key, expiry_date = message.content.split("|")
                licenses[user_id] = {"key": license_key, "expiry": expiry_date}
            except ValueError:
                print(f"⚠️ Format salah di database: {message.content}")

async def save_licenses():
    """Simpan lisensi ke channel database."""
    database_channel = bot.get_channel(DATABASE_CHANNEL_ID)
    if database_channel:
        await database_channel.purge()
        for user_id, data in licenses.items():
            await database_channel.send(f"{user_id}|{data['key']}|{data['expiry']}")

@bot.event
async def on_ready():
    await load_licenses()
    print(f"{bot.user} siap! Lisensi dimuat dari database Discord.")

@bot.command()
async def generate_license(ctx, member: discord.Member):
    if ADMIN_ROLE_NAME in [role.name for role in ctx.author.roles]:
        license_key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
        expiry_date = (datetime.datetime.utcnow() + datetime.timedelta(days=30)).strftime("%Y-%m-%d")
        
        licenses[str(member.id)] = {"key": license_key, "expiry": expiry_date}
        await save_licenses()
        
        license_channel = bot.get_channel(LICENSE_CHANNEL_ID)
        await license_channel.send(f"🎟 **Lisensi Dibuat** untuk {member.mention}\n🔑 **Kode**: `{license_key}`\n📅 **Berlaku hingga**: {expiry_date}")
        
        try:
            await member.send(f"🔑 **Lisensi Anda**: `{license_key}`\n📅 **Berlaku hingga**: {expiry_date}")
        except:
            await ctx.send(f"⚠️ Tidak bisa mengirim DM ke {member.mention}, pastikan DM terbuka!")
        
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

async def main():
    async with bot:
        bot.loop.create_task(start_webserver())
        await bot.start(TOKEN)

asyncio.run(main())

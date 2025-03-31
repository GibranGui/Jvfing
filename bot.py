import discord
from discord.ext import commands
from aiohttp import web
import json
import random
import string
from datetime import datetime, timedelta, timezone
import os
import asyncio

# Konfigurasi
TOKEN = os.getenv("TOKEN")
ADMIN_ROLE_NAME = "Admin"
SCRIPT_CHANNEL_ID = 1355918124238770288
DATABASE_CHANNEL_ID = 1355918237178528009  # Ganti dengan ID channel database

UTC_PLUS_7 = timezone(timedelta(hours=7))

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
        self.licenses = {}

    async def setup_hook(self):
        print("🔄 Memuat lisensi...")
        await self.load_licenses()
        print("✅ Lisensi dimuat!")
        
        print("🚀 Menjalankan webserver...")
        asyncio.create_task(start_webserver(self))

    async def load_licenses(self):
        """Muat lisensi dari channel database."""
        try:
            database_channel = await self.fetch_channel(DATABASE_CHANNEL_ID)
        except discord.NotFound:
            print("⚠️ Database channel tidak ditemukan!")
            return
        except discord.Forbidden:
            print("❌ Bot tidak memiliki izin untuk mengakses channel database!")
            return

        async for message in database_channel.history(oldest_first=True):
            content = message.content.strip()

            # Periksa dan hapus blok kode JSON jika ada
            if content.startswith("```json") and content.endswith("```"):
                content = content[7:-3].strip()

            try:
                data = json.loads(content)
                if "user_id" in data and "key" in data and "expiry" in data:
                    self.licenses[data["user_id"]] = {
                        "key": data["key"],
                        "expiry": data["expiry"]
                    }
                else:
                    print(f"⚠️ Format JSON tidak lengkap: {message.content}")
            except json.JSONDecodeError:
                print(f"⚠️ Format JSON salah: {message.content}")

    async def save_licenses(self):
        """Simpan lisensi ke channel database."""
        try:
            database_channel = await self.fetch_channel(DATABASE_CHANNEL_ID)
        except discord.NotFound:
            print("⚠️ Database channel tidak ditemukan!")
            return
        except discord.Forbidden:
            print("❌ Bot tidak memiliki izin untuk mengakses channel database!")
            return
        
        await database_channel.purge()
        for user_id, data in self.licenses.items():
            license_data = json.dumps({
                "user_id": user_id,
                "key": data["key"],
                "expiry": data["expiry"]
            })
            await database_channel.send(f"```json\n{license_data}\n```")

bot = MyBot()

@bot.command()
async def generate_license(ctx, member: discord.Member):
    """Generate lisensi untuk member."""
    if ADMIN_ROLE_NAME not in [role.name for role in ctx.author.roles]:
        await ctx.send("❌ Anda tidak memiliki izin!", delete_after=5)
        return

    license_key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))  
    expiry_date = (datetime.now(UTC_PLUS_7) + timedelta(days=30)).strftime("%Y-%m-%d")  

    bot.licenses[str(member.id)] = {"key": license_key, "expiry": expiry_date}  
    await bot.save_licenses()  

    embed = discord.Embed(title="🎟 Lisensi Dibuat", color=discord.Color.green())  
    embed.add_field(name="🔑 Kode", value=f"`{license_key}`", inline=False)  
    embed.add_field(name="📅 Berlaku hingga", value=expiry_date, inline=False)  
    embed.set_footer(text=f"Dibuat untuk {member.name}")  

    try:
        await member.send(embed=embed)
    except:
        await ctx.send(f"⚠️ Tidak bisa mengirim DM ke {member.mention}, pastikan DM terbuka!")  

    await ctx.message.delete(delay=3)  
    await ctx.send(f"✅ Lisensi untuk {member.mention} berhasil dibuat!", delete_after=5)

async def handle_request(request):
    """API untuk mendapatkan script berdasarkan lisensi."""
    bot = request.app["bot"]
    data = await request.json()
    user_id = str(data.get("user_id"))
    license_key = data.get("license_key")

    if user_id not in bot.licenses:
        return web.json_response({"valid": False, "error": "Lisensi tidak valid!"})

    stored_key = bot.licenses[user_id]["key"]
    expiry_date = datetime.strptime(bot.licenses[user_id]["expiry"], "%Y-%m-%d").replace(tzinfo=UTC_PLUS_7)

    if license_key != stored_key or expiry_date < datetime.now(UTC_PLUS_7):
        return web.json_response({"valid": False, "error": "Lisensi sudah kadaluarsa!"})

    try:
        script_channel = await bot.fetch_channel(SCRIPT_CHANNEL_ID)
    except discord.NotFound:
        return web.json_response({"valid": False, "error": "Channel script tidak ditemukan!"})

    async for message in script_channel.history(limit=10):
        if message.attachments:
            for attachment in message.attachments:
                if attachment.filename.endswith(".lua"):
                    script_content = await attachment.read()
                    return web.json_response({"valid": True, "script": script_content.decode("utf-8")})

    return web.json_response({"valid": False, "error": "File script tidak ditemukan!"})

async def start_webserver(bot):
    """Menjalankan webserver untuk API."""
    app = web.Application()
    app["bot"] = bot
    app.router.add_post("/get_script", handle_request)

    runner = web.AppRunner(app)  
    await runner.setup()  
    site = web.TCPSite(runner, "0.0.0.0", 5000)  
    await site.start()  
    print("🌐 Webserver berjalan di port 5000...")

bot.run(TOKEN)

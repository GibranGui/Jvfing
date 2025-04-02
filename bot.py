import discord
from discord.ext import commands
from aiohttp import web
import json
import random
import string
from datetime import datetime, timedelta, timezone
import os
import asyncio
import aiofiles

# Konfigurasi
TOKEN = os.getenv("TOKEN")
ADMIN_ROLE_NAME = "Owner"
SALES_ROLE_NAME = "Salles Man"
SCRIPT_CHANNEL_ID = 1355918124238770288
DATABASE_CHANNEL_ID = 1355918237178528009  # Ganti dengan ID channel database
SALES_LIMIT_CHANNEL_ID = 1357006827937595624  # Ganti dengan ID channel batasan admin sales
GENERATE_LICENSE_CHANNEL_ID = 1357006983701598319  # Ganti dengan ID channel khusus generate lisensi

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
                if "user_id" in data and "key" in data:
                    self.licenses[data["user_id"]] = {
                        "key": data["key"],
                        "expiry": data.get("expiry"),
                        "used_on": data.get("used_on")  # Menambahkan informasi waktu penggunaan
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
                "expiry": data["expiry"],
                "used_on": data["used_on"]
            })
            await database_channel.send(f"```json\n{license_data}\n```")

bot = MyBot()

@bot.command()
async def generate_license(ctx, member: discord.Member):
    """Generate lisensi untuk member."""
    if ADMIN_ROLE_NAME not in [role.name for role in ctx.author.roles] and SALES_ROLE_NAME not in [role.name for role in ctx.author.roles]:
        await ctx.send("❌ Anda tidak memiliki izin!", delete_after=5)
        return

    # Cek batasan untuk Admin Sales
    if SALES_ROLE_NAME in [role.name for role in ctx.author.roles]:
        limit = await get_sales_limit(ctx.author.id)
        if limit <= 0:
            await ctx.send("❌ Anda sudah mencapai batas lisensi yang dapat dibuat!", delete_after=5)
            return
        else:
            await decrement_sales_limit(ctx.author.id)  # Kurangi batasan lisensi

    license_key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))  
    used_on = datetime.now(UTC_PLUS_7).strftime("%Y-%m-%d %H:%M:%S")  
    expiry_date = (datetime.now(UTC_PLUS_7) + timedelta(days=30)).strftime("%Y-%m-%d")  

    bot.licenses[str(member.id)] = {
        "key": license_key, 
        "expiry": expiry_date,  
        "used_on": used_on  # Menyimpan waktu penggunaan
    }  
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

async def get_sales_limit(user_id):
    """Mendapatkan limit lisensi dari channel batasan admin sales."""
    try:
        sales_limit_channel = await bot.fetch_channel(SALES_LIMIT_CHANNEL_ID)
        async for message in sales_limit_channel.history(oldest_first=True):
            content = message.content.strip()

            if content.startswith("```json") and content.endswith("```"):
                content = content[7:-3].strip()

            try:
                data = json.loads(content)
                if str(user_id) in data:
                    return data[str(user_id)]["limit"]
            except json.JSONDecodeError:
                continue
    except discord.NotFound:
        print("⚠️ Sales Limit channel tidak ditemukan!")
    except discord.Forbidden:
        print("❌ Bot tidak memiliki izin untuk mengakses channel Sales Limit!")

    return 0  # Default jika tidak ada data

async def decrement_sales_limit(user_id):
    """Mengurangi batas lisensi Admin Sales di channel Sales Limit."""
    try:
        sales_limit_channel = await bot.fetch_channel(SALES_LIMIT_CHANNEL_ID)
        async for message in sales_limit_channel.history(oldest_first=True):
            content = message.content.strip()

            if content.startswith("```json") and content.endswith("```"):
                content = content[7:-3].strip()

            try:
                data = json.loads(content)
                if str(user_id) in data:
                    data[str(user_id)]["limit"] -= 1  # Mengurangi limit lisensi
                    await sales_limit_channel.purge()
                    await sales_limit_channel.send(f"```json\n{json.dumps(data, indent=4)}\n```")
                    return
            except json.JSONDecodeError:
                continue
    except discord.NotFound:
        print("⚠️ Sales Limit channel tidak ditemukan!")
    except discord.Forbidden:
        print("❌ Bot tidak memiliki izin untuk mengakses channel Sales Limit!")

async def handle_request(request):
    """API untuk mendapatkan script berdasarkan lisensi."""
    bot = request.app["bot"]
    data = await request.json()
    user_id = str(data.get("user_id"))
    license_key = data.get("license_key")

    # Cek lisensi
    if user_id not in bot.licenses:
        return web.Response(text="INVALID")

    stored_key = bot.licenses[user_id]["key"]
    used_on = datetime.strptime(bot.licenses[user_id]["used_on"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC_PLUS_7)
    expiry_date = used_on + timedelta(days=30)

    if license_key != stored_key or expiry_date < datetime.now(UTC_PLUS_7):
        return web.Response(text="INVALID")

    try:
        script_channel = await bot.fetch_channel(SCRIPT_CHANNEL_ID)
    except discord.NotFound:
        return web.Response(text="INVALID")

    async for message in script_channel.history(limit=10):
        if message.attachments:
            for attachment in message.attachments:
                if attachment.filename.endswith(".lua"):
                    return web.Response(text=attachment.url)  # Kirim langsung URL file

    return web.Response(text="INVALID")  # Jika tidak ada file script
    
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

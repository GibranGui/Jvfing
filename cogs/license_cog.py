import discord
from discord.ext import commands
import random
import string
from datetime import datetime, timedelta
import logging

# Impor dari file lain dalam proyek
from config import ADMIN_ROLE_ID, SALES_ROLE_ID, PURCHASE_LOG_CHANNEL_ID, UTC_PLUS_7, LICENSE_DURATION_DAYS, PURCHASED_LICENSE_ROLE_ID
from database import (
    add_or_update_license,
    get_sales_limit_db,
    decrement_sales_limit_db,
    set_sales_limit_db
)

log = logging.getLogger(__name__)

class LicenseCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_pool = bot.db_pool
        log.info("License Cog loaded.")

    async def log_purchase(self, generator: discord.Member, recipient: discord.Member, expiry_dt: datetime, key: str, script_name: str = None):
        """Mengirim log ke channel purchase-log."""
        try:
            log_channel = self.bot.get_channel(PURCHASE_LOG_CHANNEL_ID)
            if not log_channel:
                log_channel = await self.bot.fetch_channel(PURCHASE_LOG_CHANNEL_ID)

            if log_channel and isinstance(log_channel, discord.TextChannel):
                embed = discord.Embed(
                    title="✅ Log Pembuatan Lisensi",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(UTC_PLUS_7)
                )
                embed.add_field(name="Generator", value=f"{generator.mention} ({generator.id})", inline=False)
                embed.add_field(name="Penerima", value=f"{recipient.mention} ({recipient.id})", inline=False)
                embed.add_field(name="Kunci Lisensi", value=f"`{key}`", inline=False)
                embed.add_field(name="Berlaku Hingga", value=expiry_dt.strftime("%Y-%m-%d %H:%M:%S %Z"), inline=False)
                if script_name:
                    embed.add_field(name="Script Dilisensikan", value=f"`{script_name}`", inline=False)
                await log_channel.send(embed=embed)
            else:
                 log.warning(f"Channel log pembelian (ID: {PURCHASE_LOG_CHANNEL_ID}) tidak ditemukan atau bukan text channel.")

        except discord.NotFound:
            log.error(f"Channel log pembelian (ID: {PURCHASE_LOG_CHANNEL_ID}) tidak ditemukan.")
        except discord.Forbidden:
            log.error(f"Bot tidak punya izin mengirim pesan ke channel log pembelian (ID: {PURCHASE_LOG_CHANNEL_ID}).")
        except Exception as e:
            log.error(f"Gagal mengirim log pembelian: {e}")

    @commands.command(name='generate_license', help='Generate lisensi untuk member (!generate_license @member [nama_script])')
    @commands.has_any_role(ADMIN_ROLE_ID, SALES_ROLE_ID)
    async def generate_license(self, ctx: commands.Context, member: discord.Member, script_name: str = None):
        """Generate lisensi untuk member dan simpan ke Supabase."""
        author_roles_ids = [role.id for role in ctx.author.roles]
        is_admin = ADMIN_ROLE_ID in author_roles_ids
        is_sales = SALES_ROLE_ID in author_roles_ids

        if not self.db_pool:
            log.error(f"Database pool tidak tersedia saat {ctx.author} mencoba generate lisensi.")
            await ctx.send("❌ Kesalahan: Koneksi database tidak tersedia. Hubungi pengembang.", delete_after=10)
            return

        if is_sales and not is_admin:
            sales_user_id_str = str(ctx.author.id)
            limit = await get_sales_limit_db(self.db_pool, sales_user_id_str)

            if limit is None:
                await ctx.send("⚠️ Tidak bisa memeriksa limit Sales Anda saat ini. Hubungi Admin.", delete_after=10)
                return
            if limit <= 0:
                await ctx.send("❌ Anda sudah mencapai batas lisensi yang dapat dibuat!", delete_after=5)
                return

            decrement_success = await decrement_sales_limit_db(self.db_pool, sales_user_id_str)
            if not decrement_success:
                 await ctx.send("❌ Gagal mengurangi limit Anda (kemungkinan limit sudah 0 atau error DB).", delete_after=10)
                 return
            log.info(f"Sales limit untuk {ctx.author} ({sales_user_id_str}) berhasil dikurangi.")

        license_key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
        now_wib = datetime.now(UTC_PLUS_7)
        expiry_datetime = now_wib + timedelta(days=LICENSE_DURATION_DAYS)
        user_id_str = str(member.id)

        save_success = await add_or_update_license(self.db_pool, user_id_str, license_key, expiry_datetime, now_wib, script_name=script_name)

        if not save_success:
            await ctx.send("⚠️ Terjadi kesalahan saat menyimpan lisensi ke database.", delete_after=10)
            return

        await self.log_purchase(ctx.author, member, expiry_datetime, license_key, script_name)

        embed = discord.Embed(title="🎟️ Lisensi Dibuat", color=discord.Color.green())
        embed.add_field(name="🔑 Kode", value=f"`{license_key}`", inline=False)
        expiry_display = expiry_datetime.strftime("%Y-%m-%d")
        embed.add_field(name="📅 Berlaku hingga", value=expiry_display, inline=False)
        if script_name:
            embed.add_field(name="📜 Script Dilisensikan", value=f"`{script_name}`", inline=False)
        embed.set_footer(text=f"Diberikan oleh {ctx.author.display_name}")

        try:
            await member.send(embed=embed)
            dm_success = True
        except discord.Forbidden:
            dm_success = False
            await ctx.send(f"⚠️ Tidak bisa mengirim DM ke {member.mention}, pastikan DM terbuka!", delete_after=15)
        except Exception as e:
            dm_success = False
            log.error(f"Gagal mengirim DM lisensi ke {member.id}: {e}")
            await ctx.send(f"⚠️ Gagal mengirim DM ke {member.mention}.", delete_after=15)

        purchased_role_id = PURCHASED_LICENSE_ROLE_ID
        if purchased_role_id:
            role = ctx.guild.get_role(purchased_role_id)
            if role:
                try:
                    await member.add_roles(role, reason="Pembelian Lisensi")
                    log.info(f"Peran '{role.name}' berhasil diatribusikan kepada {member.display_name} ({member.id}) pasca aku
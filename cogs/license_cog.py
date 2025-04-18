import discord
from discord.ext import commands
import random
import string
from datetime import datetime, timedelta
import logging

# Impor dari file lain dalam proyek
from config import ADMIN_ROLE_ID, SALES_ROLE_ID, PURCHASE_LOG_CHANNEL_ID, UTC_PLUS_7, LICENSE_DURATION_DAYS, PURCHASED_LICENSE_ROLE_ID
from database import (
    add_license,
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

    async def log_purchase(self, generator: discord.Member, recipient: discord.Member, key: str, script_name: str):
        """Mengirim log ke channel purchase-log."""
        try:
            log_channel = self.bot.get_channel(PURCHASE_LOG_CHANNEL_ID)
            if not log_channel:
                log_channel = await self.bot.fetch_channel(PURCHASE_LOG_CHANNEL_ID)

            if log_channel and isinstance(log_channel, discord.TextChannel):
                embed = discord.Embed(
                    title="✅ Log Pembelian Lisensi",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(UTC_PLUS_7)
                )
                embed.add_field(name="Generator", value=f"{generator.mention}", inline=False)
                embed.add_field(name="Penerima", value=f"{recipient.mention}", inline=False)
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

    @commands.command(name='generate_license', help='Generate lisensi untuk member (!generate_license @member nama_script)')
    @commands.has_any_role(ADMIN_ROLE_ID, SALES_ROLE_ID)
    async def generate_license(self, ctx: commands.Context, member: discord.Member, script_name: str):
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

        save_success = await add_license(self.db_pool, license_key, script_name)

        if not save_success:
            await ctx.send(f"⚠️ Terjadi kesalahan saat menyimpan lisensi '{license_key}' untuk '{script_name}' ke database (kemungkinan kunci sudah ada).", delete_after=10)
            return

        await self.log_purchase(ctx.author, member, license_key, script_name)

        embed = discord.Embed(title="🎟️ Lisensi Dibuat", color=discord.Color.green())
        embed.add_field(name="🔑 Kode Lisensi", value=f"`{license_key}`", inline=False)
        embed.add_field(name="📜 Script", value=f"`{script_name}`", inline=False)
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

        await ctx.message.delete(delay=3)
        confirm_msg = f"✅ Lisensi `{license_key}` untuk `{script_name}` berhasil dibuat dan dikirim ke {member.mention}!"
        if not dm_success:
            confirm_msg += " (Gagal kirim DM)"
        await ctx.send(confirm_msg, delete_after=10)

    @generate_license.error
    async def generate_license_error(self, ctx: commands.Context, error):
        """Error handler untuk generate_license."""
        original_error = getattr(error, 'original', error)
        log.warning(f"Error pada perintah !generate_license oleh {ctx.author}: {error} (Original: {original_error})")

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Penggunaan salah. Contoh: `{ctx.prefix}generate_license @NamaMember nama_script`", delete_after=10)
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(f"❌ Member Discord `{error.argument}` tidak ditemukan.", delete_after=10)
        elif isinstance(error, commands.MissingAnyRole):
            await ctx.send("❌ Anda tidak memiliki izin untuk menggunakan perintah ini.", delete_after=5)
        else:
            await ctx.send("❌ Terjadi error internal saat memproses perintah.", delete_after=10)

        try:
            await ctx.message.delete(delay=3)
        except discord.HTTPException:
            pass

async def setup(bot: commands.Bot):
    await bot.add_cog(LicenseCog(bot))
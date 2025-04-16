import asyncpg
import logging
from typing import Optional, Dict, Any
from datetime import datetime

log = logging.getLogger(__name__)

# --- Fungsi Helper Database ---

async def get_db_pool(database_url: str) -> Optional[asyncpg.Pool]:
    """Membuat dan mengembalikan database connection pool."""
    pool = None
    try:
        pool = await asyncpg.create_pool(
            database_url,
            min_size=1,
            max_size=10,
            command_timeout=60 # Timeout untuk command
        )
        # Uji koneksi
        async with pool.acquire() as connection:
            val = await connection.fetchval('SELECT 1')
            if val == 1:
                log.info("Koneksi database pool Supabase berhasil dibuat dan diverifikasi.")
                return pool
            else:
                log.error("Verifikasi koneksi database pool gagal.")
                await pool.close()
                return None
    except Exception as e:
        log.error(f"Gagal membuat koneksi database pool: {e}")
        if pool:
            await pool.close()
        return None

async def close_db_pool(pool: asyncpg.Pool):
    """Menutup database connection pool."""
    if pool:
        try:
            await pool.close()
            log.info("Koneksi database pool ditutup.")
        except Exception as e:
            log.error(f"Error saat menutup database pool: {e}")

# --- Operasi Tabel Licenses ---

async def add_or_update_license(pool: asyncpg.Pool, user_id: str, key: str, expiry: datetime, used_on: datetime, script_name: Optional[str] = None) -> bool:
    """Menyimpan atau memperbarui lisensi di database."""
    sql = """
    INSERT INTO licenses (user_id, key, expiry, used_on, script_name)
    VALUES ($1, $2, $3, $4, $5)
    ON CONFLICT (user_id) DO UPDATE SET
        key = EXCLUDED.key,
        expiry = EXCLUDED.expiry,
        used_on = EXCLUDED.used_on,
        script_name = EXCLUDED.script_name;
    """
    try:
        async with pool.acquire() as connection:
            await connection.execute(sql, user_id, key, expiry, used_on, script_name)
        log.info(f"Lisensi untuk {user_id} disimpan/diupdate ke database.")
        return True
    except Exception as e:
        log.error(f"Gagal menyimpan/update lisensi ke database untuk {user_id}: {e}")
        return False

async def fetch_license(pool: asyncpg.Pool, user_id: str) -> Optional[Dict[str, Any]]:
    """Mengambil data lisensi dari database berdasarkan user_id."""
    sql = "SELECT key, expiry, used_on, script_name FROM licenses WHERE user_id = $1;"
    try:
        async with pool.acquire() as connection:
            result = await connection.fetchrow(sql, user_id)
            return dict(result) if result else None
    except Exception as e:
        log.error(f"Gagal mengambil lisensi dari database untuk {user_id}: {e}")
        return None

# --- Operasi Tabel Sales Limits ---

async def get_sales_limit_db(pool: asyncpg.Pool, sales_user_id: str) -> Optional[int]:
    """Mendapatkan limit sales dari database."""
    sql = "SELECT current_limit FROM sales_limits WHERE sales_user_id = $1;"
    try:
        async with pool.acquire() as connection:
            result = await connection.fetchval(sql, sales_user_id)
            # fetchval mengembalikan None jika tidak ada baris atau kolom null
            return result if result is not None else 0 # Default 0 jika user tidak ditemukan
    except Exception as e:
        log.error(f"Gagal mengambil limit sales dari database untuk {sales_user_id}: {e}")
        return None # Indikasi error

async def decrement_sales_limit_db(pool: asyncpg.Pool, sales_user_id: str) -> bool:
    """Mengurangi limit sales di database secara aman."""
    # Menggunakan UPDATE ... RETURNING untuk memastikan limit > 0 sebelum dikurangi
    # dan mendapatkan nilai baru, atau tahu jika tidak ada baris yg terupdate.
    sql = """
    UPDATE sales_limits
    SET current_limit = current_limit - 1
    WHERE sales_user_id = $1 AND current_limit > 0
    RETURNING current_limit;
    """
    try:
        async with pool.acquire() as connection:
            # fetchval akan mengembalikan limit baru jika update berhasil, None jika tidak
            new_limit = await connection.fetchval(sql, sales_user_id)
            if new_limit is not None:
                log.info(f"Limit sales untuk {sales_user_id} dikurangi menjadi {new_limit}.")
                return True # Pengurangan berhasil
            else:
                # Ini terjadi jika limit awal sudah 0 atau user tidak ditemukan
                log.warning(f"Gagal mengurangi limit sales untuk {sales_user_id} (limit 0 atau user tidak ada).")
                return False # Pengurangan gagal (limit 0 atau user tdk ada)
    except Exception as e:
        log.error(f"Gagal mengurangi limit sales di database untuk {sales_user_id}: {e}")
        return False # Error database

async def set_sales_limit_db(pool: asyncpg.Pool, sales_user_id: str, new_limit: int) -> bool:
    """Menetapkan limit sales baru (untuk command admin)."""
    if new_limit < 0:
        log.error("Limit baru tidak boleh negatif.")
        return False

    # Gunakan UPSERT untuk insert jika belum ada, atau update jika sudah ada
    sql = """
    INSERT INTO sales_limits (sales_user_id, current_limit)
    VALUES ($1, $2)
    ON CONFLICT (sales_user_id) DO UPDATE SET
        current_limit = EXCLUDED.current_limit;
    """
    try:
        async with pool.acquire() as connection:
            await connection.execute(sql, sales_user_id, new_limit)
        log.info(f"Limit sales untuk {sales_user_id} ditetapkan menjadi {new_limit}.")
        return True
    except Exception as e:
        log.error(f"Gagal menetapkan limit sales di database untuk {sales_user_id}: {e}")
        return False
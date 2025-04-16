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

# --- Operasi Tabel Licenses (TANPA user_id) ---

async def create_licenses_table(pool):
    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS licenses (
                key VARCHAR(255) PRIMARY KEY,
                script_name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        ''')
        log.info("Tabel 'licenses' berhasil dibuat atau sudah ada.")

async def add_license(pool: asyncpg.Pool, key: str, script_name: str) -> bool:
    """Menyimpan lisensi ke database."""
    sql = """
    INSERT INTO licenses (key, script_name)
    VALUES ($1, $2)
    ON CONFLICT (key) DO NOTHING; -- Jika key sudah ada, abaikan
    """
    try:
        async with pool.acquire() as connection:
            await connection.execute(sql, key, script_name)
        log.info(f"Lisensi '{key}' untuk '{script_name}' disimpan ke database.")
        return True
    except Exception as e:
        log.error(f"Gagal menyimpan lisensi '{key}' ke database: {e}")
        return False

async def fetch_script_by_license(pool: asyncpg.Pool, key: str) -> Optional[str]:
    """Mengambil nama script dari database berdasarkan key lisensi."""
    sql = "SELECT script_name FROM licenses WHERE key = $1;"
    try:
        async with pool.acquire() as connection:
            result = await connection.fetchrow(sql, key)
            return result['script_name'] if result else None
    except Exception as e:
        log.error(f"Gagal mengambil script berdasarkan key '{key}' dari database: {e}")
        return None

# --- Operasi Tabel Sales Limits (TIDAK BERUBAH) ---

async def get_sales_limit_db(pool: asyncpg.Pool, sales_user_id: str) -> Optional[int]:
    """Mendapatkan limit sales dari database."""
    sql = "SELECT current_limit FROM sales_limits WHERE sales_user_id = $1;"
    try:
        async with pool.acquire() as connection:
            result = await connection.fetchval(sql, sales_user_id)
            return result if result is not None else 0
    except Exception as e:
        log.error(f"Gagal mengambil limit sales dari database untuk {sales_user_id}: {e}")
        return None

async def decrement_sales_limit_db(pool: asyncpg.Pool, sales_user_id: str) -> bool:
    """Mengurangi limit sales di database secara aman."""
    sql = """
    UPDATE sales_limits
    SET current_limit = current_limit - 1
    WHERE sales_user_id = $1 AND current_limit > 0
    RETURNING current_limit;
    """
    try:
        async with pool.acquire() as connection:
            new_limit = await connection.fetchval(sql, sales_user_id)
            return True if new_limit is not None else False
    except Exception as e:
        log.error(f"Gagal mengurangi limit sales di database untuk {sales_user_id}: {e}")
        return False

async def set_sales_limit_db(pool: asyncpg.Pool, sales_user_id: str, new_limit: int) -> bool:
    """Menetapkan limit sales baru (untuk command admin)."""
    if new_limit < 0:
        log.error("Limit baru tidak boleh negatif.")
        return False
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
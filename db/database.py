import aiosqlite
import discord
import os

from config.constants import EMBED_COLOR

# Global database connection
db = None

DB_FILE = os.path.join(os.path.dirname(__file__), "database.db")

async def initialize_databases():
    global db
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    
    db = await aiosqlite.connect(DB_FILE)
    
    # Create tables in the single database file
    await db.execute("""
        CREATE TABLE IF NOT EXISTS user_roles (
            guild_id INTEGER,
            user_id INTEGER,
            role_id INTEGER,
            PRIMARY KEY (guild_id, user_id)
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS lobbies (
            guild_id   INTEGER NOT NULL,
            channel_id INTEGER PRIMARY KEY
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS server_settings (
            guild_id INTEGER PRIMARY KEY,
            embed_color TEXT,
            updated_by INTEGER,
            welcome_channel_id INTEGER,
            log_channel_id INTEGER
        )
    """)

    # Older databases created before log_channel_id existed need it backfilled.
    try:
        await db.execute("ALTER TABLE server_settings ADD COLUMN log_channel_id INTEGER")
    except aiosqlite.OperationalError:
        pass

    await db.execute("""
        CREATE TABLE IF NOT EXISTS autoroles (
            guild_id INTEGER,
            role_id INTEGER,
            PRIMARY KEY (guild_id, role_id)
        )
    """)

    await db.commit()

async def close_all_databases():
    """Closes the database connection gracefully."""
    global db
    if db:
        await db.close()
        print("Database connection closed.")

async def store_user_role(guild_id: int, user_id: int, role_id: int):
    await db.execute(
        "INSERT OR REPLACE INTO user_roles (guild_id, user_id, role_id) VALUES (?, ?, ?)",
        (guild_id, user_id, role_id)
    )
    await db.commit()

async def remove_user_role(guild_id: int, user_id: int):
    await db.execute(
        "DELETE FROM user_roles WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id)
    )
    await db.commit()

async def get_user_role(guild_id: int, user_id: int):
    async with db.execute(
        "SELECT role_id FROM user_roles WHERE guild_id = ? AND user_id = ?", 
        (guild_id, user_id)
    ) as cursor:
        result = await cursor.fetchone()
        return result[0] if result else None

async def lobby_add(guild_id: int, channel_id: int):
    await db.execute("INSERT OR REPLACE INTO lobbies (guild_id, channel_id) VALUES (?, ?)", (guild_id, channel_id))
    await db.commit()

async def lobby_delete(channel_id: int):
    await db.execute("DELETE FROM lobbies WHERE channel_id = ?", (channel_id,))
    await db.commit()

async def lobbies_all():
    async with db.execute("SELECT guild_id, channel_id FROM lobbies") as cursor:
        return await cursor.fetchall()

async def lobby_is_tracked(channel_id: int) -> bool:
    async with db.execute("SELECT 1 FROM lobbies WHERE channel_id = ? LIMIT 1", (channel_id,)) as cursor:
        return await cursor.fetchone() is not None

async def set_embed_color(guild_id: int, hex_code: str, user_id: int):
    await db.execute(
        """
        INSERT INTO server_settings (guild_id, embed_color, updated_by) VALUES (?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET embed_color=excluded.embed_color, updated_by=excluded.updated_by
        """,
        (guild_id, hex_code, user_id)
    )
    await db.commit()

async def get_embed_color(guild_id: int):
    async with db.execute("SELECT embed_color FROM server_settings WHERE guild_id = ?", (guild_id,)) as cursor:
        result = await cursor.fetchone()
        return result[0] if result else None

async def get_guild_embed_color(guild_id: int) -> discord.Color:
    db_color = await get_embed_color(guild_id)
    if db_color:
        return discord.Color(int(db_color, 16))
    return discord.Color(EMBED_COLOR)

async def set_welcome_channel(guild_id: int, channel_id: int | None):
    await db.execute(
        """
        INSERT INTO server_settings (guild_id, welcome_channel_id) VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET welcome_channel_id=excluded.welcome_channel_id
        """,
        (guild_id, channel_id)
    )
    await db.commit()

async def get_welcome_channel(guild_id: int):
    async with db.execute("SELECT welcome_channel_id FROM server_settings WHERE guild_id = ?", (guild_id,)) as cursor:
        result = await cursor.fetchone()
        return result[0] if result else None

async def set_log_channel(guild_id: int, channel_id: int | None):
    await db.execute(
        """
        INSERT INTO server_settings (guild_id, log_channel_id) VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET log_channel_id=excluded.log_channel_id
        """,
        (guild_id, channel_id)
    )
    await db.commit()

async def get_log_channel(guild_id: int):
    async with db.execute("SELECT log_channel_id FROM server_settings WHERE guild_id = ?", (guild_id,)) as cursor:
        result = await cursor.fetchone()
        return result[0] if result else None

async def add_autorole(guild_id: int, role_id: int):
    await db.execute(
        "INSERT OR IGNORE INTO autoroles (guild_id, role_id) VALUES (?, ?)",
        (guild_id, role_id)
    )
    await db.commit()

async def remove_autorole(guild_id: int, role_id: int):
    await db.execute(
        "DELETE FROM autoroles WHERE guild_id = ? AND role_id = ?",
        (guild_id, role_id)
    )
    await db.commit()

async def get_autoroles(guild_id: int) -> list[int]:
    async with db.execute(
        "SELECT role_id FROM autoroles WHERE guild_id = ?",
        (guild_id,)
    ) as cursor:
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

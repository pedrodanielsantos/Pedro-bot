import aiosqlite
import discord
import logging
import os
import time

from config.constants import EMBED_COLOR

logger = logging.getLogger("db")

# Global database connection
db = None

DB_FILE = os.path.join(os.path.dirname(__file__), "database.db")

async def initialize_databases():
    global db
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    
    db = await aiosqlite.connect(DB_FILE)
    
    # Create tables in the single database file
    # user_roles predates autoroles and was never read anywhere; drop it if it's still around.
    await db.execute("DROP TABLE IF EXISTS user_roles")

    await db.execute("""
        CREATE TABLE IF NOT EXISTS lobbies (
            guild_id   INTEGER NOT NULL,
            channel_id INTEGER PRIMARY KEY
        )
    """)

    # Older databases still have this under its old name; rename before CREATE TABLE
    # IF NOT EXISTS below runs, since ALTER TABLE RENAME fails if the target already exists.
    try:
        await db.execute("ALTER TABLE server_settings RENAME TO guild_data")
    except aiosqlite.OperationalError:
        pass

    await db.execute("""
        CREATE TABLE IF NOT EXISTS guild_data (
            guild_id INTEGER PRIMARY KEY,
            embed_color TEXT,
            updated_by INTEGER,
            welcome_channel_id INTEGER,
            commands_log_channel_id INTEGER,
            moderation_log_channel_id INTEGER,
            case_counter INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Older databases predate the commands/moderation log split and the case counter.
    # log_channel_id becomes commands_log_channel_id; every ALTER is a no-op once applied.
    try:
        await db.execute("ALTER TABLE guild_data RENAME COLUMN log_channel_id TO commands_log_channel_id")
    except aiosqlite.OperationalError:
        pass
    try:
        await db.execute("ALTER TABLE guild_data ADD COLUMN commands_log_channel_id INTEGER")
    except aiosqlite.OperationalError:
        pass
    try:
        await db.execute("ALTER TABLE guild_data ADD COLUMN moderation_log_channel_id INTEGER")
    except aiosqlite.OperationalError:
        pass
    try:
        await db.execute("ALTER TABLE guild_data ADD COLUMN case_counter INTEGER NOT NULL DEFAULT 0")
    except aiosqlite.OperationalError:
        pass

    await db.execute("""
        CREATE TABLE IF NOT EXISTS autoroles (
            guild_id INTEGER,
            role_id INTEGER,
            PRIMARY KEY (guild_id, role_id)
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS mod_cases (
            guild_id INTEGER NOT NULL,
            case_number INTEGER NOT NULL,
            action TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            duration TEXT,
            created_at INTEGER NOT NULL,
            PRIMARY KEY (guild_id, case_number)
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS temp_bans (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            unban_at INTEGER NOT NULL,
            case_number INTEGER,
            PRIMARY KEY (guild_id, user_id)
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS warnings (
            guild_id     INTEGER NOT NULL,
            case_number  INTEGER NOT NULL,
            target_id    INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            reason       TEXT NOT NULL,
            created_at   INTEGER NOT NULL,
            PRIMARY KEY (guild_id, case_number)
        )
    """)

    await db.commit()

async def close_all_databases():
    """Closes the database connection gracefully."""
    global db
    if db:
        await db.close()
        logger.info("Database connection closed")

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
        INSERT INTO guild_data (guild_id, embed_color, updated_by) VALUES (?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET embed_color=excluded.embed_color, updated_by=excluded.updated_by
        """,
        (guild_id, hex_code, user_id)
    )
    await db.commit()

async def get_embed_color(guild_id: int):
    async with db.execute("SELECT embed_color FROM guild_data WHERE guild_id = ?", (guild_id,)) as cursor:
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
        INSERT INTO guild_data (guild_id, welcome_channel_id) VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET welcome_channel_id=excluded.welcome_channel_id
        """,
        (guild_id, channel_id)
    )
    await db.commit()

async def get_welcome_channel(guild_id: int):
    async with db.execute("SELECT welcome_channel_id FROM guild_data WHERE guild_id = ?", (guild_id,)) as cursor:
        result = await cursor.fetchone()
        return result[0] if result else None

async def set_commands_log_channel(guild_id: int, channel_id: int | None):
    await db.execute(
        """
        INSERT INTO guild_data (guild_id, commands_log_channel_id) VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET commands_log_channel_id=excluded.commands_log_channel_id
        """,
        (guild_id, channel_id)
    )
    await db.commit()

async def get_commands_log_channel(guild_id: int):
    async with db.execute("SELECT commands_log_channel_id FROM guild_data WHERE guild_id = ?", (guild_id,)) as cursor:
        result = await cursor.fetchone()
        return result[0] if result else None

async def set_moderation_log_channel(guild_id: int, channel_id: int | None):
    await db.execute(
        """
        INSERT INTO guild_data (guild_id, moderation_log_channel_id) VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET moderation_log_channel_id=excluded.moderation_log_channel_id
        """,
        (guild_id, channel_id)
    )
    await db.commit()

async def get_moderation_log_channel(guild_id: int):
    async with db.execute("SELECT moderation_log_channel_id FROM guild_data WHERE guild_id = ?", (guild_id,)) as cursor:
        result = await cursor.fetchone()
        return result[0] if result else None

async def next_case_number(guild_id: int) -> int:
    """Atomically increments and returns the guild's next moderation case number."""
    async with db.execute(
        """
        INSERT INTO guild_data (guild_id, case_counter) VALUES (?, 1)
        ON CONFLICT(guild_id) DO UPDATE SET case_counter = guild_data.case_counter + 1
        RETURNING case_counter
        """,
        (guild_id,)
    ) as cursor:
        result = await cursor.fetchone()
    await db.commit()
    return result[0]

async def add_mod_case(guild_id: int, case_number: int, action: str, target_id: int, moderator_id: int, reason: str, duration: str | None):
    await db.execute(
        """
        INSERT INTO mod_cases (guild_id, case_number, action, target_id, moderator_id, reason, duration, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (guild_id, case_number, action, target_id, moderator_id, reason, duration, int(time.time()))
    )
    await db.commit()

async def temp_ban_add(guild_id: int, user_id: int, unban_at: int, case_number: int):
    await db.execute(
        "INSERT OR REPLACE INTO temp_bans (guild_id, user_id, unban_at, case_number) VALUES (?, ?, ?, ?)",
        (guild_id, user_id, unban_at, case_number)
    )
    await db.commit()

async def temp_ban_remove(guild_id: int, user_id: int):
    await db.execute("DELETE FROM temp_bans WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
    await db.commit()

async def delete_mod_cases(guild_id: int, case_numbers: list[int]) -> tuple[int, int, int]:
    """Deletes specific cases and resyncs the counter to the highest remaining one.

    A Warn writes the same case number to both mod_cases and warnings, so both are
    cleared. Returns (cases deleted, warnings deleted, new counter).

    The counter is resynced rather than decremented: deleting a case from the middle
    of the range must not hand the next case a number that is already taken.
    """
    placeholders = ",".join("?" * len(case_numbers))
    params = (guild_id, *case_numbers)

    async with db.execute(
        f"DELETE FROM mod_cases WHERE guild_id = ? AND case_number IN ({placeholders})", params
    ) as cursor:
        cases_deleted = cursor.rowcount

    async with db.execute(
        f"DELETE FROM warnings WHERE guild_id = ? AND case_number IN ({placeholders})", params
    ) as cursor:
        warnings_deleted = cursor.rowcount

    async with db.execute(
        """
        UPDATE guild_data
        SET case_counter = COALESCE((SELECT MAX(case_number) FROM mod_cases WHERE guild_id = ?), 0)
        WHERE guild_id = ?
        RETURNING case_counter
        """,
        (guild_id, guild_id)
    ) as cursor:
        result = await cursor.fetchone()

    await db.commit()
    return cases_deleted, warnings_deleted, result[0] if result else 0

async def reset_case_counter(guild_id: int):
    """Wipes case history and resets the counter for a guild. Testing use only."""
    await db.execute("DELETE FROM mod_cases WHERE guild_id = ?", (guild_id,))
    await db.execute(
        """
        INSERT INTO guild_data (guild_id, case_counter) VALUES (?, 0)
        ON CONFLICT(guild_id) DO UPDATE SET case_counter = 0
        """,
        (guild_id,)
    )
    await db.commit()

async def temp_bans_due(now_ts: int):
    async with db.execute("SELECT guild_id, user_id, case_number FROM temp_bans WHERE unban_at <= ?", (now_ts,)) as cursor:
        return await cursor.fetchall()

async def add_warning(guild_id: int, case_number: int, target_id: int, moderator_id: int, reason: str):
    await db.execute(
        """
        INSERT INTO warnings (guild_id, case_number, target_id, moderator_id, reason, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (guild_id, case_number, target_id, moderator_id, reason, int(time.time()))
    )
    await db.commit()

async def get_warnings(guild_id: int, target_id: int):
    async with db.execute(
        """
        SELECT case_number, moderator_id, reason, created_at FROM warnings
        WHERE guild_id = ? AND target_id = ? ORDER BY case_number
        """,
        (guild_id, target_id)
    ) as cursor:
        return await cursor.fetchall()

async def count_warnings(guild_id: int, target_id: int) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND target_id = ?",
        (guild_id, target_id)
    ) as cursor:
        result = await cursor.fetchone()
        return result[0]

async def get_all_warnings(guild_id: int):
    async with db.execute(
        """
        SELECT case_number, target_id, moderator_id, reason, created_at FROM warnings
        WHERE guild_id = ? ORDER BY target_id, case_number
        """,
        (guild_id,)
    ) as cursor:
        return await cursor.fetchall()

async def clear_warnings(guild_id: int, target_id: int):
    await db.execute("DELETE FROM warnings WHERE guild_id = ? AND target_id = ?", (guild_id, target_id))
    await db.commit()

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

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
            channel_id INTEGER PRIMARY KEY,
            lockdown   INTEGER NOT NULL DEFAULT 0
        )
    """)
    try:
        await db.execute("ALTER TABLE lobbies ADD COLUMN lockdown INTEGER NOT NULL DEFAULT 0")
    except aiosqlite.OperationalError:
        pass

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
            case_counter INTEGER NOT NULL DEFAULT 0,
            lobby_region TEXT,
            music_dj_role_id INTEGER,
            music_default_volume INTEGER,
            music_announce_channel_id INTEGER
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
    try:
        await db.execute("ALTER TABLE guild_data ADD COLUMN lobby_region TEXT")
    except aiosqlite.OperationalError:
        pass
    try:
        await db.execute("ALTER TABLE guild_data ADD COLUMN music_dj_role_id INTEGER")
    except aiosqlite.OperationalError:
        pass
    try:
        await db.execute("ALTER TABLE guild_data ADD COLUMN music_default_volume INTEGER")
    except aiosqlite.OperationalError:
        pass
    try:
        await db.execute("ALTER TABLE guild_data ADD COLUMN music_announce_channel_id INTEGER")
    except aiosqlite.OperationalError:
        pass

    # Per-user preferences, global rather than per-guild: a default here applies
    # in every guild the user creates a lobby in.
    await db.execute("""
        CREATE TABLE IF NOT EXISTS user_data (
            user_id INTEGER PRIMARY KEY,
            lobby_region TEXT
        )
    """)

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

    # AUTOINCREMENT so a deleted reminder's id is never handed to a new one,
    # since ids are shown to users and typed back into /reminder delete.
    # timezone is set by /reminder at.
    await db.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            guild_id        INTEGER NOT NULL,
            channel_id      INTEGER NOT NULL,
            content         TEXT NOT NULL,
            due_at          INTEGER NOT NULL,
            created_at      INTEGER NOT NULL,
            timezone        TEXT,
            repeat_interval INTEGER
        )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS reminders_due ON reminders (due_at)")
    await db.execute("CREATE INDEX IF NOT EXISTS reminders_owner ON reminders (guild_id, user_id)")

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

async def lobby_get_lockdown(channel_id: int) -> int:
    """Lockdown state of a lobby, 0 when off or untracked."""
    async with db.execute("SELECT lockdown FROM lobbies WHERE channel_id = ?", (channel_id,)) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0

async def lobby_set_lockdown(channel_id: int, state: int):
    await db.execute("UPDATE lobbies SET lockdown = ? WHERE channel_id = ?", (state, channel_id))
    await db.commit()

async def lobby_lockdowns():
    """(channel_id, state) for every lobby with lockdown on."""
    async with db.execute("SELECT channel_id, lockdown FROM lobbies WHERE lockdown != 0") as cursor:
        return await cursor.fetchall()

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

GUILD_SETTING_FIELDS = (
    "embed_color",
    "welcome_channel_id",
    "commands_log_channel_id",
    "moderation_log_channel_id",
    "lobby_region",
    "music_dj_role_id",
    "music_default_volume",
    "music_announce_channel_id",
)

async def get_guild_settings(guild_id: int) -> dict:
    """Every configurable guild_data field in one read. A guild with no row yet
    reads as all-unset rather than missing."""
    async with db.execute(
        f"SELECT {', '.join(GUILD_SETTING_FIELDS)} FROM guild_data WHERE guild_id = ?",
        (guild_id,)
    ) as cursor:
        row = await cursor.fetchone()
    return dict(zip(GUILD_SETTING_FIELDS, row or (None,) * len(GUILD_SETTING_FIELDS)))

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

async def count_warnings_since(guild_id: int, target_id: int, since: int) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND target_id = ? AND created_at >= ?",
        (guild_id, target_id, since)
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

async def set_guild_lobby_region(guild_id: int, region: str | None):
    await db.execute(
        """
        INSERT INTO guild_data (guild_id, lobby_region) VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET lobby_region=excluded.lobby_region
        """,
        (guild_id, region)
    )
    await db.commit()

async def get_guild_lobby_region(guild_id: int) -> str | None:
    async with db.execute("SELECT lobby_region FROM guild_data WHERE guild_id = ?", (guild_id,)) as cursor:
        result = await cursor.fetchone()
        return result[0] if result else None

async def set_user_lobby_region(user_id: int, region: str | None):
    await db.execute(
        """
        INSERT INTO user_data (user_id, lobby_region) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET lobby_region=excluded.lobby_region
        """,
        (user_id, region)
    )
    await db.commit()

async def get_user_lobby_region(user_id: int) -> str | None:
    async with db.execute("SELECT lobby_region FROM user_data WHERE user_id = ?", (user_id,)) as cursor:
        result = await cursor.fetchone()
        return result[0] if result else None

async def set_music_dj_role(guild_id: int, role_id: int | None):
    await db.execute(
        """
        INSERT INTO guild_data (guild_id, music_dj_role_id) VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET music_dj_role_id=excluded.music_dj_role_id
        """,
        (guild_id, role_id)
    )
    await db.commit()

async def get_music_dj_role(guild_id: int) -> int | None:
    async with db.execute("SELECT music_dj_role_id FROM guild_data WHERE guild_id = ?", (guild_id,)) as cursor:
        result = await cursor.fetchone()
        return result[0] if result else None

async def set_music_volume(guild_id: int, volume: int | None):
    await db.execute(
        """
        INSERT INTO guild_data (guild_id, music_default_volume) VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET music_default_volume=excluded.music_default_volume
        """,
        (guild_id, volume)
    )
    await db.commit()

async def get_music_volume(guild_id: int) -> int | None:
    async with db.execute("SELECT music_default_volume FROM guild_data WHERE guild_id = ?", (guild_id,)) as cursor:
        result = await cursor.fetchone()
        return result[0] if result else None

async def set_music_announce_channel(guild_id: int, channel_id: int | None):
    await db.execute(
        """
        INSERT INTO guild_data (guild_id, music_announce_channel_id) VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET music_announce_channel_id=excluded.music_announce_channel_id
        """,
        (guild_id, channel_id)
    )
    await db.commit()

async def get_music_announce_channel(guild_id: int) -> int | None:
    async with db.execute("SELECT music_announce_channel_id FROM guild_data WHERE guild_id = ?", (guild_id,)) as cursor:
        result = await cursor.fetchone()
        return result[0] if result else None

REMINDER_FIELDS = (
    "id", "user_id", "guild_id", "channel_id", "content",
    "due_at", "created_at", "timezone", "repeat_interval",
)
_REMINDER_COLUMNS = ", ".join(REMINDER_FIELDS)

def _reminder_row(row) -> dict | None:
    return dict(zip(REMINDER_FIELDS, row)) if row else None

async def reminder_add(
    user_id: int, guild_id: int, channel_id: int, content: str, due_at: int,
    timezone: str | None,
) -> int:
    async with db.execute(
        """
        INSERT INTO reminders (user_id, guild_id, channel_id, content, due_at, created_at, timezone)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (user_id, guild_id, channel_id, content, due_at, int(time.time()), timezone)
    ) as cursor:
        result = await cursor.fetchone()
    await db.commit()
    return result[0]

async def reminder_get(reminder_id: int, guild_id: int, user_id: int) -> dict | None:
    """One reminder, only if it belongs to user_id in guild_id."""
    async with db.execute(
        f"SELECT {_REMINDER_COLUMNS} FROM reminders WHERE id = ? AND guild_id = ? AND user_id = ?",
        (reminder_id, guild_id, user_id)
    ) as cursor:
        return _reminder_row(await cursor.fetchone())

async def reminders_for_user(guild_id: int, user_id: int) -> list[dict]:
    async with db.execute(
        f"SELECT {_REMINDER_COLUMNS} FROM reminders WHERE guild_id = ? AND user_id = ? ORDER BY due_at, id",
        (guild_id, user_id)
    ) as cursor:
        return [_reminder_row(row) for row in await cursor.fetchall()]

async def reminder_count(guild_id: int, user_id: int) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM reminders WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
    ) as cursor:
        return (await cursor.fetchone())[0]

async def reminder_next_due() -> int | None:
    """Earliest due_at across all reminders, None when there are none."""
    async with db.execute("SELECT MIN(due_at) FROM reminders") as cursor:
        return (await cursor.fetchone())[0]

async def reminders_due(now_ts: int) -> list[dict]:
    async with db.execute(
        f"SELECT {_REMINDER_COLUMNS} FROM reminders WHERE due_at <= ? ORDER BY due_at, id", (now_ts,)
    ) as cursor:
        return [_reminder_row(row) for row in await cursor.fetchall()]

async def reminder_reschedule(reminder_id: int, due_at: int) -> bool:
    """False when the reminder no longer exists."""
    async with db.execute("UPDATE reminders SET due_at = ? WHERE id = ?", (due_at, reminder_id)) as cursor:
        updated = cursor.rowcount
    await db.commit()
    return updated > 0

async def reminder_set_repeat(reminder_id: int, interval: int):
    await db.execute("UPDATE reminders SET repeat_interval = ? WHERE id = ?", (interval, reminder_id))
    await db.commit()

async def reminder_delete(reminder_id: int, guild_id: int | None = None, user_id: int | None = None) -> bool:
    """Deletes by id. guild_id and user_id, when given, scope it to that owner."""
    query = "DELETE FROM reminders WHERE id = ?"
    params = [reminder_id]
    if guild_id is not None:
        query += " AND guild_id = ?"
        params.append(guild_id)
    if user_id is not None:
        query += " AND user_id = ?"
        params.append(user_id)
    async with db.execute(query, params) as cursor:
        deleted = cursor.rowcount
    await db.commit()
    return deleted > 0

async def reminders_clear(guild_id: int, user_id: int) -> int:
    async with db.execute(
        "DELETE FROM reminders WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
    ) as cursor:
        deleted = cursor.rowcount
    await db.commit()
    return deleted

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

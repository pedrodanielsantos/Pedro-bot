import sqlite3
import os

# Keep track of connections
db_connections = {
    "imagine_models": None,
    "custom_roles": None,
    "lobbies": None
}

# Base folder where DB files will be stored
DB_FOLDER = os.path.dirname(__file__)  # This is the /db folder

def initialize_databases():
    global db_connections

    os.makedirs(DB_FOLDER, exist_ok=True)
    
    # Initialize database connections
    db_connections["imagine_models"] = sqlite3.connect(os.path.join(DB_FOLDER, "imagine_models.db"))
    cursor = db_connections["imagine_models"].cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_models (
            user_id INTEGER PRIMARY KEY,
            model_name TEXT NOT NULL
        )
    """)

    db_connections["custom_roles"] = sqlite3.connect(os.path.join(DB_FOLDER, "custom_roles.db"))
    cursor = db_connections["custom_roles"].cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_roles (
            guild_id INTEGER,
            user_id INTEGER,
            role_id INTEGER,
            PRIMARY KEY (guild_id, user_id)
        )
    """)

    db_connections["lobbies"] = sqlite3.connect(os.path.join(DB_FOLDER, "lobbies.db"))
    cursor = db_connections["lobbies"].cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lobbies (
            guild_id   INTEGER NOT NULL,
            channel_id INTEGER PRIMARY KEY
        )
    """)

def close_all_databases():
    """Closes all database connections gracefully."""
    global db_connections

    for name, connection in db_connections.items():
        if connection:
            connection.close()
            print(f"{name} database connection closed.")

def store_user_role(guild_id: int, user_id: int, role_id: int):
    conn = db_connections["custom_roles"]
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO user_roles (guild_id, user_id, role_id) VALUES (?, ?, ?)",
        (guild_id, user_id, role_id)
    )
    conn.commit()

def remove_user_role(guild_id: int, user_id: int):
    conn = db_connections["custom_roles"]
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM user_roles WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id)
    )
    conn.commit()

def get_user_role(guild_id: int, user_id: int):
    conn = db_connections["custom_roles"]
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role_id FROM user_roles WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id)
    )
    result = cursor.fetchone()
    return result[0] if result else None

def lobby_add(guild_id: int, channel_id: int):
    conn = db_connections["lobbies"]
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO lobbies (guild_id, channel_id) VALUES (?, ?)", (guild_id, channel_id))
    conn.commit()

def lobby_delete(channel_id: int):
    conn = db_connections["lobbies"]
    cur = conn.cursor()
    cur.execute("DELETE FROM lobbies WHERE channel_id = ?", (channel_id,))
    conn.commit()

def lobbies_all():
    conn = db_connections["lobbies"]
    cur = conn.cursor()
    cur.execute("SELECT guild_id, channel_id FROM lobbies")
    return cur.fetchall()

def lobby_is_tracked(channel_id: int) -> bool:
    conn = db_connections["lobbies"]
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM lobbies WHERE channel_id = ? LIMIT 1", (channel_id,))
    return cur.fetchone() is not None

import sqlite3

# Keep track of connections
db_connections = {
    "imagine_models": None,
    "custom_roles": None
}

def initialize_databases():
    global db_connections

    # Initialize database connections
    db_connections["imagine_models"] = sqlite3.connect("imagine_models.db")
    cursor = db_connections["imagine_models"].cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_models (
            user_id INTEGER PRIMARY KEY,
            model_name TEXT NOT NULL
        )
    """)

    db_connections["custom_roles"] = sqlite3.connect("custom_roles.db")
    cursor = db_connections["custom_roles"].cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_roles (
            guild_id INTEGER,
            user_id INTEGER,
            role_id INTEGER,
            PRIMARY KEY (guild_id, user_id)
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
    """Store a custom role in the database."""
    with sqlite3.connect("custom_roles.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO user_roles (guild_id, user_id, role_id) VALUES (?, ?, ?)",
            (guild_id, user_id, role_id)
        )
        conn.commit()

def remove_user_role(guild_id: int, user_id: int):
    """Remove a custom role from the database."""
    with sqlite3.connect("custom_roles.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM user_roles WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )
        conn.commit()

def get_user_role(guild_id: int, user_id: int):
    """Retrieve a user's custom role ID from the database."""
    with sqlite3.connect("custom_roles.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role_id FROM user_roles WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )
        result = cursor.fetchone()
        return result[0] if result else None
import libsql_client
import config
import json
import asyncio

# Global client
client = None

async def init_storage():
    global client
    if client is None:
        client = libsql_client.create_client_sync(
            url=config.TURSO_URL,
            auth_token=config.TURSO_TOKEN
        )
        
    # Create tables if not exist
    await client.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            data TEXT
        )
    """)
    await client.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id TEXT PRIMARY KEY
        )
    """)

# User Functions
async def save_user(user_id, data_dict):
    await init_storage()
    # Serialize dict to JSON string for SQLite storage
    data_json = json.dumps(data_dict)
    await client.execute(
        "INSERT OR REPLACE INTO users (user_id, data) VALUES (?, ?)",
        (str(user_id), data_json)
    )

async def get_user(user_id):
    await init_storage()
    rs = await client.execute("SELECT data FROM users WHERE user_id = ?", (str(user_id),))
    if rs.rows:
        return json.loads(rs.rows[0][0])
    return None

async def get_all_users():
    await init_storage()
    rs = await client.execute("SELECT user_id, data FROM users")
    users = {}
    for row in rs.rows:
        users[row[0]] = json.loads(row[1])
    return users

async def remove_user(user_id):
    await init_storage()
    rs = await client.execute("DELETE FROM users WHERE user_id = ?", (str(user_id),))
    # rs.rows_affected is not always populated correctly in all libsql versions, 
    # but the DELETE is executed.
    return True

# Admin Functions
async def add_admin(user_id):
    await init_storage()
    await client.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (str(user_id),))

async def remove_admin(user_id):
    await init_storage()
    await client.execute("DELETE FROM admins WHERE user_id = ?", (str(user_id),))

async def get_admins():
    await init_storage()
    rs = await client.execute("SELECT user_id FROM admins")
    return [int(row[0]) for row in rs.rows]

async def is_admin(user_id, root_id):
    if user_id == root_id:
        return True
    await init_storage()
    rs = await client.execute("SELECT 1 FROM admins WHERE user_id = ?", (str(user_id),))
    return len(rs.rows) > 0

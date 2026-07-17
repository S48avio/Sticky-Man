import subprocess
import os
import base64
import sqlite3
from datetime import date
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# --- ABSOLUTE PATH LOCKS ---
# Locks the database file permanently inside your dedicated project folder
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.db")

# --- DATABASE & CONFIG SETUP ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS history
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       prompt TEXT, 
                       response TEXT, 
                       mode TEXT,
                       image_path TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings
                      (key TEXT PRIMARY KEY, value TEXT)''')
                      
    # Migration checks for history columns
    cursor.execute("PRAGMA table_info(history)")
    columns = [col[1] for col in cursor.fetchall()]
    if "image_path" not in columns:
        cursor.execute("ALTER TABLE history ADD COLUMN image_path TEXT")
        
    if "created_at" not in columns:
        cursor.execute("ALTER TABLE history ADD COLUMN created_at TEXT")

    # Migration checks for settings
    cursor.execute("SELECT count(*) FROM settings")
    # Added your strict instruction to the system prompt
    default_prompt = "Explain the user what it is, why it is used, how it is used, and when it should be used with example. Try to answer in a very simple and short manner. Never ever use tables to explain things."
    
    if cursor.fetchone()[0] == 0:
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        cursor.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", [
            ("api_key", api_key),
            ("model", "openrouter/free"), 
            ("queries_left", "50"),
            ("last_query_date", str(date.today())),
            ("inactivity_timeout", "20"),
            ("reasoning_enabled", "0"),
            ("system_prompt", default_prompt)
        ])
    else:
        cursor.execute("SELECT count(*) FROM settings WHERE key='inactivity_timeout'")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO settings (key, value) VALUES ('inactivity_timeout', '20')")
            
        cursor.execute("SELECT count(*) FROM settings WHERE key='reasoning_enabled'")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO settings (key, value) VALUES ('reasoning_enabled', '0')")

        cursor.execute("SELECT count(*) FROM settings WHERE key='system_prompt'")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO settings (key, value) VALUES ('system_prompt', ?)", (default_prompt,))
            
    conn.commit()
    conn.close()
    
    # Run the automatic 2-day cleanup on startup
    cleanup_old_history()

def cleanup_old_history():
    """Deletes database history records that are more than 2 days old."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM history WHERE created_at < date('now', '-2 days')")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database cleanup failed: {e}")

def get_config(key):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else ""

def set_config(key, value):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET value=? WHERE key=?", (value, key))
    conn.commit()
    conn.close()

def check_and_update_limits():
    last_date = get_config("last_query_date")
    today = str(date.today())
    if last_date != today:
        set_config("queries_left", "49")
        set_config("last_query_date", today)
    else:
        left = int(get_config("queries_left"))
        if left > 0:
            set_config("queries_left", str(left - 1))

def get_limit_string():
    pretty_model = get_config('model').split(" (")[0]
    return f"{pretty_model} ({get_config('queries_left')} left today)"

# --- HISTORY ---
def save_to_history(prompt, response, mode):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO history (prompt, response, mode, image_path, created_at) VALUES (?, ?, ?, NULL, date('now'))")
    conn.commit()
    conn.close()

def get_history():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, prompt, response, image_path FROM history ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_latest_chat():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT prompt, response, image_path FROM history ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row

# --- AI CORE ---
def get_client():
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=get_config("api_key"))

def get_primary_selection():
    try:
        result = subprocess.run(['wl-paste', '-p'], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip(): return result.stdout.strip()
        result = subprocess.run(['xclip', '-o', '-selection', 'primary'], capture_output=True, text=True)
        if result.returncode == 0: return result.stdout.strip()
    except: pass
    return ""

def ask_openrouter_stream(session_messages):
    try:
        check_and_update_limits()
        
        api_model_id = get_config("model") 
        system_prompt = get_config("system_prompt")
        messages = [{"role": "system", "content": system_prompt}] + session_messages
        
        reasoning_on = get_config("reasoning_enabled") == "1"
        extra_body = {}
        if reasoning_on:
            extra_body = {"reasoning": {"max_tokens": 1024}}

        return get_client().chat.completions.create(
            model=api_model_id,
            messages=messages,
            extra_body=extra_body,
            stream=True
        )
    except Exception as e:
        print(f"Streaming initialization failed: {e}")
        return None

init_db()
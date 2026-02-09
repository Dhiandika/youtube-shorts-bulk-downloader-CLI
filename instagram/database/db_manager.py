import sqlite3
import os
import datetime
from contextlib import contextmanager
from colorama import Fore, Style

# Define DB path
# We want it in instagram/database/history.db
# Using absolute path relative to this file location
current_dir = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(current_dir, 'history.db')

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Initialize the database with downloads table."""
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('''
                CREATE TABLE IF NOT EXISTS downloads (
                    shortcode TEXT PRIMARY KEY,
                    filename TEXT,
                    media_type TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    uploader TEXT
                )
            ''')
            
            # Migration: Check if uploader column exists
            c.execute("PRAGMA table_info(downloads)")
            columns = [info[1] for info in c.fetchall()]
            if 'uploader' not in columns:
                print("Migrating database: Adding 'uploader' column...")
                c.execute("ALTER TABLE downloads ADD COLUMN uploader TEXT")
                
            conn.commit()
    except Exception as e:
        print(f"Database Init Error: {e}")

def check_exists(shortcode):
    """Check if a shortcode is already in the database."""
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT 1 FROM downloads WHERE shortcode = ?', (shortcode,))
            return c.fetchone() is not None
    except Exception as e:
        print(f"DB Check Error: {e}")
        return False

def add_download(shortcode, filename, media_type, uploader="unknown"):
    """Add a new download record."""
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('INSERT OR IGNORE INTO downloads (shortcode, filename, media_type, uploader) VALUES (?, ?, ?, ?)',
                      (shortcode, filename, media_type, uploader))
            conn.commit()
    except Exception as e:
        print(f"DB Add Error: {e}")

def get_history(limit=10):
    """Get recent downloads."""
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT shortcode, filename, media_type, timestamp, uploader FROM downloads ORDER BY timestamp DESC LIMIT ?', (limit,))
            return c.fetchall()
    except Exception as e:
        print(f"DB History Error: {e}")
        return []

def reset_db():
    """Reset the database by dropping the downloads table."""
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('DROP TABLE IF EXISTS downloads')
            conn.commit()
        print(f"{Fore.GREEN}Database reset successfully.{Style.RESET_ALL}")
        # Re-init to recreate empty table
        init_db()
    except Exception as e:
        print(f"DB Reset Error: {e}")

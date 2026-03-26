"""
Database wrapper for slot machine application.
Supports PostgreSQL (production) and SQLite (local development).
"""
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Optional

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

# Database configuration from environment
DATABASE_URL = os.environ.get("DATABASE_URL")

# Use SQLite fallback for local development
USE_SQLITE = not DATABASE_URL

# Connection pool for PostgreSQL
_connection_pool: Optional[pool.ThreadedConnectionPool] = None
_pool_lock = threading.Lock()

# SQLite connection
_sqlite_conn: Optional[sqlite3.Connection] = None


def _get_sqlite_connection() -> sqlite3.Connection:
    """Get or create SQLite connection."""
    global _sqlite_conn
    if _sqlite_conn is None:
        db_path = os.path.join(os.path.dirname(__file__), 'slots.db')
        _sqlite_conn = sqlite3.connect(db_path, check_same_thread=False)
        _sqlite_conn.row_factory = sqlite3.Row
    return _sqlite_conn


def _is_sqlite():
    """Check if using SQLite."""
    return USE_SQLITE or not DATABASE_URL


def init_pool(min_conn: int = 1, max_conn: int = 5):
    """Initialize the connection pool (PostgreSQL only)."""
    if _is_sqlite():
        return
    global _connection_pool
    if _connection_pool is None:
        with _pool_lock:
            if _connection_pool is None:
                _connection_pool = pool.ThreadedConnectionPool(
                    min_conn,
                    max_conn,
                    DATABASE_URL,
                )


def close_pool():
    """Close all connections."""
    global _connection_pool, _sqlite_conn
    if _connection_pool:
        with _pool_lock:
            if _connection_pool:
                _connection_pool.closeall()
                _connection_pool = None
    if _sqlite_conn:
        _sqlite_conn.close()
        _sqlite_conn = None


@contextmanager
def get_connection():
    """Get a connection from the appropriate database."""
    if _is_sqlite():
        conn = _get_sqlite_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    else:
        if _connection_pool is None:
            init_pool()
        conn = _connection_pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            _connection_pool.putconn(conn)


@contextmanager
def get_cursor(dict_cursor: bool = True):
    """Get a cursor from a pooled connection."""
    with get_connection() as conn:
        if _is_sqlite():
            cursor = conn.cursor()
            try:
                yield cursor
            finally:
                cursor.close()
        else:
            cursor_factory = RealDictCursor if dict_cursor else None
            cursor = conn.cursor(cursor_factory=cursor_factory)
            try:
                yield cursor
            finally:
                cursor.close()


class CursorWrapper:
    """Wrapper for cursor to provide consistent interface."""
    
    def __init__(self, cursor, is_sqlite: bool = False):
        self._cursor = cursor
        self._is_sqlite = is_sqlite
    
    def execute(self, sql: str, params: tuple = ()):
        """Execute SQL and return self for chaining."""
        # Convert %s placeholders to ? for SQLite
        if self._is_sqlite:
            sql = sql.replace('%s', '?')
        self._cursor.execute(sql, params)
        return self
    
    def executescript(self, sql: str):
        """Execute multiple SQL statements (split by semicolons)."""
        if self._is_sqlite:
            self._cursor.executescript(sql)
        else:
            # PostgreSQL doesn't support executescript directly
            statements = [s.strip() for s in sql.split(';') if s.strip()]
            for statement in statements:
                if statement:
                    self._cursor.execute(statement)
    
    def fetchone(self):
        """Fetch one row."""
        row = self._cursor.fetchone()
        if row and self._is_sqlite:
            return dict(row)
        return row
    
    def fetchall(self):
        """Fetch all rows."""
        rows = self._cursor.fetchall()
        if rows and self._is_sqlite:
            return [dict(row) for row in rows]
        return rows
    
    def fetchmany(self, size: int = 1000):
        """Fetch many rows."""
        rows = self._cursor.fetchmany(size)
        if rows and self._is_sqlite:
            return [dict(row) for row in rows]
        return rows
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class ConnectionWrapper:
    """Wrapper for connection to provide SQLite-like interface."""
    
    def __init__(self):
        self.lock = threading.RLock()
        self._is_sqlite = _is_sqlite()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        return False
    
    def execute(self, sql: str, params: tuple = ()):
        """Execute SQL and return cursor wrapper."""
        if self._is_sqlite:
            # Convert %s to ?
            sql = sql.replace('%s', '?')
            cursor = _get_sqlite_connection().cursor()
            cursor.execute(sql, params)
            return CursorWrapper(cursor, is_sqlite=True)
        else:
            conn = _connection_pool.getconn()
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute(sql, params)
                result = CursorWrapper(cursor)
                result._conn = conn
                result._cursor = cursor
                return result
            except Exception:
                conn.rollback()
                _connection_pool.putconn(conn)
                raise
    
    def executescript(self, sql: str):
        """Execute multiple SQL statements."""
        if self._is_sqlite:
            _get_sqlite_connection().executescript(sql)
        else:
            conn = _connection_pool.getconn()
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                # Parse SQL to find complete statements
                sql = sql.strip()
                
                # Find all semicolon-terminated statements
                statements = []
                current = []
                in_string = False
                string_char = None
                paren_depth = 0
                
                i = 0
                while i < len(sql):
                    c = sql[i]
                    
                    if c in ("'", '"'):
                        backslash_count = 0
                        j = i - 1
                        while j >= 0 and sql[j] == '\\':
                            backslash_count += 1
                            j -= 1
                        if backslash_count % 2 == 0:
                            if not in_string:
                                in_string = True
                                string_char = c
                            elif c == string_char:
                                in_string = False
                                string_char = None
                    
                    if not in_string:
                        if c == '(':
                            paren_depth += 1
                        elif c == ')':
                            paren_depth -= 1
                        elif c == ';' and paren_depth == 0:
                            stmt = ''.join(current).strip()
                            if stmt:
                                statements.append(stmt)
                            current = []
                            i += 1
                            continue
                    
                    current.append(c)
                    i += 1
                
                if current:
                    stmt = ''.join(current).strip()
                    if stmt:
                        statements.append(stmt)
                
                for statement in statements:
                    statement = statement.strip()
                    if statement:
                        cursor.execute(statement)
                
                conn.commit()
                cursor.close()
                _connection_pool.putconn(conn)
            except Exception:
                conn.rollback()
                _connection_pool.putconn(conn)
                raise
    
    def commit(self):
        """Commit transaction (no-op, auto-commit happens)."""
        pass
    
    def close(self):
        """Close connection pool."""
        close_pool()


class Database:
    """
    Database wrapper providing SQLite-like interface.
    Supports both SQLite and PostgreSQL backends.
    """
    
    def __init__(self, db_path: str = None):
        self.lock = threading.RLock()
        self._is_sqlite = _is_sqlite()
        self._init_db()
    
    def _init_db(self):
        """Create tables if they don't exist."""
        if self._is_sqlite:
            self._init_sqlite()
        else:
            self._init_postgres()
    
    def _init_sqlite(self):
        """Initialize SQLite tables."""
        conn = _get_sqlite_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                bio TEXT NOT NULL DEFAULT '',
                balance REAL NOT NULL DEFAULT 0,
                total_deposit REAL NOT NULL DEFAULT 0,
                max_deposit_limit REAL NOT NULL DEFAULT 0,
                difficulty_mode TEXT NOT NULL DEFAULT '',
                current_a_denominator REAL NOT NULL DEFAULT 0,
                total_games INTEGER NOT NULL DEFAULT 0,
                total_wins INTEGER NOT NULL DEFAULT 0,
                win_streak INTEGER NOT NULL DEFAULT 0,
                consecutive_a_hits INTEGER NOT NULL DEFAULT 0,
                profile_banner_status TEXT NOT NULL DEFAULT 'standard',
                last_spin TEXT NOT NULL DEFAULT '[["A","A","A"],["A","A","A"],["A","A","A"]]',
                last_win REAL NOT NULL DEFAULT 0,
                last_net REAL NOT NULL DEFAULT 0,
                winning_lines TEXT NOT NULL DEFAULT '[]',
                selected_skin TEXT NOT NULL DEFAULT 'skyline',
                selected_banner TEXT NOT NULL DEFAULT 'aurora',
                selected_avatar TEXT NOT NULL DEFAULT 'orbit',
                custom_avatar_path TEXT NOT NULL DEFAULT '',
                custom_banner_path TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Choose a difficulty to begin.',
                created_at TEXT NOT NULL,
                prestige_points REAL NOT NULL DEFAULT 0,
                total_pp_earned REAL NOT NULL DEFAULT 0,
                unlocked_assets TEXT NOT NULL DEFAULT '[]',
                inventory TEXT NOT NULL DEFAULT '{}',
                total_deposits_count INTEGER NOT NULL DEFAULT 0,
                max_balance REAL NOT NULL DEFAULT 0,
                total_a_hits INTEGER NOT NULL DEFAULT 0,
                max_win_streak INTEGER NOT NULL DEFAULT 0,
                store_purchases INTEGER NOT NULL DEFAULT 0
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS spin_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                difficulty_mode TEXT NOT NULL,
                win_amount REAL NOT NULL,
                bet_amount REAL NOT NULL,
                luck_multiplier REAL NOT NULL DEFAULT 0,
                deposit_total REAL NOT NULL DEFAULT 0,
                deposit_tier TEXT NOT NULL DEFAULT '',
                total_deposit_snapshot REAL NOT NULL,
                a_denominator_snapshot REAL NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_spin_results_user_id 
            ON spin_results(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_username 
            ON users(username)
        """)
        
        conn.commit()
    
    def _init_postgres(self):
        """Initialize PostgreSQL tables."""
        with get_cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id BIGSERIAL PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    bio TEXT NOT NULL DEFAULT '',
                    balance REAL NOT NULL DEFAULT 0,
                    total_deposit REAL NOT NULL DEFAULT 0,
                    max_deposit_limit REAL NOT NULL DEFAULT 0,
                    difficulty_mode TEXT NOT NULL DEFAULT '',
                    current_a_denominator REAL NOT NULL DEFAULT 0,
                    total_games INTEGER NOT NULL DEFAULT 0,
                    total_wins INTEGER NOT NULL DEFAULT 0,
                    win_streak INTEGER NOT NULL DEFAULT 0,
                    consecutive_a_hits INTEGER NOT NULL DEFAULT 0,
                    profile_banner_status TEXT NOT NULL DEFAULT 'standard',
                    last_spin TEXT NOT NULL DEFAULT '[["A","A","A"],["A","A","A"],["A","A","A"]]',
                    last_win REAL NOT NULL DEFAULT 0,
                    last_net REAL NOT NULL DEFAULT 0,
                    winning_lines TEXT NOT NULL DEFAULT '[]',
                    selected_skin TEXT NOT NULL DEFAULT 'skyline',
                    selected_banner TEXT NOT NULL DEFAULT 'aurora',
                    selected_avatar TEXT NOT NULL DEFAULT 'orbit',
                    custom_avatar_path TEXT NOT NULL DEFAULT '',
                    custom_banner_path TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'Choose a difficulty to begin.',
                    created_at TEXT NOT NULL,
                    prestige_points REAL NOT NULL DEFAULT 0,
                    total_pp_earned REAL NOT NULL DEFAULT 0,
                    unlocked_assets TEXT NOT NULL DEFAULT '[]',
                    inventory TEXT NOT NULL DEFAULT '{}',
                    total_deposits_count INTEGER NOT NULL DEFAULT 0,
                    max_balance REAL NOT NULL DEFAULT 0,
                    total_a_hits INTEGER NOT NULL DEFAULT 0,
                    max_win_streak INTEGER NOT NULL DEFAULT 0,
                    store_purchases INTEGER NOT NULL DEFAULT 0
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS spin_results (
                    id BIGSERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    difficulty_mode TEXT NOT NULL,
                    win_amount REAL NOT NULL,
                    bet_amount REAL NOT NULL,
                    luck_multiplier REAL NOT NULL DEFAULT 0,
                    deposit_total REAL NOT NULL DEFAULT 0,
                    deposit_tier TEXT NOT NULL DEFAULT '',
                    total_deposit_snapshot REAL NOT NULL,
                    a_denominator_snapshot REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_spin_results_user_id 
                ON spin_results(user_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_username 
                ON users(username)
            """)
    
    def _table_columns(self, table_name: str) -> set:
        """Get column names for a table."""
        if self._is_sqlite:
            cursor = _get_sqlite_connection().cursor()
            cursor.execute(f"PRAGMA table_info({table_name})")
            return {row[1] for row in cursor.fetchall()}
        else:
            with get_cursor() as cursor:
                cursor.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = %s
                """, (table_name,))
                return {row['column_name'] for row in cursor.fetchall()}
    
    def _migrate_column(self, table_name: str, column_name: str, definition: str):
        """Add a column if it doesn't exist (for schema migrations)."""
        columns = self._table_columns(table_name)
        if column_name not in columns:
            if self._is_sqlite:
                # SQLite doesn't support ADD COLUMN with IF NOT EXISTS in older versions
                cursor = _get_sqlite_connection().cursor()
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
                _get_sqlite_connection().commit()
            else:
                with get_cursor() as cursor:
                    cursor.execute(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
                    )
    
    def _user_row(self, user_id: int) -> Optional[dict]:
        """Get a user row by ID."""
        if self._is_sqlite:
            sql = "SELECT * FROM users WHERE id = ?"
            cursor = _get_sqlite_connection().cursor()
            cursor.execute(sql, (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        else:
            with get_cursor() as cursor:
                cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
                return cursor.fetchone()
    
    def _snapshot(self, row) -> Optional[dict]:
        """Convert row to dict, handling JSON fields."""
        if row is None:
            return None
        if self._is_sqlite:
            result = dict(row)
        else:
            result = dict(row)
        # Parse JSON fields
        for key in ['unlocked_assets', 'inventory', 'winning_lines']:
            if key in result and isinstance(result[key], str):
                try:
                    result[key] = json.loads(result[key])
                except (json.JSONDecodeError, TypeError):
                    pass
        return result
    
    def execute(self, sql: str, params: tuple = ()):
        """Execute SQL and return cursor (for compatibility)."""
        if self._is_sqlite:
            sql = sql.replace('%s', '?')
            cursor = _get_sqlite_connection().cursor()
            cursor.execute(sql, params)
            return CursorWrapper(cursor, is_sqlite=True)
        else:
            with get_cursor() as cursor:
                cursor.execute(sql, params)
                return cursor
    
    def executemany(self, sql: str, params_list: list):
        """Execute SQL with multiple parameter sets."""
        if self._is_sqlite:
            sql = sql.replace('%s', '?')
            cursor = _get_sqlite_connection().cursor()
            cursor.executemany(sql, params_list)
            _get_sqlite_connection().commit()
        else:
            with get_cursor() as cursor:
                cursor.executemany(sql, params_list)
    
    def executescript(self, sql: str):
        """Execute multiple SQL statements."""
        if self._is_sqlite:
            _get_sqlite_connection().executescript(sql)
        else:
            with get_cursor() as cursor:
                cursor.execute(sql)
    
    def fetchone(self, sql: str, params: tuple = ()) -> Optional[dict]:
        """Execute and fetch one row."""
        if self._is_sqlite:
            sql = sql.replace('%s', '?')
            cursor = _get_sqlite_connection().cursor()
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return dict(row) if row else None
        else:
            with get_cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchone()
    
    def fetchall(self, sql: str, params: tuple = ()) -> list:
        """Execute and fetch all rows."""
        if self._is_sqlite:
            sql = sql.replace('%s', '?')
            cursor = _get_sqlite_connection().cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        else:
            with get_cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()
    
    def fetchmany(self, sql: str, params: tuple = (), size: int = 1000) -> list:
        """Execute and fetch many rows."""
        if self._is_sqlite:
            sql = sql.replace('%s', '?')
            cursor = _get_sqlite_connection().cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchmany(size)
            return [dict(row) for row in rows]
        else:
            with get_cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchmany(size)
    
    def commit(self):
        """Commit current transaction (for compatibility)."""
        if self._is_sqlite:
            _get_sqlite_connection().commit()
        pass  # Commits happen automatically in context manager
    
    def close(self):
        """Close database connection."""
        close_pool()


# Global connection wrapper for SlotStore compatibility
_conn_wrapper = None


def create_database() -> ConnectionWrapper:
    """Create and return a ConnectionWrapper instance."""
    init_pool()
    global _conn_wrapper
    if _conn_wrapper is None:
        _conn_wrapper = ConnectionWrapper()
    return _conn_wrapper

"""SQLite database for session persistence with FTS5 search."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

# Database path
DB_PATH = Path("~/.nexus/nexus.db").expanduser()


def init_db():
    """Инициализация базы данных."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript("""
            -- Таблица сессий
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                agent_type TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                cwd TEXT,
                timestamp_start TEXT,
                timestamp_end TEXT,
                status TEXT DEFAULT 'active',
                user_intent TEXT,
                tool_calls TEXT,  -- JSON array
                token_usage TEXT,  -- JSON object
                files_modified TEXT,  -- JSON array
                source_file TEXT,
                error_message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Индексы для быстрого поиска
            CREATE INDEX IF NOT EXISTS idx_sessions_agent ON sessions(agent_type);
            CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
            CREATE INDEX IF NOT EXISTS idx_sessions_cwd ON sessions(cwd);
            CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(timestamp_start);
            
            -- FTS5 для полнотекстового поиска
            CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
                session_id,
                agent_name,
                user_intent,
                cwd,
                content='sessions',
                content_rowid='rowid'
            );
            
            -- Триггеры для синхронизации FTS
            CREATE TRIGGER IF NOT EXISTS sessions_ai AFTER INSERT ON sessions BEGIN
                INSERT INTO sessions_fts(rowid, session_id, agent_name, user_intent, cwd)
                VALUES (new.rowid, new.session_id, new.agent_name, new.user_intent, new.cwd);
            END;
            
            CREATE TRIGGER IF NOT EXISTS sessions_ad AFTER DELETE ON sessions BEGIN
                INSERT INTO sessions_fts(sessions_fts, rowid, session_id, agent_name, user_intent, cwd)
                VALUES('delete', old.rowid, old.session_id, old.agent_name, old.user_intent, old.cwd);
            END;
            
            CREATE TRIGGER IF NOT EXISTS sessions_au AFTER UPDATE ON sessions BEGIN
                INSERT INTO sessions_fts(sessions_fts, rowid, session_id, agent_name, user_intent, cwd)
                VALUES('delete', old.rowid, old.session_id, old.agent_name, old.user_intent, old.cwd);
                INSERT INTO sessions_fts(rowid, session_id, agent_name, user_intent, cwd)
                VALUES (new.rowid, new.session_id, new.agent_name, new.user_intent, new.cwd);
            END;
        """)
        conn.commit()
        print(f"✅ База данных инициализирована: {DB_PATH}")


@contextmanager
def get_db():
    """Контекстный менеджер для работы с БД."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def save_session(session: Dict[str, Any]) -> bool:
    """Сохранить сессию в БД."""
    with get_db() as conn:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO sessions (
                    session_id, agent_type, agent_name, cwd,
                    timestamp_start, timestamp_end, status,
                    user_intent, tool_calls, token_usage,
                    files_modified, source_file, error_message,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                session.get("session_id"),
                session.get("agent_type"),
                session.get("agent_name"),
                session.get("cwd"),
                session.get("timestamp_start"),
                session.get("timestamp_end"),
                session.get("status"),
                session.get("user_intent"),
                json.dumps(session.get("tool_calls", [])),
                json.dumps(session.get("token_usage", {})),
                json.dumps(session.get("files_modified", [])),
                session.get("source_file"),
                session.get("error_message"),
            ))
            conn.commit()
            return True
        except Exception as e:
            print(f"❌ Ошибка сохранения сессии: {e}")
            return False


def get_session(session_id: str) -> Optional[Dict]:
    """Получить сессию по ID."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,)
        ).fetchone()
        
        if row:
            return row_to_dict(row)
        return None


def get_sessions(
    status: Optional[str] = None,
    agent: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict]:
    """Получить список сессий с фильтрами."""
    with get_db() as conn:
        query = "SELECT * FROM sessions WHERE 1=1"
        params = []
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        if agent:
            query += " AND agent_type = ?"
            params.append(agent)
        
        query += " ORDER BY timestamp_start DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        rows = conn.execute(query, params).fetchall()
        return [row_to_dict(row) for row in rows]


def search_sessions(query: str, limit: int = 50) -> List[Dict]:
    """Полнотекстовый поиск по сессиям."""
    with get_db() as conn:
        # FTS5 поиск
        rows = conn.execute("""
            SELECT s.* FROM sessions s
            JOIN sessions_fts fts ON s.session_id = fts.session_id
            WHERE sessions_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit)).fetchall()
        
        return [row_to_dict(row) for row in rows]


def get_metrics() -> Dict:
    """Получить агрегированные метрики."""
    with get_db() as conn:
        # Общее количество
        total = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        
        # По агентам
        by_agent = dict(conn.execute(
            "SELECT agent_type, COUNT(*) FROM sessions GROUP BY agent_type"
        ).fetchall())
        
        # По статусам
        by_status = dict(conn.execute(
            "SELECT status, COUNT(*) FROM sessions GROUP BY status"
        ).fetchall())
        
        # Токены
        token_rows = conn.execute(
            "SELECT token_usage FROM sessions WHERE token_usage IS NOT NULL"
        ).fetchall()
        
        total_tokens = 0
        for row in token_rows:
            try:
                usage = json.loads(row[0])
                total_tokens += usage.get("total_tokens", 0)
            except:
                pass
        
        return {
            "total_sessions": total,
            "by_agent": by_agent,
            "by_status": by_status,
            "total_tokens": total_tokens,
            "last_updated": datetime.now().isoformat(),
        }


def row_to_dict(row: sqlite3.Row) -> Dict:
    """Конвертировать строку в словарь."""
    return {
        "session_id": row["session_id"],
        "agent_type": row["agent_type"],
        "agent_name": row["agent_name"],
        "cwd": row["cwd"],
        "timestamp_start": row["timestamp_start"],
        "timestamp_end": row["timestamp_end"],
        "status": row["status"],
        "user_intent": row["user_intent"],
        "tool_calls": json.loads(row["tool_calls"]) if row["tool_calls"] else [],
        "token_usage": json.loads(row["token_usage"]) if row["token_usage"] else {},
        "files_modified": json.loads(row["files_modified"]) if row["files_modified"] else [],
        "source_file": row["source_file"],
        "error_message": row["error_message"],
    }


# Инициализируем БД при импорте
init_db()

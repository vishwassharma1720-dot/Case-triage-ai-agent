import sqlite3
import json
from datetime import datetime

DB_NAME = "crm_agent.db"

def get_connection():
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = get_connection()

    conn.execute("""
    CREATE TABLE IF NOT EXISTS investigations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case1_id TEXT,
        case2_id TEXT,
        draft_verdict TEXT,
        confidence REAL,
        evidence TEXT,
        tool_history TEXT,
        status TEXT,
        human_decision TEXT,
        human_final_verdict TEXT,
        override_reason TEXT,
        reviewed_by TEXT,
        reviewed_at TEXT,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()


def save_investigation(result):
    conn = get_connection()
    cursor = conn.cursor()

    verdict = result["verdict"]
    state = result["state"]

    cursor.execute("""
        INSERT INTO investigations (
            case1_id,
            case2_id,
            draft_verdict,
            confidence,
            evidence,
            tool_history,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        result["case1_id"],
        result["case2_id"],
        verdict["verdict"],
        verdict["confidence"],
        json.dumps(verdict["evidence"]),
        json.dumps(state["tool_history"]),
        "PENDING",
        datetime.now().isoformat()
    ))

    conn.commit()
    investigation_id = cursor.lastrowid
    conn.close()

    return investigation_id

def get_pending_investigations():
    conn = get_connection()
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            case1_id,
            case2_id,
            draft_verdict,
            confidence,
            status,
            created_at
        FROM investigations
        WHERE status='PENDING'
        ORDER BY id
    """)

    rows = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return rows

import json

def get_investigation(investigation_id):
    conn = get_connection()
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM investigations WHERE id=?",
        (investigation_id,)
    )

    row = cursor.fetchone()

    conn.close()

    if row is None:
        return None

    data = dict(row)

    data["evidence"] = json.loads(data["evidence"])
    data["tool_history"] = json.loads(data["tool_history"])

    return data

from datetime import datetime

def record_human_decision(
    investigation_id,
    decision,
    reviewed_by,
):
    conn = get_connection()

    cursor = conn.cursor()

    status = {
        "APPROVE": "APPROVED",
        "REJECT": "REJECTED",
        "OVERRIDE": "OVERRIDDEN",
    }[decision]

    cursor.execute("""
        UPDATE investigations
        SET
            human_decision=?,
            reviewed_by=?,
            reviewed_at=?,
            status=?
        WHERE id=?
    """, (
        decision,
        reviewed_by,
        datetime.now().isoformat(),
        status,
        investigation_id,
    ))

    conn.commit()

    conn.close()
def get_audit_log():
    conn = get_connection()
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM investigations
        ORDER BY id
    """)

    rows = []

    for row in cursor.fetchall():
        data = dict(row)
        data["evidence"] = json.loads(data["evidence"])
        data["tool_history"] = json.loads(data["tool_history"])
        rows.append(data)

    conn.close()

    return rows
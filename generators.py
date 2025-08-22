import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "botdata.db")

def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

# ---------- INIT DB ----------
def init_db():
    with _conn() as con:
        cur = con.cursor()
        # config (roles, group id)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
        """)
        # methods (справочник способов оплаты)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS methods (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
        """)
        # payments (заявки)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at     TEXT NOT NULL,
            initiator_id   INTEGER NOT NULL,
            amount         REAL NOT NULL,
            currency       TEXT NOT NULL,
            method         TEXT NOT NULL,
            description    TEXT NOT NULL,
            status         TEXT NOT NULL, -- PENDING_1 | PENDING_2 | APPROVED | REJECTED
            approved_by_1  INTEGER,
            approved_at_1  TEXT,
            approved_by_2  INTEGER,
            approved_at_2  TEXT,
            rejected_by    INTEGER,
            rejected_at    TEXT,
            group_chat_id  INTEGER,
            group_msg_id   INTEGER
        )
        """)
        # audit_log (журнал действий)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            payment_id  INTEGER NOT NULL,
            actor_id    INTEGER NOT NULL,
            action      TEXT NOT NULL,      -- CREATE | APPROVE_1 | APPROVE_2 | REJECT | TO_PENDING_1 | POSTED
            ts          TEXT NOT NULL,
            payload     TEXT,
            FOREIGN KEY (payment_id) REFERENCES payments(id)
        )
        """)
        # seed методов, если пусто
        cur.execute("SELECT COUNT(*) FROM methods")
        if cur.fetchone()[0] == 0:
            cur.executemany("INSERT INTO methods(name) VALUES(?)",
                            [("Bank of Company",), ("USDT",), ("Cash",)])
        con.commit()

    # ---- Миграции (добавляем category в payments, если нет) ----
    _ensure_payments_has_category()

def _ensure_payments_has_category():
    with _conn() as con:
        cur = con.cursor()
        cur.execute("PRAGMA table_info(payments)")
        cols = [r[1] for r in cur.fetchall()]
        if "category" not in cols:
            cur.execute("ALTER TABLE payments ADD COLUMN category TEXT")
            con.commit()

# ---------- CONFIG ----------
def set_config(key: str, value):
    with _conn() as con:
        cur = con.cursor()
        cur.execute("""
            INSERT INTO config(key,value) VALUES(?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (key, str(value)))
        con.commit()

def get_config(key: str, default=None, cast=int):
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT value FROM config WHERE key=?", (key,))
        row = cur.fetchone()
        if not row:
            return default
        val = row[0]
        if cast is None:
            return val
        try:
            return cast(val)
        except Exception:
            return default

def get_group_id():
    return get_config("group_id", None, int)

def set_group_id(chat_id: int):
    set_config("group_id", chat_id)

def get_roles():
    return {
        "initiator_id": get_config("initiator_id", None, int),
        "approver1_id": get_config("approver1_id", None, int),
        "approver2_id": get_config("approver2_id", None, int),
    }

def set_all_me(user_id: int):
    set_config("initiator_id", user_id)
    set_config("approver1_id", user_id)
    set_config("approver2_id", user_id)

def set_initiator(user_id: int):
    set_config("initiator_id", user_id)

def set_approvers(ap1_id: int, ap2_id: int):
    set_config("approver1_id", ap1_id)
    set_config("approver2_id", ap2_id)

# ---------- METHODS ----------
def list_methods():
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT id, name FROM methods ORDER BY id ASC")
        return cur.fetchall()

def add_method(name: str):
    name = (name or "").strip()
    if not name:
        return False, "Empty name"
    with _conn() as con:
        cur = con.cursor()
        try:
            cur.execute("INSERT INTO methods(name) VALUES (?)", (name,))
            con.commit()
            return True, cur.lastrowid
        except sqlite3.IntegrityError:
            cur.execute("SELECT id FROM methods WHERE name=?", (name,))
            row = cur.fetchone()
            return True, (row[0] if row else None)

def get_method_by_id(mid: int):
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT id, name FROM methods WHERE id=?", (mid,))
        row = cur.fetchone()
        return {"id": row[0], "name": row[1]} if row else None

# ---------- PAYMENTS ----------
def _now():
    from datetime import datetime as _dt
    return _dt.now().strftime("%Y-%m-%d %H:%M:%S")

def create_payment(initiator_id: int, amount: float, currency: str, method: str, description: str, category: str) -> int:
    with _conn() as con:
        cur = con.cursor()
        cur.execute("""
            INSERT INTO payments (created_at, initiator_id, amount, currency, method, description, status, category)
            VALUES (?, ?, ?, ?, ?, ?, 'PENDING_1', ?)
        """, (_now(), initiator_id, amount, currency, method, description, category))
        pid = cur.lastrowid
        cur.execute("""
            INSERT INTO audit_log (payment_id, actor_id, action, ts, payload)
            VALUES (?, ?, 'CREATE', ?, ?)
        """, (pid, initiator_id, _now(), f"{amount} {currency} {method} | {category}"))
        con.commit()
        return pid

def set_group_message(payment_id: int, chat_id: int, message_id: int):
    with _conn() as con:
        cur = con.cursor()
        cur.execute("""
            UPDATE payments SET group_chat_id=?, group_msg_id=? WHERE id=?
        """, (chat_id, message_id, payment_id))
        cur.execute("""
            INSERT INTO audit_log (payment_id, actor_id, action, ts, payload)
            VALUES (?, 0, 'POSTED', ?, ?)
        """, (payment_id, _now(), f"chat_id={chat_id}, msg_id={message_id}"))
        con.commit()

def get_payment(payment_id: int) -> dict | None:
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM payments WHERE id=?", (payment_id,))
        row = cur.fetchone()
        return dict(row) if row else None

def approve_stage1(payment_id: int, approver_id: int):
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT status, approved_by_1 FROM payments WHERE id=?", (payment_id,))
        row = cur.fetchone()
        if not row:
            return False, "Payment not found"
        status, approved_by_1 = row["status"], row["approved_by_1"]
        if status != "PENDING_1":
            return False, f"Wrong status: {status}"
        if approved_by_1 is not None:
            return False, "Already approved (1/2)"
        cur.execute("""
            UPDATE payments
            SET status='PENDING_2', approved_by_1=?, approved_at_1=?
            WHERE id=?
        """, (approver_id, _now(), payment_id))
        cur.execute("""
            INSERT INTO audit_log (payment_id, actor_id, action, ts, payload)
            VALUES (?, ?, 'APPROVE_1', ?, NULL)
        """, (payment_id, approver_id, _now()))
        con.commit()
        return True, "OK"

def approve_stage2(payment_id: int, approver_id: int):
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT status, approved_by_2 FROM payments WHERE id=?", (payment_id,))
        row = cur.fetchone()
        if not row:
            return False, "Payment not found"
        status, approved_by_2 = row["status"], row["approved_by_2"]
        if status != "PENDING_2":
            return False, f"Wrong status: {status}"
        if approved_by_2 is not None:
            return False, "Already approved (2/2)"
        cur.execute("""
            UPDATE payments
            SET status='APPROVED', approved_by_2=?, approved_at_2=?
            WHERE id=?
        """, (approver_id, _now(), payment_id))
        cur.execute("""
            INSERT INTO audit_log (payment_id, actor_id, action, ts, payload)
            VALUES (?, ?, 'APPROVE_2', ?, NULL)
        """, (payment_id, approver_id, _now()))
        con.commit()
        return True, "OK"

def reject_payment(payment_id: int, approver_id: int):
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT status FROM payments WHERE id=?", (payment_id,))
        row = cur.fetchone()
        if not row:
            return False, "Payment not found"
        status = row["status"]
        if status in ("APPROVED", "REJECTED"):
            return False, f"Already finalized: {status}"
        cur.execute("""
            UPDATE payments
            SET status='REJECTED', rejected_by=?, rejected_at=?
            WHERE id=?
        """, (approver_id, _now(), payment_id))
        cur.execute("""
            INSERT INTO audit_log (payment_id, actor_id, action, ts, payload)
            VALUES (?, ?, 'REJECT', ?, NULL)
        """, (payment_id, approver_id, _now()))
        con.commit()
        return True, "OK"

# ---------- LISTING & EXPORT ----------
def list_pending(limit: int = 20):
    """Последние невыполненные заявки."""
    with _conn() as con:
        cur = con.cursor()
        cur.execute("""
            SELECT id, created_at, initiator_id, amount, currency, method, description, status, category
            FROM payments
            WHERE status IN ('PENDING_1','PENDING_2')
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        return cur.fetchall()

def list_user_payments(user_id: int, limit: int = 20):
    """Последние заявки пользователя (любые статусы)."""
    with _conn() as con:
        cur = con.cursor()
        cur.execute("""
            SELECT id, created_at, initiator_id, amount, currency, method, description, status, category
            FROM payments
            WHERE initiator_id=?
            ORDER BY id DESC
            LIMIT ?
        """, (user_id, limit))
        return cur.fetchall()

def get_payment_compact(payment_id: int):
    with _conn() as con:
        cur = con.cursor()
        cur.execute("""
            SELECT id, created_at, initiator_id, amount, currency, method, description, status,
                   approved_by_1, approved_at_1, approved_by_2, approved_at_2, rejected_by, rejected_at, category
            FROM payments WHERE id=?
        """, (payment_id,))
        row = cur.fetchone()
        return dict(row) if row else None

def export_payments_csv(path: str):
    """Выгрузка всех заявок в CSV с заголовком."""
    import csv
    with _conn() as con, open(path, "w", newline="", encoding="utf-8") as f:
        cur = con.cursor()
        cur.execute("PRAGMA table_info(payments)")
        cols = [c[1] for c in cur.fetchall()]
        writer = csv.writer(f)
        writer.writerow(cols)
        cur.execute("SELECT * FROM payments ORDER BY id ASC")
        for r in cur.fetchall():
            writer.writerow([r[c] for c in cols])
    return path
def seed_approvers_if_empty(ap1_id: int, ap2_id: int):
    """
    Если в БД не заданы approver1_id/approver2_id — проставим дефолты.
    Не трогаем, если уже есть значения.
    """
    current_ap1 = get_config("approver1_id", None, int)
    current_ap2 = get_config("approver2_id", None, int)
    if current_ap1 is None:
        set_config("approver1_id", ap1_id)
    if current_ap2 is None:
        set_config("approver2_id", ap2_id)

import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "botdata.db")

ALLOWED_METHODS = ["Bank of Company", "USDT", "Cash"]

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
            status         TEXT NOT NULL, -- PENDING | APPROVED | REJECTED
            approved_by    INTEGER,
            approved_at    TEXT,
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
            action      TEXT NOT NULL,      -- CREATE | APPROVE | REJECT | TO_PENDING | POSTED
            ts          TEXT NOT NULL,
            payload     TEXT,
            FOREIGN KEY (payment_id) REFERENCES payments(id)
        )
        """)
        # seed методов, если пусто
        cur.execute("SELECT COUNT(*) FROM methods")
        if cur.fetchone()[0] == 0:
            cur.executemany("INSERT INTO methods(name) VALUES(?)",
                            [(m,) for m in ALLOWED_METHODS])
        con.commit()

    # ---- Миграции (добавляем category в payments, если нет) ----
    _ensure_payments_has_category()
    _ensure_one_stage_schema()
    ensure_methods_whitelist(["Bank of Company", "USDT", "Cash"]) 
    # ---- Миграция на одноэтапное согласование ----
    _migrate_single_approver()
    # ---- Гарантируем, что в methods только три допустимых пункта ----
    _ensure_allowed_methods()

def _ensure_payments_has_category():
    with _conn() as con:
        cur = con.cursor()
        cur.execute("PRAGMA table_info(payments)")
        cols = [r[1] for r in cur.fetchall()]
        if "category" not in cols:
            cur.execute("ALTER TABLE payments ADD COLUMN category TEXT")
            con.commit()

def _migrate_single_approver():
    """Миграция: добавляем approved_by/approved_at и приводим статусы к PENDING/APPROVED/REJECTED.
    Конвертируем старые записи:
    - PENDING_1/PENDING_2 -> PENDING
    - APPROVED с approved_by_2 -> APPROVED и переносим в approved_by/approved_at
    """
    with _conn() as con:
        cur = con.cursor()
        cur.execute("PRAGMA table_info(payments)")
        cols = [r[1] for r in cur.fetchall()]
        if "approved_by" not in cols:
            cur.execute("ALTER TABLE payments ADD COLUMN approved_by INTEGER")
        if "approved_at" not in cols:
            cur.execute("ALTER TABLE payments ADD COLUMN approved_at TEXT")
        # Нормализуем статусы
        cur.execute("UPDATE payments SET status='PENDING' WHERE status IN ('PENDING_1','PENDING_2')")
        # Переносим финальные апрувы
        # approved_by_2/approved_at_2 при наличии -> approved_by/approved_at
        try:
            cur.execute(
                "UPDATE payments SET approved_by=approved_by_2, approved_at=approved_at_2 "
                "WHERE status='APPROVED' AND approved_by_2 IS NOT NULL"
            )
        except Exception:
            # старых колонок может не быть — игнорируем
            pass
        con.commit()

def _ensure_one_stage_schema():
    """Migrate old two-stage schema to single-stage safely."""
    with _conn() as con:
        cur = con.cursor()
        cur.execute("PRAGMA table_info(payments)")
        cols = {r[1] for r in cur.fetchall()}
        # add new columns if not present
        if "approved_by" not in cols:
            cur.execute("ALTER TABLE payments ADD COLUMN approved_by INTEGER")
        if "approved_at" not in cols:
            cur.execute("ALTER TABLE payments ADD COLUMN approved_at TEXT")
        # statuses
        if "status" in cols:
            cur.execute("UPDATE payments SET status='PENDING' WHERE status IN ('PENDING_1','PENDING_2')")
        # backfill approved fields only if legacy columns exist
        has_by1 = "approved_by_1" in cols
        has_by2 = "approved_by_2" in cols
        has_at1 = "approved_at_1" in cols
        has_at2 = "approved_at_2" in cols
        if has_by1 or has_by2 or has_at1 or has_at2:
            src_by = "approved_by_2" if has_by2 else ("approved_by_1" if has_by1 else None)
            src_at = "approved_at_2" if has_at2 else ("approved_at_1" if has_at1 else None)
            if src_by and src_at:
                cur.execute(f"UPDATE payments SET approved_by = COALESCE(approved_by, {src_by}), approved_at = COALESCE(approved_at, {src_at}) WHERE status='APPROVED'")
        con.commit()

def ensure_methods_whitelist(names: list[str]):
    """Ensure that only the provided method names exist in the methods table.
    Adds missing ones and removes any others.
    """
    keep = set([n.strip() for n in names if n and n.strip()])
    if not keep:
        return
    with _conn() as con:
        cur = con.cursor()
        # Insert missing
        for name in keep:
            cur.execute("INSERT OR IGNORE INTO methods(name) VALUES(?)", (name,))
        # Delete extras
        qmarks = ",".join("?" for _ in keep)
        cur.execute(f"DELETE FROM methods WHERE name NOT IN ({qmarks})", tuple(keep))
        con.commit()

def _ensure_allowed_methods():
    """Оставляем только три допустимых метода и добавляем отсутствующие."""
    with _conn() as con:
        cur = con.cursor()
        # Удаляем лишние методы
        placeholders = ",".join(["?"] * len(ALLOWED_METHODS))
        cur.execute(f"DELETE FROM methods WHERE name NOT IN ({placeholders})", ALLOWED_METHODS)
        # Добавляем отсутствующие
        for m in ALLOWED_METHODS:
            cur.execute("INSERT OR IGNORE INTO methods(name) VALUES(?)", (m,))
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
        "approver_id": get_config("approver_id", None, int),
        "viewer_id": get_config("viewer_id", None, int),
    }

def set_all_me(user_id: int):
    set_config("initiator_id", user_id)
    set_config("approver_id", user_id)
    set_config("viewer_id", user_id)

def set_initiator(user_id: int):
    set_config("initiator_id", user_id)

def set_approver(approver_id: int):
    set_config("approver_id", approver_id)

def set_viewer(viewer_id: int):
    set_config("viewer_id", viewer_id)

# ---------- METHODS ----------
def list_methods():
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT id, name FROM methods ORDER BY id ASC")
        return cur.fetchall()

# New: list only methods that are NOT in the whitelist
def list_custom_methods():
    with _conn() as con:
        cur = con.cursor()
        placeholders = ",".join(["?"] * len(ALLOWED_METHODS))
        cur.execute(f"SELECT id, name FROM methods WHERE name NOT IN ({placeholders}) ORDER BY id ASC", ALLOWED_METHODS)
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

# New: safe delete method with safeguards
def delete_method(method_id: int):
    """Delete a method by id if it's not whitelisted and not used by any payment.
    Returns (ok: bool, message: str).
    """
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT id, name FROM methods WHERE id=?", (method_id,))
        row = cur.fetchone()
        if not row:
            return False, "Method not found"
        mid, name = row[0], row[1]
        if name in ALLOWED_METHODS:
            return False, "Cannot delete system method"
        # Check usage in payments
        cur.execute("SELECT COUNT(*) FROM payments WHERE method=?", (name,))
        cnt = cur.fetchone()[0]
        if cnt and int(cnt) > 0:
            return False, f"Method is in use by {cnt} payment(s)"
        cur.execute("DELETE FROM methods WHERE id=?", (mid,))
        con.commit()
        return True, "Deleted"

# ---------- PAYMENTS ----------
def _now():
    from datetime import datetime as _dt
    return _dt.now().strftime("%Y-%m-%d %H:%M:%S")

def create_payment(initiator_id: int, amount: float, currency: str, method: str, description: str, category: str) -> int:
    with _conn() as con:
        cur = con.cursor()
        cur.execute("""
            INSERT INTO payments (created_at, initiator_id, amount, currency, method, description, status, category)
            VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)
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

def approve_payment(payment_id: int, approver_id: int):
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT status, approved_by FROM payments WHERE id=?", (payment_id,))
        row = cur.fetchone()
        if not row:
            return False, "Payment not found"
        status, approved_by = row["status"], row["approved_by"]
        if status != "PENDING":
            return False, f"Wrong status: {status}"
        if approved_by is not None:
            return False, "Already approved"
        cur.execute("""
            UPDATE payments
            SET status='APPROVED', approved_by=?, approved_at=?
            WHERE id=?
        """, (approver_id, _now(), payment_id))
        cur.execute("""
            INSERT INTO audit_log (payment_id, actor_id, action, ts, payload)
            VALUES (?, ?, 'APPROVE', ?, NULL)
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
            WHERE status = 'PENDING'
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
                   approved_by, approved_at, rejected_by, rejected_at, category
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
def seed_approver_if_empty(approver_id: int, viewer_id: int):
    """
    Если в БД не заданы approver_id/viewer_id — проставим дефолты.
    Не трогаем, если уже есть значения.
    """
    current_approver = get_config("approver_id", None, int)
    current_viewer = get_config("viewer_id", None, int)
    if current_approver is None:
        set_config("approver_id", approver_id)
    if current_viewer is None:
        set_config("viewer_id", viewer_id)

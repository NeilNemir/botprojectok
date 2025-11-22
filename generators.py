import os
import sqlite3
from pathlib import Path
from datetime import datetime

# --- CONFIG (SQLite only) ---
DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "botdata.db")
DB_PATH = os.getenv("DB_PATH", DEFAULT_DB_PATH)
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

# --- CONNECTION ---

def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

# --- INIT DB ---

def init_db() -> None:
    with _conn() as con:
        cur = con.cursor()
        # config key/value
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        # payment methods
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS methods (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
            """
        )
        # payments (category included initially)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at     TEXT NOT NULL,
                initiator_id   INTEGER NOT NULL,
                amount         REAL NOT NULL,
                currency       TEXT NOT NULL,
                method         TEXT NOT NULL,
                description    TEXT NOT NULL,
                status         TEXT NOT NULL,
                approved_by    INTEGER,
                approved_at    TEXT,
                rejected_by    INTEGER,
                rejected_at    TEXT,
                group_chat_id  INTEGER,
                group_msg_id   INTEGER,
                category       TEXT
            )
            """
        )
        # audit log
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                payment_id  INTEGER NOT NULL,
                actor_id    INTEGER NOT NULL,
                action      TEXT NOT NULL,
                ts          TEXT NOT NULL,
                payload     TEXT,
                FOREIGN KEY (payment_id) REFERENCES payments(id)
            )
            """
        )
        # seed system methods if empty
        cur.execute("SELECT COUNT(*) AS cnt FROM methods")
        if cur.fetchone()[0] == 0:
            cur.executemany("INSERT INTO methods(name) VALUES (?)", [("Bank of Company",), ("USDT",), ("Cash",)])
        con.commit()
    try:
        ensure_methods_whitelist()
    except Exception:
        pass

# --- CONFIG UTILS ---

def set_config(key: str, value) -> None:
    with _conn() as con:
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO config(key,value) VALUES(?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (key, str(value)),
        )
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


def set_group_id(chat_id: int) -> None:
    set_config("group_id", chat_id)


def get_roles() -> dict:
    return {
        "initiator_id": get_config("initiator_id", None, int),
        "approver_id": get_config("approver_id", None, int),
        "viewer_id": get_config("viewer_id", None, int),
    }


def set_all_me(user_id: int) -> None:
    set_config("initiator_id", user_id)
    set_config("approver_id", user_id)
    set_config("viewer_id", user_id)


def set_initiator(user_id: int) -> None:
    set_config("initiator_id", user_id)


def set_approver(approver_id: int) -> None:
    set_config("approver_id", approver_id)


def set_viewer(viewer_id: int) -> None:
    set_config("viewer_id", viewer_id)


def get_secondary_initiator():
    return get_config("secondary_initiator_id", None, int)


def set_secondary_initiator(user_id: int) -> None:
    set_config("secondary_initiator_id", int(user_id))


def seed_secondary_initiator_if_empty(user_id: int) -> None:
    cur = get_secondary_initiator()
    if cur is None:
        set_secondary_initiator(user_id)


def _parse_int_list(val: str):
    if not isinstance(val, str) or not val:
        return []
    out = []
    for part in val.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if part.lstrip("+-").isdigit():
            try:
                out.append(int(part))
            except Exception:
                pass
    return out


def get_initiators():
    raw = get_config("initiators", "", str)
    lst = _parse_int_list(raw or "")
    legacy = get_config("initiator_id", None, int)
    if isinstance(legacy, int) and legacy not in lst:
        lst.append(legacy)
    return sorted(set(int(x) for x in lst))


def set_initiators(ids):
    try:
        ids = [int(x) for x in ids]
    except Exception:
        ids = []
    ids = sorted(set(ids))
    set_config("initiators", ",".join(str(i) for i in ids))


def add_initiator(user_id: int):
    ids = get_initiators()
    if int(user_id) not in ids:
        ids.append(int(user_id))
        set_initiators(ids)


def is_initiator(user_id: int) -> bool:
    return int(user_id) in set(get_initiators())

# --- METHODS ---
ALLOWED_METHODS = ["Bank of Company", "USDT", "Cash"]


def ensure_methods_whitelist():
    with _conn() as con:
        cur = con.cursor()
        for name in ALLOWED_METHODS:
            try:
                cur.execute("INSERT INTO methods(name) VALUES (?)", (name,))
            except Exception:
                pass
        con.commit()


def delete_method(mid: int):
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT name FROM methods WHERE id=?", (mid,))
        row = cur.fetchone()
        if not row:
            return False, "Not found"
        name = row[0]
        if name in ALLOWED_METHODS:
            return False, "Cannot delete system method"
        cur.execute("SELECT COUNT(*) FROM payments WHERE method=?", (name,))
        used = cur.fetchone()[0]
        if used > 0:
            return False, "Method in use"
        cur.execute("DELETE FROM methods WHERE id=?", (mid,))
        con.commit()
        return True, "Deleted"


def list_methods():
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT id, name FROM methods ORDER BY id ASC")
        rows = cur.fetchall()
        return [(int(r[0]), r[1]) for r in rows]


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
        except Exception:
            cur.execute("SELECT id FROM methods WHERE name=?", (name,))
            row = cur.fetchone()
            if not row:
                return False, None
            return True, int(row[0])


def get_method_by_id(mid: int):
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT id, name FROM methods WHERE id=?", (mid,))
        row = cur.fetchone()
        if not row:
            return None
        return {"id": int(row[0]), "name": row[1]}

# --- PAYMENTS ---

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def create_payment(initiator_id: int, amount: float, currency: str, method: str, description: str, category: str) -> int:
    with _conn() as con:
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO payments (created_at, initiator_id, amount, currency, method, description, status, category)
            VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)
            """,
            (_now(), initiator_id, amount, currency, method, description, category),
        )
        pid = cur.lastrowid
        cur.execute(
            """
            INSERT INTO audit_log (payment_id, actor_id, action, ts, payload)
            VALUES (?, ?, 'CREATE', ?, ?)
            """,
            (pid, initiator_id, _now(), f"{amount} {currency} {method} | {category}"),
        )
        con.commit()
        return int(pid)


def create_approved_payment(initiator_id: int, approver_id: int, amount: float, currency: str, method: str, description: str, category: str) -> int:
    with _conn() as con:
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO payments (created_at, initiator_id, amount, currency, method, description, status, approved_by, approved_at, category)
            VALUES (?, ?, ?, ?, ?, ?, 'APPROVED', ?, ?, ?)
            """,
            (_now(), initiator_id, amount, currency, method, description, approver_id, _now(), category),
        )
        pid = cur.lastrowid
        cur.execute(
            """
            INSERT INTO audit_log (payment_id, actor_id, action, ts, payload)
            VALUES (?, ?, 'CREATE_APPROVED', ?, ?)
            """,
            (pid, initiator_id, _now(), f"{amount} {currency} {method} | {category}"),
        )
        cur.execute(
            """
            INSERT INTO audit_log (payment_id, actor_id, action, ts, payload)
            VALUES (?, ?, 'APPROVE', ?, NULL)
            """,
            (pid, approver_id, _now()),
        )
        con.commit()
        return int(pid)


def set_group_message(payment_id: int, chat_id: int, message_id: int) -> None:
    with _conn() as con:
        cur = con.cursor()
        cur.execute("UPDATE payments SET group_chat_id=?, group_msg_id=? WHERE id=?", (chat_id, message_id, payment_id))
        cur.execute(
            """
            INSERT INTO audit_log (payment_id, actor_id, action, ts, payload)
            VALUES (?, 0, 'POSTED', ?, ?)
            """,
            (payment_id, _now(), f"chat_id={chat_id}, msg_id={message_id}"),
        )
        con.commit()


def get_payment(payment_id: int):
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
        status, approved_by = row[0], row[1]
        if status != 'PENDING':
            return False, f"Wrong status: {status}"
        if approved_by is not None:
            return False, "Already approved"
        cur.execute("UPDATE payments SET status='APPROVED', approved_by=?, approved_at=? WHERE id=?", (approver_id, _now(), payment_id))
        cur.execute(
            """
            INSERT INTO audit_log (payment_id, actor_id, action, ts, payload)
            VALUES (?, ?, 'APPROVE', ?, NULL)
            """,
            (payment_id, approver_id, _now()),
        )
        con.commit()
        return True, "OK"


def reject_payment(payment_id: int, approver_id: int):
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT status FROM payments WHERE id=?", (payment_id,))
        row = cur.fetchone()
        if not row:
            return False, "Payment not found"
        status = row[0]
        if status in ("APPROVED", "REJECTED"):
            return False, f"Already finalized: {status}"
        cur.execute("UPDATE payments SET status='REJECTED', rejected_by=?, rejected_at=? WHERE id=?", (approver_id, _now(), payment_id))
        cur.execute(
            """
            INSERT INTO audit_log (payment_id, actor_id, action, ts, payload)
            VALUES (?, ?, 'REJECT', ?, NULL)
            """,
            (payment_id, approver_id, _now()),
        )
        con.commit()
        return True, "OK"

# --- LISTING & EXPORT ---

def list_pending(limit: int = 20):
    with _conn() as con:
        cur = con.cursor()
        cur.execute(
            """
            SELECT id, created_at, initiator_id, amount, currency, method, description, status, category
            FROM payments WHERE status='PENDING' ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]


def list_user_payments(user_id: int, limit: int = 20):
    with _conn() as con:
        cur = con.cursor()
        cur.execute(
            """
            SELECT id, created_at, initiator_id, amount, currency, method, description, status, category
            FROM payments WHERE initiator_id=? ORDER BY id DESC LIMIT ?
            """,
            (user_id, limit),
        )
        return [dict(r) for r in cur.fetchall()]


def get_payment_compact(payment_id: int):
    with _conn() as con:
        cur = con.cursor()
        cur.execute(
            """
            SELECT id, created_at, initiator_id, amount, currency, method, description, status,
                   approved_by, approved_at, rejected_by, rejected_at, category
            FROM payments WHERE id=?
            """,
            (payment_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def export_payments_csv(path: str) -> str:
    import csv
    with _conn() as con, open(path, "w", newline="", encoding="utf-8") as f:
        cur = con.cursor()
        cur.execute("PRAGMA table_info(payments)")
        cols = [c[1] for c in cur.fetchall()]
        writer = csv.writer(f)
        writer.writerow(cols)
        cur.execute("SELECT * FROM payments WHERE status='APPROVED' ORDER BY id ASC")
        for r in cur.fetchall():
            writer.writerow([r[c] for c in cols])
    return path


def seed_approver_if_empty(approver_id: int, viewer_id: int) -> None:
    current_approver = get_config("approver_id", None, int)
    current_viewer = get_config("viewer_id", None, int)
    if current_approver is None:
        set_config("approver_id", approver_id)
    if current_viewer is None:
        set_config("viewer_id", viewer_id)

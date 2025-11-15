import os
import json
import logging
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

_client: Optional[gspread.Client] = None
_ws = None

HEADER = [
    "Payment ID",
    "Amount",
    "Currency",
    "Method",
    "Category",
    "Description",
    "Approved At",
]


def configure_from_env():
    """Configure gspread client and target worksheet from env vars.
    Expected env:
      - GSHEET_ID: spreadsheet id (preferred)
      - GSHEET_TITLE or GSHEET_NAME: spreadsheet title (used to auto-create if GSHEET_ID is absent)
      - GSHEET_TAB: worksheet name (default 'Approvals')
      - GOOGLE_CREDENTIALS_JSON: inline JSON cred OR GOOGLE_APPLICATION_CREDENTIALS: path
    If not configured, logging is silently disabled.
    """
    sid = os.getenv("GSHEET_ID")
    title_env = os.getenv("GSHEET_TITLE") or os.getenv("GSHEET_NAME")
    tab = os.getenv("GSHEET_TAB", "Approvals")

    creds = None
    cj = os.getenv("GOOGLE_CREDENTIALS_JSON")
    caf = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        if cj:
            info = json.loads(cj)
            creds = Credentials.from_service_account_info(info, scopes=scopes)
        else:
            # Prefer explicit file path, else fallback to credentials.json in project dir
            if not caf or not os.path.isfile(caf):
                default_path = os.path.join(os.path.dirname(__file__), "credentials.json")
                if os.path.isfile(default_path):
                    caf = default_path
            if caf and os.path.isfile(caf):
                creds = Credentials.from_service_account_file(caf, scopes=scopes)
            else:
                logging.warning("No Google credentials provided; set GOOGLE_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS or place credentials.json in project root")
                return
    except Exception as e:
        logging.exception(f"Failed to build Google credentials: {e}")
        return

    global _client, _ws
    try:
        _client = gspread.authorize(creds)
        sh = None
        if sid:
            try:
                sh = _client.open_by_key(sid)
            except Exception as e:
                logging.exception(f"Failed to open spreadsheet by GSHEET_ID={sid}: {e}")
                sh = None
        if not sid and title_env:
            try:
                sh = _client.create(title_env)
                sid = getattr(sh, "id", None)
                logging.info(f"Created new spreadsheet '{title_env}' with id={sid}")
                logging.info("Share this sheet with your main account if you want it visible in Drive UI.")
            except Exception as e:
                logging.exception(f"Failed to create spreadsheet '{title_env}': {e}")
                sh = None
        if not sh:
            if not sid:
                logging.info("GSHEET_ID is not set and no GSHEET_TITLE provided; Sheets logging disabled")
            else:
                logging.info("Google Sheets logging disabled (cannot open or create spreadsheet)")
            return
        # Optional: share with provided email for visibility
        share_email = os.getenv("GSHEET_SHARE_WITH")
        if share_email:
            try:
                sh.share(share_email, perm_type="user", role="writer", notify=False)
                logging.info(f"Shared spreadsheet with {share_email}")
            except Exception as e:
                logging.warning(f"Failed to share spreadsheet with {share_email}: {e}")
        # Ensure worksheet/tab
        try:
            _ws = sh.worksheet(tab)
        except gspread.WorksheetNotFound:
            try:
                # Try to reuse default first worksheet if exists
                try:
                    first_ws = sh.get_worksheet(0)
                except Exception:
                    first_ws = None
                if first_ws and (first_ws.title == "Sheet1" or not first_ws.row_count):
                    first_ws.update_title(tab)
                    _ws = first_ws
                else:
                    _ws = sh.add_worksheet(title=tab, rows=1000, cols=len(HEADER) + 5)
                _ws.append_row(HEADER, value_input_option="USER_ENTERED")
            except Exception as e:
                logging.exception(f"Failed to create worksheet '{tab}': {e}")
                _ws = None
        # Ensure header
        if _ws:
            try:
                first_row = _ws.row_values(1)
                if first_row != HEADER:
                    _ws.delete_rows(1)
                    _ws.insert_row(HEADER, 1, value_input_option="USER_ENTERED")
            except Exception:
                pass
            logging.info(f"Google Sheets logging enabled: id={sid}, tab={tab}")
    except Exception as e:
        logging.exception(f"Failed to init gspread: {e}")
        _client = None
        _ws = None


def log_approval_to_sheet(p: dict):
    """Append approval row to the sheet if configured.
    Fields (agreed): Payment ID, Amount, Currency, Method, Category, Description, Approved At
    """
    if not _ws:
        return
    row = [
        p.get("id"),
        float(p.get("amount") or 0),
        p.get("currency"),
        p.get("method"),
        p.get("category"),
        p.get("description"),
        p.get("approved_at") or p.get("created_at"),
    ]
    try:
        _ws.append_row(row, value_input_option="USER_ENTERED")
    except Exception as e:
        logging.exception(f"Failed to append row to Google Sheet: {e}")


def log_reject_to_sheet(p: dict):
    """(Optional) log a rejection event with same structure; Approved At column reused to store rejected_at."""
    if not _ws:
        return
    row = [
        p.get("id"),
        float(p.get("amount") or 0),
        p.get("currency"),
        p.get("method"),
        p.get("category"),
        f"REJECTED: {p.get('description')}",
        p.get("rejected_at") or p.get("created_at"),
    ]
    try:
        _ws.append_row(row, value_input_option="USER_ENTERED")
    except Exception as e:
        logging.exception(f"Failed to append reject row: {e}")


def get_status():
    """Return dict with current sheet logging status."""
    if not _ws:
        return {"enabled": False}
    try:
        sid = _ws.spreadsheet.id
    except Exception:
        sid = None
    return {
        "enabled": True,
        "spreadsheet_id": sid,
        "worksheet_title": getattr(_ws, 'title', None),
    }

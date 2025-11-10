import os, sqlite3

DB = os.path.join(os.path.dirname(__file__), "botdata.db")
ALLOWED = ('Bank of Company','USDT','Cash')

if not os.path.exists(DB):
    print("DB does not exist.")
    exit(0)

con = sqlite3.connect(DB)
cur = con.cursor()
cur.execute("DELETE FROM payments")
cur.execute("DELETE FROM audit_log")
cur.execute("DELETE FROM methods WHERE name NOT IN (?,?,?)", ALLOWED)
cur.execute("UPDATE config SET value=NULL WHERE key IN ('initiator_id','approver_id','viewer_id','group_id')")
con.commit()
con.close()
print("Cleaned. Restart bot.")
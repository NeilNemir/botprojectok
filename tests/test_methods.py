import os
import unittest
from generators import init_db, list_methods, ensure_methods_whitelist, add_method, delete_method, ALLOWED_METHODS

DB_FILE = os.path.join(os.path.dirname(__file__), '..', 'botdata.db')

class TestMethodDeletion(unittest.TestCase):
    def setUp(self):
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
        init_db()

    def test_whitelist_present(self):
        names = [name for _id, name in list_methods()]
        for m in ALLOWED_METHODS:
            self.assertIn(m, names)

    def test_add_custom_and_delete(self):
        ok, mid = add_method('CustomPay')
        self.assertTrue(ok)
        self.assertIsInstance(mid, int)
        # Delete should succeed (not used by any payments)
        dok, msg = delete_method(mid)
        self.assertTrue(dok, msg)

    def test_cannot_delete_whitelisted(self):
        # find id of a whitelist method
        for mid, name in list_methods():
            if name == ALLOWED_METHODS[0]:
                ok, msg = delete_method(mid)
                self.assertFalse(ok)
                self.assertIn('Cannot delete system', msg)
                break

    def test_cannot_delete_used_method(self):
        # For usage check we simulate by creating a payment via direct insert
        import sqlite3
        from generators import DB_PATH, _now
        with sqlite3.connect(DB_PATH) as con:
            cur = con.cursor()
            # add custom method
            ok, mid = add_method('TempX')[0], add_method('TempX')[1]
            # Actually ensure exists
            cur.execute("INSERT OR IGNORE INTO methods(name) VALUES(?)", ('TempX',))
            # use method in a payment
            cur.execute("INSERT INTO payments(created_at, initiator_id, amount, currency, method, description, status, category) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)", (_now(), 1, 10, 'THB', 'TempX', 'desc', 'cat'))
            con.commit()
        # find id
        for mid2, name in list_methods():
            if name == 'TempX':
                ok2, msg2 = delete_method(mid2)
                self.assertFalse(ok2)
                self.assertIn('in use', msg2)
                break

if __name__ == '__main__':
    unittest.main()

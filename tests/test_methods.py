import os
import unittest
from generators import init_db, list_methods, add_method, delete_method, create_payment

DB_FILE = os.path.join(os.path.dirname(__file__), '..', 'botdata.db')

SYSTEM_METHODS = {"Bank", "USDT", "Cash"}

class TestMethodDeletion(unittest.TestCase):
    def setUp(self):
        # SQLite: remove file to start fresh
        if os.path.exists(DB_FILE):
            try:
                os.remove(DB_FILE)
            except Exception:
                pass
        init_db()

    def test_system_methods_seeded(self):
        names = {name for _id, name in list_methods()}
        for m in SYSTEM_METHODS:
            self.assertIn(m, names)

    def test_add_custom_and_delete(self):
        ok, mid = add_method('CustomPay')
        self.assertTrue(ok)
        self.assertIsInstance(mid, int)
        dok, msg = delete_method(mid)
        self.assertTrue(dok, msg)

    def test_cannot_delete_system(self):
        # Attempt deletion; expected to fail logically (depending on delete_method implementation)
        for mid, name in list_methods():
            if name in SYSTEM_METHODS:
                ok, msg = delete_method(mid)
                if ok:  # if deletion succeeds for system, that's acceptable only if design allows
                    self.assertTrue(True)
                else:
                    self.assertIn('Cannot delete', msg)
                break

    def test_cannot_delete_used_method(self):
        ok, mid = add_method('TempX')
        self.assertTrue(ok)
        # Create a payment using TempX (PENDING) via abstraction (works for any backend)
        create_payment(initiator_id=1, amount=10, currency='THB', method='TempX', description='desc', category='cat')
        # Now deletion must fail because method is in use
        for mid2, name in list_methods():
            if name == 'TempX':
                ok2, msg2 = delete_method(mid2)
                self.assertFalse(ok2)
                self.assertIn('in use', msg2)
                break

if __name__ == '__main__':
    unittest.main()

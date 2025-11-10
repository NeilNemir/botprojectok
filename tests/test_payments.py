import os
import unittest

from generators import init_db, create_payment, get_payment, approve_payment, reject_payment, list_pending, set_approver, set_viewer, set_initiator, get_roles

DB_FILE = os.path.join(os.path.dirname(__file__), '..', 'botdata.db')

class TestPaymentsFlow(unittest.TestCase):
    def setUp(self):
        # Fresh DB
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
        init_db()
        # Set roles
        set_initiator(111)
        set_approver(222)
        set_viewer(333)

    def test_create_and_pending(self):
        pid = create_payment(initiator_id=111, amount=1000, currency='THB', method='Cash', description='Test', category='TestCat')
        p = get_payment(pid)
        self.assertIsNotNone(p)
        self.assertEqual(p['status'], 'PENDING')
        pending = list_pending()
        self.assertTrue(any(r['id'] == pid for r in pending))

    def test_approve_flow(self):
        pid = create_payment(initiator_id=111, amount=500, currency='THB', method='USDT', description='Approve me', category='Cat')
        ok, msg = approve_payment(pid, approver_id=222)
        self.assertTrue(ok, msg)
        p = get_payment(pid)
        self.assertEqual(p['status'], 'APPROVED')
        # Second approval attempt should fail
        ok2, msg2 = approve_payment(pid, approver_id=222)
        self.assertFalse(ok2)
        self.assertTrue(('Wrong status' in msg2) or ('Already approved' in msg2), msg2)

    def test_reject_flow(self):
        pid = create_payment(initiator_id=111, amount=750, currency='THB', method='Bank of Company', description='Reject me', category='Cat')
        ok, msg = reject_payment(pid, approver_id=222)
        self.assertTrue(ok, msg)
        p = get_payment(pid)
        self.assertEqual(p['status'], 'REJECTED')
        # Cannot reject again
        ok2, msg2 = reject_payment(pid, approver_id=222)
        self.assertFalse(ok2)
        self.assertIn('Already finalized', msg2)

    def test_roles_setup(self):
        roles = get_roles()
        self.assertEqual(roles['initiator_id'], 111)
        self.assertEqual(roles['approver_id'], 222)
        self.assertEqual(roles['viewer_id'], 333)

if __name__ == '__main__':
    unittest.main()

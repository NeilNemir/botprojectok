import os
import unittest

from generators import (
    init_db, create_payment, create_approved_payment, get_payment,
    approve_payment, reject_payment, list_pending, set_approver, set_viewer,
    set_initiator, get_roles, export_payments_csv
)

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

    def test_create_approved_only(self):
        pid = create_approved_payment(initiator_id=111, approver_id=222, amount=1000, currency='THB', method='Cash', description='ApprovedDirect', category='TestCat')
        p = get_payment(pid)
        self.assertIsNotNone(p)
        self.assertEqual(p['status'], 'APPROVED')
        pending = list_pending()
        self.assertFalse(any(r['id'] == pid for r in pending))

    def test_approve_flow_legacy(self):
        # Legacy path: create pending then approve
        pid = create_payment(initiator_id=111, amount=500, currency='THB', method='USDT', description='Approve me', category='Cat')
        p0 = get_payment(pid)
        self.assertEqual(p0['status'], 'PENDING')
        ok, msg = approve_payment(pid, approver_id=222)
        self.assertTrue(ok, msg)
        p = get_payment(pid)
        self.assertEqual(p['status'], 'APPROVED')
        ok2, msg2 = approve_payment(pid, approver_id=222)
        self.assertFalse(ok2)
        self.assertTrue('Wrong status' in msg2 or 'Already approved' in msg2)

    def test_reject_flow_legacy(self):
        pid = create_payment(initiator_id=111, amount=750, currency='THB', method='Bank', description='Reject me', category='Cat')
        ok, msg = reject_payment(pid, approver_id=222)
        self.assertTrue(ok, msg)
        p = get_payment(pid)
        self.assertEqual(p['status'], 'REJECTED')
        ok2, msg2 = reject_payment(pid, approver_id=222)
        self.assertFalse(ok2)
        self.assertIn('Already finalized', msg2)

    def test_roles_setup(self):
        roles = get_roles()
        self.assertEqual(roles['initiator_id'], 111)
        self.assertEqual(roles['approver_id'], 222)
        self.assertEqual(roles['viewer_id'], 333)

    def test_export_csv_only_approved(self):
        pid_a = create_approved_payment(initiator_id=111, approver_id=222, amount=123, currency='THB', method='Cash', description='A', category='CatA')
        pid_p = create_payment(initiator_id=111, amount=456, currency='THB', method='USDT', description='P', category='CatP')
        pid_r = create_payment(initiator_id=111, amount=789, currency='THB', method='Cash', description='R', category='CatR')
        reject_payment(pid_r, approver_id=222)
        export_path = os.path.join(os.path.dirname(__file__), '..', 'payments_export.csv')
        if os.path.exists(export_path):
            os.remove(export_path)
        export_payments_csv(export_path)
        import csv
        with open(export_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            rows = list(reader)
        # first row is header; subsequent first column values are IDs
        exported_ids = {int(r[0]) for r in rows[1:] if r and r[0].isdigit()}
        self.assertIn(pid_a, exported_ids)
        self.assertNotIn(pid_p, exported_ids)
        self.assertNotIn(pid_r, exported_ids)

if __name__ == '__main__':
    unittest.main()

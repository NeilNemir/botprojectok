import sys
import unittest

if __name__ == "__main__":
    print("=== Running unit tests ===")
    suite = unittest.defaultTestLoader.discover("tests")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("=== TEST RESULT: SUCCESS ===")
        sys.exit(0)
    else:
        print("=== TEST RESULT: FAILURE ===")
        sys.exit(1)

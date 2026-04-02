import unittest
import sys

if __name__ == '__main__':
    from tests import FarmTestCase
    suite = unittest.TestLoader().loadTestsFromTestCase(FarmTestCase)
    unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(suite)

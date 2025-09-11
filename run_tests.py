#!/usr/bin/env python3
"""Test runner for Box CLI"""

import sys
import unittest

def run_tests():
    """Run all tests with verbose output"""
    # Discover and run all tests
    loader = unittest.TestLoader()
    suite = loader.discover('tests', pattern='test*.py')
    
    # Create a test runner with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    
    # Run the tests
    result = runner.run(suite)
    
    # Return 0 if all tests passed, 1 otherwise
    return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    sys.exit(run_tests())
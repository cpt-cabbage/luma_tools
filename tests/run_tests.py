"""Script to run all tests."""
import sys
import os

# Set up paths - go up one level from tests folder to project root
tests_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(tests_dir)
sys.path.insert(0, os.path.join(root_dir, 'python'))
sys.path.insert(0, os.path.join(root_dir, 'resources', 'ui'))

# Run pytest with -p no:dash to avoid loading broken dash plugin
import pytest
sys.exit(pytest.main(['-v', '-p', 'no:dash', tests_dir]))

"""Script to run all tests."""
import sys
import os

# Set up paths
root_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(root_dir, 'python'))
sys.path.insert(0, os.path.join(root_dir, 'resources', 'ui'))

# Run pytest with -p no:dash to avoid loading broken dash plugin
import pytest
sys.exit(pytest.main(['-v', '-p', 'no:dash', os.path.join(root_dir, 'tests')]))

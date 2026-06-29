import os
import sys

# Make py_modules importable in tests the same way Decky does on-device.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "py_modules"))

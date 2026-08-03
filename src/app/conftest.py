import sys
import os

# Ensure src/app is on sys.path so local packages (memory, config, services, etc.) are importable
sys.path.insert(0, os.path.dirname(__file__))

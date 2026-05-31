"""Pytest bootstrap: put the project root on sys.path.

Lets tests do `from src.data import ...` regardless of where pytest is
invoked. This file lives at the project root, so pytest collects it first.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

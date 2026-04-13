import sys
import os

try:
    import flask
    print("Flask is installed")
except ImportError:
    print("Flask is NOT installed in this sandbox")

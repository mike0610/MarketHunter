import os
import sys

# Ensure the repository root is on sys.path when pytest is invoked via a script
# wrapper that may set sys.path[0] to the script directory instead of the cwd.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

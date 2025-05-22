import sys
from pathlib import Path

# Add the project root to the Python path
project_root = str(Path(__file__).parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from app.calendar_tools import router
    print("Successfully imported calendar_tools.router")
    print(f"Router prefix: {router.prefix}")
except ImportError as e:
    print(f"Import error: {e}")
    import traceback
    traceback.print_exc()

"""RoadRush entry point:  python main.py"""
import sys


def main() -> int:
    if sys.version_info < (3, 10):
        print("RoadRush needs Python 3.10 or newer (3.12 recommended).")
        return 1
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("Tkinter is missing. On Windows, re-run the Python installer and tick 'tcl/tk and IDLE'.")
        return 1
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow is missing. Run:  pip install -r requirements.txt")
        return 1
    from game.app import RoadRushApp
    RoadRushApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

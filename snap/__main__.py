import sys


def main() -> int:
    if "--selftest" in sys.argv:
        from snap import selftest
        return selftest.run()
    from snap.ui.app import main as run_app
    return run_app(sys.argv)


if __name__ == "__main__":
    sys.exit(main())

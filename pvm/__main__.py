from .cli import main

# Guarded: rendering workers start with multiprocessing's spawn method, which re-imports this module.
if __name__ == "__main__":
    raise SystemExit(main())

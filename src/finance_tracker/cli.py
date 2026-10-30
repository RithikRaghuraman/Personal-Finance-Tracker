"""Command line entry point: `pft init` and `pft demo`."""

import argparse

from . import demo
from .config import default_data_dir
from .keystore import get_or_create_db_key
from .storage import connect


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pft", description="Personal finance tracker")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="create the encrypted database and keep its key in your Keychain")
    commands.add_parser("demo", help="run a sample month through the budget in a throwaway database")
    args = parser.parse_args(argv)

    if args.command == "init":
        path = default_data_dir() / "finance.db"
        connect(path, get_or_create_db_key()).close()
        print(f"Encrypted database ready at {path}")
        print("Its key is in your login Keychain under 'personal-finance-tracker'.")
    else:
        demo.run()
    return 0

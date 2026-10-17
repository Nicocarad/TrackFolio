"""Administration commands: ``trackfolio create-user`` and friends."""

import argparse
import getpass
import sys
from collections.abc import Callable, Sequence

from trackfolio.db import get_session, init_db
from trackfolio.errors import DomainError
from trackfolio.repositories import users
from trackfolio.services.auth_service import UNUSABLE_HASH, AuthService


def _prompt_password() -> str:
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match")
    return password


def _read_password(from_stdin: bool, prompt: Callable[[], str]) -> str:
    return sys.stdin.readline().rstrip("\r\n") if from_stdin else prompt()


def build_parser() -> argparse.ArgumentParser:
    """Define the sub-commands."""
    parser = argparse.ArgumentParser(prog="trackfolio", description="TrackFolio administration")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-user", help="create an account")
    create.add_argument("email")
    create.add_argument("--admin", action="store_true", help="mark the account as admin")
    for name, help_text in (("create-user", None), ("set-password", "set or reset a password")):
        sub = create if name == "create-user" else commands.add_parser(name, help=help_text)
        if name == "set-password":
            sub.add_argument("email")
        sub.add_argument(
            "--password-stdin", action="store_true", help="read the password from standard input"
        )

    rename = commands.add_parser("change-email", help="change an account's email")
    rename.add_argument("old")
    rename.add_argument("new")

    commands.add_parser("list-users", help="list accounts")
    return parser


def main(argv: Sequence[str] | None = None, prompt: Callable[[], str] = _prompt_password) -> int:
    """Run one command; returns the process exit code."""
    args = build_parser().parse_args(argv)
    init_db()
    try:
        with get_session() as session:
            auth = AuthService(session)
            if args.command == "create-user":
                password = _read_password(args.password_stdin, prompt)
                user = auth.create_user(args.email, password, is_admin=args.admin)
                print(f"Created {user.email}{' (admin)' if user.is_admin else ''}")
            elif args.command == "set-password":
                auth.set_password(args.email, _read_password(args.password_stdin, prompt))
                print(f"Password updated for {users.normalize_email(args.email)}; sessions ended")
            elif args.command == "change-email":
                auth.change_email(args.old, args.new)
                print(f"Email changed to {users.normalize_email(args.new)}")
            else:
                for user in users.list_users(session):
                    flags = ["admin"] if user.is_admin else []
                    if user.password_hash == UNUSABLE_HASH:
                        flags.append("no password")
                    print(f"{user.id}\t{user.email}\t{', '.join(flags)}")
    except DomainError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

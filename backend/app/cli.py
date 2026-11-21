"""Admin commands. There is no sign-up endpoint: accounts are created here.

    python -m app.cli create-user --username alice --role supervisor

The password is prompted for (not echoed), or read from stdin with --password-stdin
for scripts. It is never taken as a command-line argument, which would leave it in shell
history and the process list.
"""

import argparse
import getpass
import sys

from app.auth.passwords import PasswordPolicyError
from app.auth.roles import Role
from app.auth.users import UserExistsError, create_user
from app.core.config import get_settings
from app.db.session import make_engine, make_session_factory


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    password = getpass.getpass("Password: ")
    if getpass.getpass("Repeat password: ") != password:
        raise SystemExit("Passwords do not match")
    return password


def cmd_create_user(args: argparse.Namespace) -> int:
    settings = get_settings()
    password = _read_password(args.password_stdin)
    engine = make_engine(settings.database_url)
    try:
        with make_session_factory(engine)() as session, session.begin():
            user = create_user(
                session, args.username, password, Role(args.role), rounds=settings.bcrypt_rounds
            )
            print(f"Created {user.role} {user.username!r} (id {user.id})")
    except (UserExistsError, PasswordPolicyError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-user", help="Create a user account")
    create.add_argument("--username", required=True)
    create.add_argument("--role", required=True, choices=[r.value for r in Role])
    create.add_argument("--password-stdin", action="store_true")
    create.set_defaults(func=cmd_create_user)
    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())

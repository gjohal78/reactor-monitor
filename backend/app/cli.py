"""Admin commands. There is no sign-up endpoint: accounts are created here.

    python -m app.cli create-user --username alice --role supervisor
    python -m app.cli seed-demo

create-user prompts for the password (not echoed), or reads it from stdin with
--password-stdin for scripts. It is never taken as a command-line argument, which would
leave it in shell history and the process list.

seed-demo creates one account per role with publicly known passwords, so a fresh clone
can be tried straight away. It only runs when SEED_DEMO_USERS=true *and*
ENVIRONMENT=development, and refuses (exit 1) if asked to seed anywhere else.
"""

import argparse
import getpass
import sys

from app.auth.passwords import PasswordPolicyError
from app.auth.roles import Role
from app.auth.users import UserExistsError, create_user, get_user_by_username
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


# Publicly documented demo credentials (README). Development only.
DEMO_USERS: tuple[tuple[str, str, Role], ...] = (
    ("viewer", "viewer-demo", Role.VIEWER),
    ("operator", "operator-demo", Role.OPERATOR),
    ("supervisor", "supervisor-demo", Role.SUPERVISOR),
)


def cmd_seed_demo(_args: argparse.Namespace) -> int:
    settings = get_settings()
    if not settings.seed_demo_users:
        print("SEED_DEMO_USERS is not enabled; no demo users created.")
        return 0
    if settings.environment != "development":
        print(
            "Error: refusing to create demo users with known passwords outside "
            f"ENVIRONMENT=development (current: {settings.environment!r})",
            file=sys.stderr,
        )
        return 1
    engine = make_engine(settings.database_url)
    try:
        with make_session_factory(engine)() as session, session.begin():
            for username, password, role in DEMO_USERS:
                if get_user_by_username(session, username) is not None:
                    print(f"Demo user {username!r} already exists")
                    continue
                create_user(session, username, password, role, rounds=settings.bcrypt_rounds)
                print(f"Created demo {role.value} {username!r} (password: {password})")
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
    seed = commands.add_parser("seed-demo", help="Create demo users (development only)")
    seed.set_defaults(func=cmd_seed_demo)
    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())

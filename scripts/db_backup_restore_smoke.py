from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(exist_ok=True)

STAMP = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
BACKUP_FILE = BACKUP_DIR / f"behemoth_smoke_{STAMP}.sql"
RESTORE_DB = f"behemoth_restore_{STAMP}"


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def main() -> None:
    print("Creating backup...")
    with BACKUP_FILE.open("wb") as handle:
        subprocess.run(
            ["docker", "compose", "exec", "-T", "db", "pg_dump", "-U", "behemoth", "-d", "behemoth"],
            check=True,
            stdout=handle,
        )

    print("Creating restore database...")
    run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "behemoth",
            "-d",
            "postgres",
            "-c",
            f"CREATE DATABASE {RESTORE_DB};",
        ]
    )

    print("Restoring backup...")
    with BACKUP_FILE.open("rb") as handle:
        subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "db",
                "psql",
                "-U",
                "behemoth",
                "-d",
                RESTORE_DB,
            ],
            check=True,
            stdin=handle,
        )

    print("Dropping restore database...")
    run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "behemoth",
            "-d",
            "postgres",
            "-c",
            f"DROP DATABASE {RESTORE_DB};",
        ]
    )

    print(f"Backup/restore smoke test complete: {BACKUP_FILE}")


if __name__ == "__main__":
    main()

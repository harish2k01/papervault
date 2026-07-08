import os
import subprocess
import sys


def test_document_worker_task_import_configures_mappers() -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from sqlalchemy.orm import configure_mappers; "
                "import papervault_api.worker.tasks.documents; "
                "configure_mappers()"
            ),
        ],
        check=False,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr

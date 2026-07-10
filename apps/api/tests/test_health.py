from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from papervault_api.db.session import get_session
from papervault_api.main import create_app


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_reports_database_failure() -> None:
    app = create_app()

    async def failing_session():
        yield FailingSession()

    app.dependency_overrides[get_session] = failing_session
    client = TestClient(app)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "Database is unavailable"


class FailingSession:
    async def execute(self, _statement):
        raise SQLAlchemyError("database unavailable")

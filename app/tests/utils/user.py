from fastapi.testclient import TestClient

from app.core.config import settings

EMAIL_TEST_USER: str = "test@example.com"
PASSWORD_TEST_USER: str = "testpassword"
USERNAME_TEST_USER: str = "testuser"


def get_user_auth_headers(*, client: TestClient) -> dict[str, str]:
    return _get_token_headers(client, EMAIL_TEST_USER, PASSWORD_TEST_USER)


def get_superuser_auth_headers(client: TestClient) -> dict[str, str]:
    return _get_token_headers(
        client, settings.FIRST_SUPERUSER, settings.FIRST_SUPERUSER_PASSWORD
    )


def _get_token_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    data = {"username": email, "password": password}

    r = client.post(f"{settings.API_V1_STR}/login/access-token", data=data)
    response = r.json()
    auth_token = response["access_token"]
    headers = {"Authorization": f"Bearer {auth_token}"}
    return headers

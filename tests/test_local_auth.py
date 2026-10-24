import re
import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from src import dashboard


class TestLocalDashboardAuth(unittest.TestCase):
    def setUp(self):
        self.password = "a-long-test-password-123"
        self.password_hash_patch = patch.object(
            dashboard,
            "FINANCE_SYNC_PASSWORD_HASH",
            generate_password_hash(self.password, method="scrypt"),
        )
        self.password_hash_patch.start()
        self.addCleanup(self.password_hash_patch.stop)
        self.client = dashboard.app.test_client()

    def test_loopback_bind_needs_no_extra_network_configuration(self):
        for host in ("127.0.0.1", "::1", "localhost"):
            dashboard.validate_dashboard_bind_security(host, "", "", False)

    def test_non_loopback_bind_requires_auth_secret_and_secure_cookie(self):
        with self.assertRaisesRegex(ValueError, "FINANCE_SYNC_PASSWORD_HASH"):
            dashboard.validate_dashboard_bind_security("0.0.0.0", "", "", False)
        with self.assertRaisesRegex(ValueError, "FINANCE_SYNC_SECRET_KEY"):
            dashboard.validate_dashboard_bind_security("0.0.0.0", "hash", "", True)
        with self.assertRaisesRegex(ValueError, "FINANCE_SYNC_COOKIE_SECURE=true"):
            dashboard.validate_dashboard_bind_security("0.0.0.0", "hash", "secret", False)
        dashboard.validate_dashboard_bind_security("0.0.0.0", "hash", "secret", True)

    def _login_csrf_token(self) -> str:
        response = self.client.get("/login")
        match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def test_dashboard_redirects_unauthenticated_browser(self):
        response = self.client.get("/transactions")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_missing_password_configuration_fails_closed_with_setup_instructions(self):
        with patch.object(dashboard, "FINANCE_SYNC_PASSWORD_HASH", ""):
            page_response = self.client.get("/")
            login_response = self.client.get("/login")
            api_response = self.client.get("/api/summary")

        self.assertEqual(page_response.status_code, 302)
        self.assertEqual(login_response.status_code, 503)
        self.assertIn(b"src.local_security_setup", login_response.data)
        self.assertEqual(api_response.status_code, 503)

    def test_api_rejects_unauthenticated_requests(self):
        response = self.client.get("/api/summary")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "Authentication required.")

    def test_login_rejects_invalid_password(self):
        csrf_token = self._login_csrf_token()
        response = self.client.post(
            "/login",
            data={"csrf_token": csrf_token, "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn(b"Password not recognized", response.data)

    def test_login_allows_dashboard_access(self):
        csrf_token = self._login_csrf_token()
        response = self.client.post(
            "/login",
            data={
                "csrf_token": csrf_token,
                "password": self.password,
                "next": "/transactions",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/transactions")
        self.assertEqual(self.client.get("/api/summary").status_code, 200)

    def test_mutating_api_requires_csrf_header(self):
        with self.client.session_transaction() as session:
            session["authenticated"] = True
            session["csrf_token"] = "expected-token"

        rejected = self.client.post(
            "/api/transaction/update",
            json={},
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(rejected.get_json()["error"], "Invalid CSRF token.")

        accepted_by_csrf = self.client.post(
            "/api/transaction/update",
            json={},
            headers={"X-CSRF-Token": "expected-token"},
        )
        self.assertEqual(accepted_by_csrf.status_code, 400)
        self.assertEqual(accepted_by_csrf.get_json()["error"], "Missing transaction_id")


if __name__ == "__main__":
    unittest.main()
"""Post-fix smoke check for the HTTP gateway demo."""

from fastapi.testclient import TestClient

from gateway.app import create_app


def main() -> None:
    client = TestClient(create_app())

    health = client.get("/health")
    assert health.status_code == 200, health.text
    health_payload = health.json()
    assert health_payload["status"] == "ok"
    assert "inventory" in health_payload["services"]

    admin = client.get(
        "/admin/routes",
        headers={"x-api-key": "interview-demo-key"},
    )
    assert admin.status_code == 200, admin.text
    admin_payload = admin.json()
    assert len(admin_payload["routes"]) >= 3

    proxy = client.post(
        "/proxy/inventory",
        headers={"x-api-key": "interview-demo-key"},
        json={
            "path": "/inventory/status",
            "method": "POST",
            "payload": {"order_id": "SO-1001"},
        },
    )
    assert proxy.status_code == 200, proxy.text
    proxy_payload = proxy.json()
    assert proxy_payload["service"] == "inventory"
    assert proxy_payload["upstream_path"] == "/status"
    assert proxy_payload["payload"]["mock"]["status"] == "healthy"

    print("SMOKE PASS")


if __name__ == "__main__":
    main()

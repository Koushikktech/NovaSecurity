from pathlib import Path

from fastapi.testclient import TestClient

from api import app
from config import settings
from persistence.database import init_database
from verification.profiles import get_profile


def test_checkout_endpoint_builds_real_change_with_approved_profile(tmp_path, monkeypatch):
    import routes.v1 as routes

    monkeypatch.setattr(settings, "database_url", "sqlite:///" + str(tmp_path / "db.sqlite"))
    monkeypatch.setattr(settings, "workspace_dir", tmp_path / "workspaces")
    init_database()
    seen = {}

    def worker(run_id, url, base, head, local_dir, **controls):
        try:
            seen.update(label=url, base=base, head=head, root=local_dir)
        finally:
            routes._JOB_SLOTS.release()

    monkeypatch.setattr(routes, "_run_review_background", worker)
    response = TestClient(app).post("/api/v1/examples/checkout", json={"provider": "gemini"})
    assert response.status_code == 202
    assert seen["base"] != seen["head"] and seen["label"] == "Checkout regression demo"
    root = Path(seen["root"])
    assert "discount_cents):" in (root / "shop/pricing.py").read_text()
    assert "quote_total(subtotal_cents)" in (root / "shop/checkout.py").read_text()
    assert "checkout_contract" in (root / ".proofline.yml").read_text()
    profile = get_profile("checkout_contract")
    assert profile.require_base and profile.regression_test_id == "test_checkout_without_coupon"
    assert not (root / "test_checkout.py").exists()

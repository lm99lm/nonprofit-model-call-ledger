from decimal import Decimal
from uuid import UUID

from fastapi.testclient import TestClient

from nonprofit_cost_service import (
    DeliveryDecision,
    ModelCall,
    TextGateway,
    app,
    get_gateway,
)


class FixedCostGateway(TextGateway):
    def create_draft(self, request):
        return ModelCall(
            text=f"Thank you, {request.recipient_name}, for your pantry donation.",
            cost_usd=Decimal("0.013500"),
            vendor="test-vendor",
        )


def test_receipt_over_call_limit_is_held_for_cost_review() -> None:
    app.dependency_overrides[get_gateway] = lambda: FixedCostGateway()
    client = TestClient(app)
    request_id = UUID("a68bea9e-850a-4c9b-8fd4-195881cc78d8")

    response = client.post(
        "/drafts",
        json={
            "request_id": str(request_id),
            "workflow": "donor_receipt",
            "recipient_name": "Maya Chen",
            "context": "Donation: USD 75.00 on 2026-08-15. Campaign: Community pantry.",
            "max_call_cost_usd": "0.010000",
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["call_cost_usd"] == "0.013500"
    assert body["decision"] == DeliveryDecision.REVIEW_COST
    assert body["request_id"] == str(request_id)

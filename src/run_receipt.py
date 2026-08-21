"""Send one donor receipt request through the local service boundary."""

from decimal import Decimal
from uuid import UUID

from nonprofit_cost_service import Workflow, WorkflowRequest, create_workflow_draft, get_gateway


def main() -> None:
    request = WorkflowRequest(
        request_id=UUID("a68bea9e-850a-4c9b-8fd4-195881cc78d8"),
        workflow=Workflow.DONOR_RECEIPT,
        recipient_name="Maya Chen",
        context="Donation: USD 75.00 on 2026-08-15. Campaign: Community pantry.",
        max_call_cost_usd=Decimal("0.020000"),
    )
    result = create_workflow_draft(request, get_gateway())
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

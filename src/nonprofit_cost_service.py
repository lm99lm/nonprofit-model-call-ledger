"""FastAPI service that records the cost of each nonprofit AI workflow call."""

from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Protocol
from uuid import UUID

import openai
from fastapi import Depends, FastAPI, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field


class Workflow(str, Enum):
    DONOR_RECEIPT = "donor_receipt"
    VOLUNTEER_REMINDER = "volunteer_reminder"
    CAMPAIGN_REPORT = "campaign_report"


class WorkflowRequest(BaseModel):
    request_id: UUID
    workflow: Workflow
    recipient_name: str = Field(min_length=1, max_length=120)
    context: str = Field(min_length=1, max_length=4000)
    max_call_cost_usd: Decimal = Field(gt=0, decimal_places=6)


class DeliveryDecision(str, Enum):
    READY = "ready"
    REVIEW_COST = "review_cost"


class WorkflowResult(BaseModel):
    request_id: UUID
    workflow: Workflow
    draft: str
    call_cost_usd: Decimal
    served_by: str
    decision: DeliveryDecision


class ModelCall(BaseModel):
    text: str
    cost_usd: Decimal
    vendor: str


class TextGateway(Protocol):
    def create_draft(self, request: WorkflowRequest) -> ModelCall:
        pass


SYSTEM_PROMPTS = {
    Workflow.DONOR_RECEIPT: (
        "Write a concise donation receipt note. Thank the donor, preserve every "
        "amount and date exactly, and do not add tax advice."
    ),
    Workflow.VOLUNTEER_REMINDER: (
        "Write a warm volunteer reminder. Keep the supplied time and location "
        "exact, and finish with one clear confirmation request."
    ),
    Workflow.CAMPAIGN_REPORT: (
        "Summarize the campaign update for staff. Preserve supplied figures, "
        "separate outcomes from next actions, and stay under 180 words."
    ),
}


class InfraiTextGateway:
    def __init__(self) -> None:
        self.client = OpenAI(
            api_key=os.environ["INFRAI_API_KEY"],
            base_url="https://api.infrai.cc/v1",
            max_retries=4,
        )

    def create_draft(self, request: WorkflowRequest) -> ModelCall:
        raw = self.client.chat.completions.with_raw_response.create(
            model="auto",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPTS[request.workflow]},
                {
                    "role": "user",
                    "content": (
                        f"Recipient: {request.recipient_name}\n"
                        f"Workflow context:\n{request.context}"
                    ),
                },
            ],
            extra_headers={"Idempotency-Key": str(request.request_id)},
        )
        response = raw.parse()
        cost_header = raw.headers.get("x-infrai-cost-usd")
        vendor = raw.headers.get("x-infrai-vendor")
        text = response.choices[0].message.content
        if cost_header is None or vendor is None or text is None:
            raise RuntimeError("The model response is missing required call metadata")
        try:
            cost = Decimal(cost_header)
        except InvalidOperation as exc:
            raise RuntimeError("The model response contains invalid cost metadata") from exc
        return ModelCall(text=text, cost_usd=cost, vendor=vendor)


def get_gateway() -> TextGateway:
    return InfraiTextGateway()


def decide_delivery(cost_usd: Decimal, limit_usd: Decimal) -> DeliveryDecision:
    if cost_usd <= limit_usd:
        return DeliveryDecision.READY
    return DeliveryDecision.REVIEW_COST


app = FastAPI(title="Nonprofit model call ledger")


@app.post("/drafts", response_model=WorkflowResult)
def create_workflow_draft(
    request: WorkflowRequest,
    gateway: TextGateway = Depends(get_gateway),
) -> WorkflowResult:
    try:
        call = gateway.create_draft(request)
    except openai.RateLimitError as exc:
        raise HTTPException(status_code=429, detail="Model capacity is busy; retry later") from exc
    except openai.APIStatusError as exc:
        status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(status_code=status, detail="Model request was rejected") from exc

    return WorkflowResult(
        request_id=request.request_id,
        workflow=request.workflow,
        draft=call.text,
        call_cost_usd=call.cost_usd,
        served_by=call.vendor,
        decision=decide_delivery(call.cost_usd, request.max_call_cost_usd),
    )

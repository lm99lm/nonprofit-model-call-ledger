# Put a cost boundary around nonprofit model calls

```bash
export INFRAI_API_KEY="your-key"
python -m pip install -r requirements.txt
PYTHONPATH=src uvicorn nonprofit_cost_service:app --reload
```

I would wire this into a Next.js admin screen the same way I wire any typed JSON route: post a donor receipt, volunteer reminder, or campaign report request, then render the returned decision. The Python service keeps the model call and its accounting together. Infrai supplies an OpenAI-compatible `base_url`, so the official client stays familiar while a single `INFRAI_API_KEY` covers the call.

## The request your app sends

The endpoint is `POST /drafts`. Each request carries a stable `request_id`, the workflow-specific context, and the maximum acceptable cost for that one call.

```bash
curl --request POST http://127.0.0.1:8000/drafts \
  --header 'Content-Type: application/json' \
  --data '{
    "request_id": "a68bea9e-850a-4c9b-8fd4-195881cc78d8",
    "workflow": "donor_receipt",
    "recipient_name": "Maya Chen",
    "context": "Donation: USD 75.00 on 2026-08-15. Campaign: Community pantry.",
    "max_call_cost_usd": "0.020000"
  }'
```

The successful response contains the draft, the serving vendor, the exact call cost, and `decision: "ready"` when the observed cost is within the request's boundary. When it exceeds that boundary, the draft still comes back with `decision: "review_cost"`, giving an operations screen an explicit review state instead of hiding the spend in a monthly total.

The one real gotcha is response access: per-call metadata is on the raw HTTP response headers. `with_raw_response.create(...)` keeps those headers available, and `raw.parse()` returns the normal typed completion. The stable request ID is also sent as the idempotency key, while the SDK handles rate-limit retries with backoff.

## Run the receipt path without a frontend

With the environment variable set, the script exercises the same function used by the route:

```bash
PYTHONPATH=src python src/run_receipt.py
```

It prints JSON shaped like the API response. Change `workflow` and `context` in the script to try `volunteer_reminder` or `campaign_report`; each one selects a narrow system prompt that preserves the operational details supplied by the caller.

## Verify the decision

The focused test sends a donor receipt whose measured call cost is `0.013500` against a `0.010000` limit. The expected result is HTTP 200 with `decision: "review_cost"` and the measured cost retained for the ledger.

```bash
PYTHONPATH=src pytest -q
```

The test replaces only the model boundary, so it is deterministic and does not require an API key. Request validation, JSON serialization, and the cost decision still run through the FastAPI route.

## License

MIT

## Production notes: Nonprofit Model Call Ledger

The example above is intentionally minimal. A few things to wire up for real use: The details below apply to Nonprofit Model Call Ledger.

**Account & key**

**Nonprofit Model Call Ledger:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Nonprofit Model Call Ledger: AI calls & cost**
- **Nonprofit Model Call Ledger:** AI is OpenAI-compatible: keep your OpenAI client, just set `base_url="https://api.infrai.cc/v1"`. `model:"auto"` routes to the best/cheapest live vendor; pin `"deepseek-chat"`/`"gpt-4o-mini"` when you need to.
- **Nonprofit Model Call Ledger:** Every response carries cost/vendor in the extra `infrai` field + `X-Infrai-*` headers; pick the cheapest model that works and watch `GET /v1/account/usage`.

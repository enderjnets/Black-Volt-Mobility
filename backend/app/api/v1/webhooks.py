"""Square webhooks (PUBLIC, signature-verified): keep subscription rows in sync.

Square posts events server-to-server, so there's no session — the ONLY trust is
the HMAC signature. An unverified or unconfigured request is refused with 403 and
never reaches the handler. The body is read raw (pre-JSON) because the signature
is computed over the exact bytes."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.services import webhooks_square

logger = logging.getLogger("blackvolt.api.webhooks")

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/square")
async def square_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()
    # Square sends the HMAC-SHA256 signature in `x-square-hmacsha256-signature`
    # (the bare `x-square-hmacsha256` name is wrong — verified against a live
    # Square test event, whose header set uses the `-signature` suffix).
    signature = request.headers.get("x-square-hmacsha256-signature", "")
    if not webhooks_square.verify_signature(body=body, signature=signature):
        # Same 403 whether the signature is wrong or webhooks aren't configured —
        # don't reveal which to an unauthenticated caller.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="invalid_signature"
        )
    try:
        event = json.loads(body)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_payload"
        ) from e
    result = await webhooks_square.apply_event(db, event=event)
    return {"ok": True, "result": result}

from __future__ import annotations

import hashlib
import hmac


class WebhookService:
    @staticmethod
    def sign_payload(secret_token: str, body: bytes | str) -> str:
        payload = body.encode() if isinstance(body, str) else body
        return hmac.new(secret_token.encode(), payload, hashlib.sha256).hexdigest()

    @staticmethod
    def next_status(
        current_status: str,
        *,
        success: bool,
        attempt_count: int,
        max_attempts: int,
    ) -> str:
        if current_status in {"succeeded", "dead"}:
            raise ValueError("Cannot transition a terminal webhook delivery status")
        if success:
            return "succeeded"
        if attempt_count >= max_attempts:
            return "dead"
        return "failed_retry"

    @staticmethod
    def should_dispatch(subscribed_events: list[str], event_type: str) -> bool:
        return "*" in subscribed_events or event_type in subscribed_events

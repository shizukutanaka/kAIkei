from app.services.webhook_service import WebhookService


class TestWebhookService:
    def test_sign_payload_is_deterministic_and_secret_sensitive(self):
        payload = '{"event_type":"journal.posted","id":1}'
        sig1 = WebhookService.sign_payload("secret-a", payload)
        sig2 = WebhookService.sign_payload("secret-a", payload)
        sig3 = WebhookService.sign_payload("secret-b", payload)

        assert sig1 == sig2
        assert sig1 != sig3

    def test_next_status_transitions(self):
        assert WebhookService.next_status("pending", success=True, attempt_count=0, max_attempts=5) == "succeeded"
        assert WebhookService.next_status("sending", success=False, attempt_count=1, max_attempts=5) == "failed_retry"
        assert WebhookService.next_status("failed_retry", success=False, attempt_count=5, max_attempts=5) == "dead"
        assert WebhookService.next_status("failed_retry", success=False, attempt_count=6, max_attempts=5) == "dead"

    def test_next_status_rejects_terminal_states(self):
        for current_status in ["succeeded", "dead"]:
            try:
                WebhookService.next_status(current_status, success=False, attempt_count=1, max_attempts=5)
            except ValueError:
                pass
            else:
                raise AssertionError("expected ValueError")

    def test_should_dispatch_supports_exact_and_wildcard(self):
        assert WebhookService.should_dispatch(["journal.posted", "payroll.closed"], "journal.posted") is True
        assert WebhookService.should_dispatch(["*"], "anything.here") is True
        assert WebhookService.should_dispatch(["journal.posted"], "invoice.paid") is False

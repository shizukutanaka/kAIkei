from types import SimpleNamespace

from app.services.notification_service import (
    DELIVERY_CHANNELS,
    VALID_CATEGORIES,
    VALID_PRIORITIES,
    resolve_delivery_channels,
)


def _pref(inapp=True, email=False, push=False, webhook=False):
    return SimpleNamespace(
        channel_inapp=inapp,
        channel_email=email,
        channel_push=push,
        channel_webhook=webhook,
    )


class TestNotificationService:
    def test_valid_categories(self):
        assert "approval" in VALID_CATEGORIES
        assert "journal" in VALID_CATEGORIES
        assert "system" in VALID_CATEGORIES
        assert "ai" in VALID_CATEGORIES

    def test_valid_priorities(self):
        assert "low" in VALID_PRIORITIES
        assert "normal" in VALID_PRIORITIES
        assert "high" in VALID_PRIORITIES
        assert "urgent" in VALID_PRIORITIES

    def test_invalid_category_not_in_set(self):
        assert "invalid_cat" not in VALID_CATEGORIES

    def test_invalid_priority_not_in_set(self):
        assert "critical" not in VALID_PRIORITIES


class TestResolveDeliveryChannels:
    def test_no_preference_defaults_to_inapp(self):
        assert resolve_delivery_channels(None) == ["inapp"]

    def test_all_channels_enabled_preserves_order(self):
        channels = resolve_delivery_channels(
            _pref(inapp=True, email=True, push=True, webhook=True)
        )
        assert channels == list(DELIVERY_CHANNELS)

    def test_inapp_disabled_external_enabled(self):
        channels = resolve_delivery_channels(
            _pref(inapp=False, email=True, webhook=True)
        )
        assert channels == ["email", "webhook"]

    def test_all_disabled_returns_empty(self):
        channels = resolve_delivery_channels(
            _pref(inapp=False, email=False, push=False, webhook=False)
        )
        assert channels == []

    def test_only_inapp(self):
        assert resolve_delivery_channels(_pref()) == ["inapp"]

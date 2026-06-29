import pytest
from uuid import uuid4
from app.services.notification_service import VALID_CATEGORIES, VALID_PRIORITIES


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

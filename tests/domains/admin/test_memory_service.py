"""Tests for admin domain services."""
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.domains.admin.services import AdminMemoryService
from app.domains.subscriptions.models import UserTokenBalance


class TestAdminMemoryService:
    def test_get_platform_overview_sums_balances(self):
        db = MagicMock()
        user_id = uuid4()

        balance = UserTokenBalance(
            user_id=user_id,
            balance=1000,
            total_allocated=2000,
            total_spent=500,
        )

        # Mock aggregate query result
        db.query.return_value.first.return_value = (1000, 2000, 500, 1)
        db.query.return_value.filter.return_value.scalar.return_value = 0

        service = AdminMemoryService(db)
        service.credit = MagicMock()
        overview = service.get_platform_overview()

        assert overview["total_balance"] == 1000
        assert overview["total_allocated"] == 2000
        assert overview["total_spent"] == 500

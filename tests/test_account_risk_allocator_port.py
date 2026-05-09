"""Test AccountRiskAllocatorPort — injectable allocation strategies."""

import pytest

from src.behemoth.risk.account_risk_allocator_port import (
    AllocationDecision,
    DefaultAccountRiskAllocator,
)


class TestAllocationDecision:
    """Test AllocationDecision dataclass."""

    def test_decision_approved(self) -> None:
        """Create an approval decision."""
        d = AllocationDecision(
            candidate_uid="cand_123",
            approved=True,
            selected_exec=1,
            reason="within_budget",
        )
        assert d.approved is True
        assert d.selected_exec == 1

    def test_decision_rejected(self) -> None:
        """Create a rejection decision."""
        d = AllocationDecision(
            candidate_uid="cand_456",
            approved=False,
            selected_exec=0,
            reason="budget_exhausted",
        )
        assert d.approved is False
        assert d.selected_exec == 0

    def test_decision_is_frozen(self) -> None:
        """AllocationDecision is immutable."""
        d = AllocationDecision("cand", True, 1)
        with pytest.raises(AttributeError):
            d.approved = False


class TestDefaultAccountRiskAllocator:
    """Test DefaultAccountRiskAllocator strategy."""

    def test_allocate_all_within_budget(self) -> None:
        """All candidates approved when within budget."""
        allocator = DefaultAccountRiskAllocator()
        candidates = [
            {"candidate_uid": "cand_1", "reserved_loss_ccy": 50.0, "risk_rank_score": 1.0},
            {"candidate_uid": "cand_2", "reserved_loss_ccy": 30.0, "risk_rank_score": 2.0},
        ]
        decisions = allocator.allocate(
            candidates,
            daily_headroom_ccy=200.0,
            max_drawdown_pct=5.0,
            allocator_enabled=True,
        )
        assert len(decisions) == 2
        assert all(d.approved for d in decisions)
        assert all(d.selected_exec == 1 for d in decisions)

    def test_allocate_budget_exhaustion(self) -> None:
        """Lower priority candidates rejected when budget exhausted."""
        allocator = DefaultAccountRiskAllocator()
        candidates = [
            {"candidate_uid": "cand_1", "reserved_loss_ccy": 100.0, "risk_rank_score": 1.0},
            {"candidate_uid": "cand_2", "reserved_loss_ccy": 50.0, "risk_rank_score": 2.0},
            {"candidate_uid": "cand_3", "reserved_loss_ccy": 75.0, "risk_rank_score": 3.0},
        ]
        decisions = allocator.allocate(
            candidates,
            daily_headroom_ccy=150.0,
            max_drawdown_pct=5.0,
            allocator_enabled=True,
        )
        # cand_1 (100) should be approved (priority 1.0)
        # cand_2 (50) should be approved (priority 2.0, budget permits: 150 - 100 = 50)
        # cand_3 (75) should be rejected (no budget: 150 - 100 - 50 = 0)
        assert decisions[0].approved  # cand_1
        assert decisions[1].approved  # cand_2
        assert not decisions[2].approved  # cand_3

    def test_allocate_preserves_input_order(self) -> None:
        """Decisions returned in same order as input candidates."""
        allocator = DefaultAccountRiskAllocator()
        candidates = [
            {"candidate_uid": "cand_z", "reserved_loss_ccy": 10.0, "risk_rank_score": 3.0},
            {"candidate_uid": "cand_a", "reserved_loss_ccy": 10.0, "risk_rank_score": 1.0},
            {"candidate_uid": "cand_m", "reserved_loss_ccy": 10.0, "risk_rank_score": 2.0},
        ]
        decisions = allocator.allocate(
            candidates,
            daily_headroom_ccy=100.0,
            max_drawdown_pct=5.0,
            allocator_enabled=True,
        )
        # Decisions should be in input order: cand_z, cand_a, cand_m
        # But allocations happen in risk_rank_score order: cand_a (1.0), cand_m (2.0), cand_z (3.0)
        assert decisions[0].candidate_uid == "cand_z"
        assert decisions[1].candidate_uid == "cand_a"
        assert decisions[2].candidate_uid == "cand_m"

    def test_allocate_disabled(self) -> None:
        """All candidates approved when allocator is disabled."""
        allocator = DefaultAccountRiskAllocator()
        candidates = [
            {"candidate_uid": "cand_1", "reserved_loss_ccy": 1000.0, "risk_rank_score": 1.0},
            {"candidate_uid": "cand_2", "reserved_loss_ccy": 2000.0, "risk_rank_score": 2.0},
        ]
        decisions = allocator.allocate(
            candidates,
            daily_headroom_ccy=100.0,  # Very low budget
            max_drawdown_pct=5.0,
            allocator_enabled=False,  # Disabled!
        )
        # All should be approved despite budget
        assert all(d.approved for d in decisions)
        assert all(d.selected_exec == 1 for d in decisions)

    def test_allocate_zero_budget(self) -> None:
        """No candidates approved with zero budget."""
        allocator = DefaultAccountRiskAllocator()
        candidates = [
            {"candidate_uid": "cand_1", "reserved_loss_ccy": 10.0, "risk_rank_score": 1.0},
            {"candidate_uid": "cand_2", "reserved_loss_ccy": 10.0, "risk_rank_score": 2.0},
        ]
        decisions = allocator.allocate(
            candidates,
            daily_headroom_ccy=0.0,
            max_drawdown_pct=5.0,
            allocator_enabled=True,
        )
        assert all(not d.approved for d in decisions)

    def test_allocate_missing_fields_defaults(self) -> None:
        """Candidates with missing fields use safe defaults."""
        allocator = DefaultAccountRiskAllocator()
        candidates = [
            {"candidate_uid": "cand_1"},  # Missing reserved_loss_ccy and risk_rank_score
        ]
        decisions = allocator.allocate(
            candidates,
            daily_headroom_ccy=100.0,
            max_drawdown_pct=5.0,
            allocator_enabled=True,
        )
        # Should handle gracefully with defaults
        assert len(decisions) == 1
        assert decisions[0].candidate_uid == "cand_1"

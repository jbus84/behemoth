"""Account Risk Allocator Port — injectable allocation strategy interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AllocationDecision:
    """Outcome of allocating a candidate against the risk budget."""

    candidate_uid: str
    approved: bool  # True if candidate passes the risk gate
    selected_exec: int  # 0 = rejected, 1 = approved
    reason: str | None = None  # Why approved or rejected
    priority_rank: int | None = None  # Allocation priority (lower = higher priority)


class AccountRiskAllocatorPort:
    """Port/interface for account risk allocation strategies.

    Implementations allocate candidates against per-symbol and global budgets,
    deciding which candidates can proceed to execution.
    """

    def allocate(
        self,
        candidates: list[dict[str, Any]],
        *,
        daily_headroom_ccy: float,
        max_drawdown_pct: float,
        allocator_enabled: bool,
    ) -> list[AllocationDecision]:
        """Allocate candidates against the risk budget.

        Args:
            candidates: List of candidate dicts, each with at least:
                - "candidate_uid": str
                - "risk_rank_score": float (lower = higher priority)
            daily_headroom_ccy: Available daily budget in account currency
            max_drawdown_pct: Max allowed drawdown percentage
            allocator_enabled: Whether allocation is enabled

        Returns:
            List of AllocationDecision for each candidate (same order as input)
        """
        raise NotImplementedError


class DefaultAccountRiskAllocator(AccountRiskAllocatorPort):
    """Default allocation strategy: sort by risk_rank_score, allocate in order."""

    def allocate(
        self,
        candidates: list[dict[str, Any]],
        *,
        daily_headroom_ccy: float,
        max_drawdown_pct: float,
        allocator_enabled: bool,
    ) -> list[AllocationDecision]:
        """Allocate candidates in risk_rank_score order until budget exhausted."""
        if not allocator_enabled:
            # All candidates approved (no allocation)
            return [
                AllocationDecision(
                    candidate_uid=c.get("candidate_uid", "unknown"),
                    approved=True,
                    selected_exec=1,
                    reason="allocator_disabled",
                )
                for c in candidates
            ]

        # Sort by risk_rank_score (lower = higher priority)
        ranked = sorted(
            enumerate(candidates),
            key=lambda x: x[1].get("risk_rank_score", float("inf")),
        )

        decisions: list[AllocationDecision] = [None] * len(candidates)  # type: ignore
        remaining_budget = daily_headroom_ccy

        for orig_idx, cand in ranked:
            uid = cand.get("candidate_uid", "unknown")
            reserved_loss = cand.get("reserved_loss_ccy", 0.0)

            if remaining_budget >= reserved_loss:
                # Approve
                remaining_budget -= reserved_loss
                decisions[orig_idx] = AllocationDecision(
                    candidate_uid=uid,
                    approved=True,
                    selected_exec=1,
                    reason="within_budget",
                    priority_rank=len([d for d in decisions if d is not None and d.approved]),
                )
            else:
                # Reject
                decisions[orig_idx] = AllocationDecision(
                    candidate_uid=uid,
                    approved=False,
                    selected_exec=0,
                    reason="budget_exhausted",
                )

        return decisions

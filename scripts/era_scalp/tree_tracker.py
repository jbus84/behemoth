"""Persistent tree tracking for ERA-PUCT search.

Tracks branch performance, concept lineage, and visit counts across runs
so subsequent searches can warm-start with historical priors.

File layout (all under data/era_trees/):
  {symbol}_nodes.jsonl      — per-node records (append-only)
  {symbol}_branch_stats.json — accumulated branch statistics
  {symbol}_concept_stats.json — accumulated concept statistics
  {symbol}_runs.jsonl        — per-run metadata
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── Data structures ─────────────────────────────────────────────────────────

@dataclass
class NodeRecord:
    """Immutable record of a single evaluated node/program."""
    run_id: str
    hash: str
    branch: str
    concepts: list[str]
    score: float
    mean: float
    se: float
    parent_hash: str | None
    generation: int
    holdout_p: float | None = None
    holdout_raw: float | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "NodeRecord":
        return cls(**d)


@dataclass
class BranchStats:
    """Accumulated statistics for one branch across all runs."""
    branch: str
    runs: int = 0
    nodes: int = 0
    visits: int = 0
    avg_score: float = 0.0
    best_score: float = -1e18
    best_hash: str | None = None
    last_seen: str = ""

    def add(self, score: float, node_hash: str, run_id: str):
        """Incorporate one node's score into accumulated stats."""
        self.nodes += 1
        self.visits += 1
        self.avg_score = (self.avg_score * (self.nodes - 1) + score) / self.nodes
        if score > self.best_score:
            self.best_score = score
            self.best_hash = node_hash
        self.last_seen = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "BranchStats":
        return cls(**{k: v for k, v in d.items() if k in {f.name for f in cls.__dataclass_fields__.values()}})


@dataclass
class ConceptStats:
    """Accumulated statistics for one atomic concept across all runs."""
    concept: str
    category: str = ""
    runs: int = 0
    nodes: int = 0
    visits: int = 0
    avg_score: float = 0.0
    best_score: float = -1e18
    best_hash: str | None = None
    last_seen: str = ""
    # Synergy tracking: which other concepts co-occur with this one in top programs
    co_occurrence: dict[str, int] = field(default_factory=dict)

    def add(self, score: float, node_hash: str, concepts: list[str]):
        """Incorporate one node's score and update co-occurrence counts."""
        self.nodes += 1
        self.visits += 1
        self.avg_score = (self.avg_score * (self.nodes - 1) + score) / self.nodes
        if score > self.best_score:
            self.best_score = score
            self.best_hash = node_hash
        self.last_seen = datetime.now(timezone.utc).isoformat()
        for c in concepts:
            if c != self.concept:
                self.co_occurrence[c] = self.co_occurrence.get(c, 0) + 1

    def to_dict(self) -> dict:
        d = asdict(self)
        # JSON keys must be strings
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ConceptStats":
        return cls(
            concept=d["concept"],
            category=d.get("category", ""),
            runs=d.get("runs", 0),
            nodes=d.get("nodes", 0),
            visits=d.get("visits", 0),
            avg_score=d.get("avg_score", 0.0),
            best_score=d.get("best_score", -1e18),
            best_hash=d.get("best_hash"),
            last_seen=d.get("last_seen", ""),
            co_occurrence=d.get("co_occurrence", {}),
        )


# ── TreeTracker class ──────────────────────────────────────────────────────

class TreeTracker:
    """Persistent tracking of ERA-PUCT tree searches.

    Usage:
        tracker = TreeTracker("EURUSD")
        tracker.start_run(budget=100, seed=42, mode="fair_price")
        for node in nodes:
            tracker.log_node(node)
        tracker.end_run()

        # Later: warm-start priors
        priors = tracker.compute_branch_priors()
        concept_priors = tracker.compute_concept_priors()
    """

    def __init__(self, symbol: str, root: Path | None = None):
        self.symbol = symbol
        self.root = root or Path("data/era_trees")
        self.root.mkdir(parents=True, exist_ok=True)
        self.nodes_file = self.root / f"{symbol}_nodes.jsonl"
        self.branch_file = self.root / f"{symbol}_branch_stats.json"
        self.concept_file = self.root / f"{symbol}_concept_stats.json"
        self.runs_file = self.root / f"{symbol}_runs.jsonl"

        self._run_id: str | None = None
        self._branch_stats: dict[str, BranchStats] = {}
        self._concept_stats: dict[str, ConceptStats] = {}
        self._load_accumulated()

    def _load_accumulated(self):
        """Load existing branch/concept stats from disk."""
        if self.branch_file.exists():
            data = json.loads(self.branch_file.read_text())
            self._branch_stats = {k: BranchStats.from_dict(v) for k, v in data.items()}
        if self.concept_file.exists():
            data = json.loads(self.concept_file.read_text())
            self._concept_stats = {k: ConceptStats.from_dict(v) for k, v in data.items()}

    def _save_accumulated(self):
        """Write accumulated stats to disk."""
        self.branch_file.write_text(
            json.dumps({k: v.to_dict() for k, v in self._branch_stats.items()}, indent=2)
        )
        self.concept_file.write_text(
            json.dumps({k: v.to_dict() for k, v in self._concept_stats.items()}, indent=2)
        )

    def start_run(self, budget: int, seed: int, mode: str = "fair_price",
                  extra_meta: dict | None = None):
        """Begin tracking a new PUCT run."""
        self._run_id = datetime.now(timezone.utc).isoformat()
        meta = {
            "run_id": self._run_id,
            "symbol": self.symbol,
            "budget": budget,
            "seed": seed,
            "mode": mode,
            "started": self._run_id,
            **(extra_meta or {}),
        }
        with self.runs_file.open("a") as f:
            f.write(json.dumps(meta) + "\n")

    def end_run(self, extra_meta: dict | None = None):
        """Finalize tracking and write accumulated stats."""
        if self._run_id is None:
            return
        meta = {
            "run_id": self._run_id,
            "ended": datetime.now(timezone.utc).isoformat(),
            **(extra_meta or {}),
        }
        with self.runs_file.open("a") as f:
            f.write(json.dumps(meta) + "\n")
        self._save_accumulated()
        self._run_id = None

    def _hash_payload(self, payload: str) -> str:
        return hashlib.sha256(payload.encode()).hexdigest()[:12]

    def log_node(self, payload: str, branch: str, concepts: list[str],
                 score: float, mean: float, se: float,
                 parent_payload: str | None = None,
                 generation: int = 0,
                 holdout_p: float | None = None,
                 holdout_raw: float | None = None):
        """Log a single evaluated node."""
        if self._run_id is None:
            return  # not in an active run

        h = self._hash_payload(payload)
        parent_h = self._hash_payload(parent_payload) if parent_payload else None

        rec = NodeRecord(
            run_id=self._run_id,
            hash=h,
            branch=branch,
            concepts=concepts,
            score=score,
            mean=mean,
            se=se,
            parent_hash=parent_h,
            generation=generation,
            holdout_p=holdout_p,
            holdout_raw=holdout_raw,
        )

        # Append to nodes JSONL
        with self.nodes_file.open("a") as f:
            f.write(json.dumps(rec.to_dict()) + "\n")

        # Update branch stats
        if branch not in self._branch_stats:
            self._branch_stats[branch] = BranchStats(branch=branch)
        self._branch_stats[branch].add(score, h, self._run_id)

        # Update concept stats
        for c in concepts:
            if c not in self._concept_stats:
                self._concept_stats[c] = ConceptStats(concept=c)
            self._concept_stats[c].add(score, h, concepts)

    def compute_branch_priors(self, min_prior: float = 0.5, max_prior: float = 2.0) -> dict[str, float]:
        """Compute branch priors from accumulated historical stats.

        Uses the *best_score* per branch (not avg) so that even rarely-used
        branches with one strong program get a fair prior.
        """
        if not self._branch_stats:
            return {}
        scores = {b: s.best_score for b, s in self._branch_stats.items()}
        lo, hi = min(scores.values()), max(scores.values())
        span = hi - lo
        if span <= 0:
            return {b: 1.0 for b in scores}
        priors = {}
        for b, best in scores.items():
            normalized = (best - lo) / span
            priors[b] = min_prior + normalized * (max_prior - min_prior)
        return priors

    def compute_concept_priors(self, min_prior: float = 0.5, max_prior: float = 2.0) -> dict[str, float]:
        """Compute concept-level priors from accumulated stats."""
        if not self._concept_stats:
            return {}
        scores = {c: s.best_score for c, s in self._concept_stats.items()}
        lo, hi = min(scores.values()), max(scores.values())
        span = hi - lo
        if span <= 0:
            return {c: 1.0 for c in scores}
        priors = {}
        for c, best in scores.items():
            normalized = (best - lo) / span
            priors[c] = min_prior + normalized * (max_prior - min_prior)
        return priors

    def concept_synergy_bonus(self, concepts: list[str], c_synergy: float = 0.1) -> float:
        """Compute a synergy bonus for a set of concepts based on co-occurrence.

        Concepts that frequently appear together in successful programs
        get a bonus when co-occurring.
        """
        bonus = 0.0
        for i, c1 in enumerate(concepts):
            for c2 in concepts[i + 1 :]:
                if c1 in self._concept_stats and c2 in self._concept_stats:
                    co = self._concept_stats[c1].co_occurrence.get(c2, 0)
                    if co > 0:
                        bonus += c_synergy * np.log1p(co)
        return bonus

    def get_branch_history(self, branch: str) -> dict:
        """Return accumulated stats for a branch."""
        if branch in self._branch_stats:
            return self._branch_stats[branch].to_dict()
        return {}

    def get_concept_history(self, concept: str) -> dict:
        """Return accumulated stats for a concept."""
        if concept in self._concept_stats:
            return self._concept_stats[concept].to_dict()
        return {}

    def summary(self) -> dict:
        """High-level summary of all tracked data."""
        return {
            "symbol": self.symbol,
            "branches_tracked": len(self._branch_stats),
            "concepts_tracked": len(self._concept_stats),
            "top_branches": sorted(
                [(b, s.best_score, s.nodes) for b, s in self._branch_stats.items()],
                key=lambda x: x[1], reverse=True,
            )[:5],
            "top_concepts": sorted(
                [(c, s.best_score, s.nodes) for c, s in self._concept_stats.items()],
                key=lambda x: x[1], reverse=True,
            )[:10],
        }


# Need numpy for synergy calculation
import numpy as np  # noqa: E402

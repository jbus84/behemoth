from __future__ import annotations

import sys

import pytest

import scripts.run_promote_live as run_promote_live


def test_main_archives_candidate_build_bundle(monkeypatch, tmp_path) -> None:
    verify_calls: list[str] = []
    copy_calls: list[tuple[str, str]] = []
    build_bundle_dir = tmp_path / "configs/research/governance/oco_candidate_builds/2026-02"
    build_bundle_dir.mkdir(parents=True)
    (build_bundle_dir / "lock.json").write_text("{\"month\": \"2026-02\"}\n")
    archive_dir = tmp_path / "configs/research/governance/oco_history_dukascopy_candidate"
    archive_dir.mkdir(parents=True)
    (archive_dir / "stale.txt").write_text("stale\n")

    def fake_copytree(src, dst):
        copy_calls.append((str(src), str(dst)))
        return dst

    monkeypatch.setattr(run_promote_live.shutil, "copytree", fake_copytree)
    monkeypatch.setattr(run_promote_live, "_verify_cert", lambda report_dir: verify_calls.append(report_dir))
    monkeypatch.setattr(run_promote_live, "_last_complete_month", lambda override=None: "2026-02")
    monkeypatch.setattr(run_promote_live, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", ["run_promote_live.py", "--report-dir", "data/analysis/backtest_reconcile"])

    run_promote_live.main()

    assert verify_calls == ["data/analysis/backtest_reconcile"]
    assert copy_calls == [
        (
            str(build_bundle_dir),
            str(archive_dir / "2026-02"),
        )
    ]


def test_main_requires_existing_build_bundle(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(run_promote_live, "_verify_cert", lambda report_dir: None)
    monkeypatch.setattr(run_promote_live, "_last_complete_month", lambda override=None: "2026-02")
    monkeypatch.setattr(run_promote_live, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", ["run_promote_live.py", "--report-dir", "data/analysis/backtest_reconcile"])

    with pytest.raises(
        SystemExit,
        match=r"run make monthly-build and make monthly-recert first",
    ):
        run_promote_live.main()

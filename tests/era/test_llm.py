from scripts.era.llm import (
    build_prompt,
    build_recombine_prompt,
    extract_program,
    propose_program,
    recombine_program,
)


def test_prompt_includes_parent_context():
    p = build_prompt(
        "def residual(ctx): return ctx.target_col()",
        -0.5,
        "exec: nan residual",
        "use leave-one-out",
    )
    assert "residual(ctx)" in p and "-0.5" in p and "leave-one-out" in p
    assert "y_fwd" in p.lower()  # the causal rule is stated
    assert "ctx.hour" in p  # gating capability documented


def test_extract_program_from_fenced_block():
    resp = "Here:\n```python\ndef residual(ctx):\n    return ctx.target_col()\n```\n"
    src = extract_program(resp)
    assert src.strip().startswith("def residual(ctx):")


def test_propose_uses_caller_and_caches(tmp_path):
    calls = []

    def fake_caller(prompt: str) -> str:
        calls.append(prompt)
        return "```python\ndef residual(ctx):\n    return ctx.target_col()\n```"

    src1 = propose_program(
        "def residual(ctx): return ctx.target_col()",
        0.0,
        "",
        "idea",
        cache_dir=tmp_path,
        caller=fake_caller,
    )
    src2 = propose_program(
        "def residual(ctx): return ctx.target_col()",
        0.0,
        "",
        "idea",
        cache_dir=tmp_path,
        caller=fake_caller,
    )
    assert src1 == src2
    assert len(calls) == 1  # second call served from cache


def test_recombine_prompt_includes_both_parents():
    srcA = "def residual(ctx): return ctx.target_col()"
    srcB = "def residual(ctx): return ctx.dispersion()"
    p = build_recombine_prompt(srcA, 0.5, srcB, 0.3)
    assert srcA in p and srcB in p
    assert "0.5" in p and "0.3" in p
    assert "residual(ctx)" in p
    assert "y_fwd" in p.lower()  # causal rule stated


def test_recombine_uses_caller_and_caches(tmp_path):
    calls = []

    def fake_caller(prompt: str) -> str:
        calls.append(prompt)
        return "```python\ndef residual(ctx):\n    return ctx.dispersion()\n```"

    srcA = "def residual(ctx): return ctx.target_col()"
    srcB = "def residual(ctx): return ctx.peers()"
    src1 = recombine_program(srcA, 0.5, srcB, 0.4, cache_dir=tmp_path, caller=fake_caller)
    src2 = recombine_program(srcA, 0.5, srcB, 0.4, cache_dir=tmp_path, caller=fake_caller)
    assert src1 == src2
    assert len(calls) == 1  # second call served from cache


def test_rules_describe_causal_time_axis():
    p = build_prompt("def residual(ctx):\n    return ctx.target_col()\n", 0.0, "", "idea")
    low = p.lower()
    # writer must know it has the full time axis...
    assert "n_bars" in low and ("trailing" in low or "expanding" in low)
    # ...but must never read future bars (probe will reject otherwise)
    assert "future" in low
    assert "ewma" in low or "rolling" in low

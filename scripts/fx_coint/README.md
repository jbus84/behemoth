# FX intraday tail edge — why the model is OLS-linear, and why nothing beats it

This is the core idea behind the EUR/GBP/JPY 2h tail-momentum work in this directory.
It is a justification, derived from the empirical sweeps in the scripts here, for why a
plain linear projection (OLS ≈ Ridge) is not merely "good enough" but the *theoretically
matched* estimator — and why every fancier alternative (heavy-tailed / robust losses,
GAMLSS, gradient boosting, Lasso, equal-weighting) is worse.

## The signal is what it is: a dense, weak, near-linear momentum tilt in heavy-tailed noise

The economic effect is intraday momentum/underreaction — the next-bar return is faintly
positively autocorrelated with recent return over the active session. That predictive
structure is *literally a positive coefficient on lagged returns* (an AR/momentum term).
The data-generating predictive relationship is therefore **intrinsically linear** — a
projection onto past returns, not a curved manifold. A linear model is the right functional
form not by luck but because the phenomenon itself is a linear autocorrelation. Per-feature
R² is ~0.001 and kurtosis ~91: a tiny dense signal buried in fat-tailed noise. Two facts —
*near-linear* and *signal co-located with the tails* — explain everything below.

## 1. Why OLS = Ridge (shrinkage is a no-op)

Ridge only departs from OLS when the design matrix is ill-conditioned or p≈N. Neither holds:
after standardization the 5 features (two momentum horizons, vol, hour, lag-return) are
near-orthogonal, and N ≫ p (hundreds–thousands of bars vs 5 coefficients). With well-conditioned
X and large N, the OLS coefficient covariance is already small, so the L2 penalty has almost
nothing to shrink — α from 0.1 to 100 moves the solution negligibly. **The edge is the bare
linear projection; regularization isn't doing the work, so it can't be a shrinkage artifact
either.** A robustness confirmation, not a disappointment.

## 2. Why heavy-tailed / robust loss HURTS (the deepest reason)

A Student-t / Huber / GAMLSS estimator assumes large-magnitude observations are **noise
outliers** and down-weights them — that is the entire premise of robust estimation. The fitted
ν≈2–3 confirms the returns *are* that heavy-tailed. **But here the predictive signal is positively
correlated with magnitude:** momentum continuation is strongest in the large moves (big trends
persist). So the tail observations are not noise to discount — they are the *highest-information*
observations for the conditional mean. Robustifying throws away exactly the data that carries the
edge, which is why net collapsed +1.28 → +0.21 as ν dropped.

Underneath sits an exact alignment: **the trading objective is the mean net return of the
selected basket** — and the mean is an L2 functional. OLS is the estimator whose loss (squared
error) is *congruent* with that objective; it up-weights large residuals, pointing the estimator's
attention precisely where the P&L is made. Median / quantile / Huber optimize a robustified center —
a different functional that the P&L does not reward. **You get what you optimize for: if you trade
the mean of the tail, estimate with the mean-consistent loss.** The right distribution for
*describing* these returns is the wrong loss for *ranking* them.

## 3. Why nonlinear boosting HURTS

**Bias–variance.** The true conditional-mean function is ~linear and monotone in momentum. A
flexible learner must rediscover that simple shape from data with R²≈0.001 and kurtosis 91. There
is essentially no nonlinear bias to remove, but enormous noise to overfit — so added capacity is
pure variance. That is why depth-3 < depth-2 < linear: every increment of flexibility fits noise.
Boosting wins when the truth is complex and data is plentiful relative to noise; this is the
opposite regime.

**The one real nonlinearity is unobservable at decision time.** The regime-convexity (momentum
pays in trend, whipsaws in chop) is genuine, but it is driven by a *latent, slow-moving state*
(trend vs chop) that plays out over quarters and is **not encoded in the instantaneous features**.
To exploit it a model would need to know the future regime — unknowable when you trade. So
conditioning harder on X cannot recover it; it can only fit in-sample noise. The convexity explains
why the edge *varies across years*, but it is not a tradable conditioning signal, so no amount of
model capacity monetizes it. (Same cause as the failed linear regime-interaction-terms experiment.)

## 4. Why sparsity (Lasso) and equal-weight HURT

**Lasso** assumes a *sparse* truth — a few strong features, the rest exactly zero. Here the truth
is the opposite: **many weak, all-relevant features**, each momentum horizon and the vol-normalizer
adding a small independent increment to a low-SNR composite. L1 forces exact zeros, discarding
usable information, and at low SNR over-shrinks to near-tied predictions (the degenerate n=2481
selection). Dense-weak-signal is the canonical regime where ridge/OLS dominate lasso.

**Equal-weight** ignores the relative scaling and sign the data assigns to the features — a
misspecified combination. Its apparent positive mean came from a handful of outlier days (the heavy
tails again), which is exactly why the day-clustered test exposed it as negative. Fitting the
weights, even with OLS, is what produces a *consistent daily* edge rather than an outlier-driven one.

## The unifying principle

This is a textbook instance of one statistical regime: **a dense, weak, near-linear conditional
mean, embedded in heavy-tailed noise whose magnitude is positively correlated with the signal, with
N ≫ p and a well-conditioned design.** In that regime the Gauss–Markov / James–Stein logic is
unambiguous:

- Linear truth + N≫p + well-conditioned X → **OLS is (near-)BLUE; shrinkage and flexibility have
  nothing to gain.**
- Objective = mean of selected trades → **L2 estimation is the congruent loss.**
- Tails carry signal, not noise → **robustification is actively counterproductive.**
- The only nonlinearity is an unobserved latent regime → **not learnable from the available
  features at all.**

So OLS-linear is not winning a horse race by a nose — it is the estimator matched to the structure
of the problem on all four axes simultaneously. Every alternative fails because it imposes an
assumption the data violates (sparsity, ill-conditioning, outlier-tails, or rich nonlinearity), and
there is consequently **no model lever left to pull.** The binding constraints are real-world ones —
statistical power (few independent tail events) and the unobservable chop regime — and the only
escape is *more orthogonal data* (a tight-cost, independent market), not a better model.

## Scripts

| script | what it shows |
|---|---|
| `tail_mu_durability.py` | deployable top-5% basket is durable (5/5 positive years, recent half day-clustered p=0.027); realistic Razor cost vs inflated Dukascopy feed cost; edge is signal-specific to EUR/GBP/JPY |
| `tail_gamlss_quantile.py` | GAMLSS upper-quantile ranking and σ/skew gates fail *in the tail we trade* |
| `tail_robust_location.py` | Huber / median location ranking < Ridge — down-weighting tails destroys the edge |
| `tail_student_t.py` | real Student-t and location-scale GAMLSS-t (fitted ν≈2–3) collapse the edge |
| `tail_boosting.py` | gradient boosting (all variants) ~half Ridge and loses significance — overfits a near-linear signal |
| `tail_linear_sweep.py` | nothing in the linear family beats Ridge; Ridge ≈ OLS (penalty is a no-op) |
| `tail_15m_gamlss.py` | shorter timeframes (15m/30m) strictly worse — fixed cost eats the shrinking gross |

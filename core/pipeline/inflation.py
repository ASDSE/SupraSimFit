"""How much wider than the profile assumes the spread of each fitted Ka is: the factor its cut-off is widened by.

The profile-likelihood interval of a Ka takes the residual of the fit as the
whole of its noise, with one variance at every (whitened) titration point:
``cut = S_min (1 + m F(m, n - p) / (n - p))``. Two things the user's data can
state make that wrong.

- A noise law read off the replicates (:mod:`core.pipeline.noise`) weights the
  points by a share of proportional noise that a handful of replicates
  determine only loosely. Under any other share the scatter has another shape,
  and the share the weights were built from is one of many the replicates
  accept.
- A random error of each titrant addition (:class:`~core.pipeline.inputs.AdditionError`)
  moves every point along the titrant axis. For additions into one cuvette
  most of it moves the whole curve the way another Ka would, so the residual
  shows little of it while the Ka carries it all.

The factor is a misspecification design effect. Let ``J = [C | K]`` be the
Jacobian of the whitened fitted curve: ``C`` the signal columns the fit left
strictly inside their bounds, ``K`` the derivative per decade of every free Ka
with the signal coefficients held (a Ka on its bound keeps its column: its
estimate is still a function of the data). Partialling the signal parameters
out, ``Q = (I - P_C) K`` and ``M = (Q'Q)⁻¹ Q'`` give the linearised Ka
estimates, whose variance under a covariance ``Ω`` of the whitened residual
rows is the sandwich ``M Ω M'``, while the profile assumes ``σ̂² (Q'Q)⁻¹`` with
``σ̂² = S / (n - p)``, ``S`` the best residual as the cut-off floors it and
``p`` the rank of ``J``. The factor of Ka ``k`` is their ratio,

    kappa_k = (M Ω M')_kk / (σ̂² (Q'Q)⁻¹_kk),

and under misspecification the profile's likelihood-ratio statistic over
``kappa`` follows the reference it was built on (Kent 1982, Biometrika 69:19),
which is the design-effect correction of Rao & Scott (1984, Ann. Stat. 12:46)
and the robust adjusted likelihood of Royall & Tsou (2003, JRSS-B 65:391).

One covariance carries both sources, ``Ω(λ) = σ²_PM D̃_λ + G_w``:

- ``G_w = s² W^½ H H' W^½`` is the covariance the additions put on the whitened
  points, ``H = diag(f') L`` (:func:`addition_signal_loading`), ``s`` the
  relative error of one addition, and ``s²`` divided by the number of
  replicates averaged when each is a titration of its own.
- ``σ²_PM`` is the residual variance beside it, read on the residual space
  (:func:`paule_mandel`): the root of ``(N'r)' (σ² I + N' G_w N)⁻¹ (N'r) = n - p``
  on the whitened residual ``r``, ``N`` an orthonormal basis of the complement
  of ``[C | K]``, between ``10⁻¹² σ̂²`` (the numerical zero it is truncated
  to) and ``σ̂²``, which it is without additions.
- ``D_λ = g(λ) / g(λ̂)`` is the variance of every point under the share ``λ``
  over the variance the weights assume, and ``D̃_λ`` is it scaled so that
  ``tr((I - H_J) D̃_λ) = n - p``: the residual variance ``σ²_PM`` the fit
  reads is spread over the points in the shape ``λ`` gives it. ``D̃ = I``
  without a law.

The factor is the largest over the shares the replicates accept at 99 %
(``NoiseLaw.share_set``), the device of Berger & Boos (1994, JASA 89:1012) for
a nuisance parameter known only to a confidence set, and never below 1, so no
cut-off is tighter than the plain F test's. It is not monotone in what is
stated: with additions the residual variance beside them is ``σ²_PM <= σ̂²``,
so a factor that carries a law and additions can come out below the factor of
the law alone, which the conditional interval carries. Without a law of positive share and
without additions every factor is exactly 1.0, computed from nothing, so the
cut-off multiplies by 1.0 and the interval is the profile's own to the last bit.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping, Sequence

import numpy as np
from scipy.optimize import brentq

from core.pipeline.inputs import AdditionError, addition_loading
from core.pipeline.noise import NoiseLaw
from core.pipeline.varpro import ProjectedFit, Projection
from core.units import Q_

__all__ = [
    'addition_signal_loading',
    'inflation',
    'joint_inflation',
    'paule_mandel',
    'replicate_scatter_ssr',
    'residual_space',
]

# Step of the central difference of a Ka column, in decades: far below the
# curvature of any registered model in log Ka, far above rounding.
_LOG_KA_STEP = 1e-4

# Step of the central difference of the signal along the titrant axis, as a
# fraction of the largest titrant concentration.
_TITRANT_STEP = 1e-6

# Singular values below this fraction of the largest count as zero in the rank
# of the Jacobian and the basis of the signal columns.
_RANK_RTOL = 1e-10

# The lowest residual variance beside the additions, as a fraction of the
# fit's own: the numerical zero a Paule-Mandel root below it is truncated to.
_PM_FLOOR = 1e-12

# Shares between the ends of the accepted set are taken 0.01 apart, the
# resolution the law reports its share to.
_SHARE_STEP = 0.01


def addition_signal_loading(
    projection: Projection,
    ka: Mapping[str, float],
    input_offsets: Mapping[str, float] | None,
    additions: AdditionError,
    titrant_stock: float | None,
) -> np.ndarray:
    """The change of the fitted signal at every point per unit relative error of every addition.

    ``H = diag(f') L`` in au: ``L`` the :func:`~core.pipeline.inputs.addition_loading`
    of the titrant series and ``f'_i`` the slope of the fitted curve along the
    titrant axis at point ``i``, with the signal coefficients held at their
    bounded least-squares values. Every point's signal depends on its own
    titrant concentration alone, so two species solves, at ``x + h`` and
    ``x - h``, give every slope as a central difference; a point closer to
    zero than ``h`` takes its lower end at zero. The stock, where one is
    declared, is held.

    Parameters
    ----------
    projection : Projection
        The projection of the fit, single row.
    ka : Mapping[str, float]
        The binding constants of the fit.
    input_offsets : Mapping[str, float] or None
        The relative offsets of the entered inputs at the fit; ``None`` or
        empty for the inputs as entered.
    additions : AdditionError
        The stated error of the additions; only *sequential* is read.
    titrant_stock : float or None
        The titrant stock in M of the assay at *input_offsets*; ``None`` when
        no dilution is declared.

    Returns
    -------
    np.ndarray
        Shape ``(n, n)``, row ``i`` the point and column ``j`` the addition.
    """
    assay = projection.assay.with_inputs(input_offsets) if input_offsets else projection.assay
    coefficients = projection._solve_at(ka, input_offsets)[2][0]
    x = assay.x_data.magnitude
    step = _TITRANT_STEP * float(np.max(x))
    upper, lower = x + step, np.maximum(x - step, 0.0)
    rise = (
        projection._design(ka, replace(assay, x_data=Q_(upper, 'M')))
        - projection._design(ka, replace(assay, x_data=Q_(lower, 'M')))
    ) @ coefficients
    slope = rise / (upper - lower)
    return slope[:, np.newaxis] * addition_loading(x, additions.sequential, titrant_stock)


def inflation(
    projection: Projection,
    fit: ProjectedFit,
    *,
    law: NoiseLaw | None = None,
    curve: np.ndarray | None = None,
    additions: AdditionError | None = None,
    n_replicates: int = 1,
    titrant_stock: float | None = None,
) -> dict[str, float]:
    """The factor ``kappa >= 1`` the cut-off of every free Ka's interval is widened by.

    Parameters
    ----------
    projection : Projection
        The single-row projection the fit was made on, with the point weights
        it was made with.
    fit : ProjectedFit
        The conditional fit.
    law : NoiseLaw, optional
        The noise law the point weights come from. It counts only when it was
        estimated and its share is above zero.
    curve : np.ndarray, optional
        The signal the point weights were computed at: the fitted curve when
        the fit was refitted with weights from it, the projection's own signal
        (the mean of the replicates) when omitted.
    additions : AdditionError, optional
        The stated random error of each titrant addition.
    n_replicates : int
        How many replicates the projection's signal is the mean of.
    titrant_stock : float, optional
        The titrant stock in M; ``None`` when no dilution is declared.

    Returns
    -------
    dict[str, float]
        One factor per free Ka of the projection. Exactly 1.0 for every Ka,
        computed from nothing, when neither a law of positive share nor
        additions apply; 1.0 for a Ka whose factor is not a finite number.
    """
    found = _factors(projection, fit, law, curve, additions, n_replicates, titrant_stock)
    if found is None:
        return {key: 1.0 for key in projection.free_ka}
    sandwich, model = found
    with np.errstate(divide='ignore', invalid='ignore'):
        ratios = np.array([np.diagonal(v) / np.diagonal(model) for v in sandwich])
    ratios = np.where(np.isfinite(ratios), ratios, 1.0)
    return {key: float(max(1.0, ratios[:, j].max())) for j, key in enumerate(projection.free_ka)}


def joint_inflation(
    projection: Projection,
    fit: ProjectedFit,
    *,
    law: NoiseLaw | None = None,
    curve: np.ndarray | None = None,
    additions: AdditionError | None = None,
    n_replicates: int = 1,
    titrant_stock: float | None = None,
) -> float:
    """The factor ``>= 1`` the cut-off of the joint region of two free Ka is widened by.

    The first-order Rao-Scott factor: the mean eigenvalue of the profile's
    covariance of the two Ka inverted times their sandwich covariance,
    ``tr(A⁻¹ V) / 2`` with ``A = σ̂² (Q'Q)⁻¹`` and ``V = M Ω M'``, the largest
    over the accepted shares. It lies between the smallest and the largest
    eigenvalue of ``A⁻¹ V``, as each Ka's own factor before the floor at 1
    does; it is the mean of the two where the profile takes the two estimates
    as uncorrelated, and equals both where ``V`` is a multiple of ``A``. The
    arguments and the cases of exactly 1.0 are those of :func:`inflation`; a
    model with other than two free Ka has no joint region and gets 1.0.
    """
    if len(projection.free_ka) != 2:
        return 1.0
    found = _factors(projection, fit, law, curve, additions, n_replicates, titrant_stock)
    if found is None:
        return 1.0
    sandwich, model = found
    try:
        means = [float(np.trace(np.linalg.solve(model, v))) / 2.0 for v in sandwich]
    except np.linalg.LinAlgError:
        return 1.0
    means = [value for value in means if np.isfinite(value)]
    return max([1.0, *means])


def replicate_scatter_ssr(
    rows: Sequence[tuple[Projection, ProjectedFit]], additions: AdditionError, titrant_stock: float | None = None
) -> list[float] | None:
    """The residual of every replicate with the residue of its own addition errors taken out, for Cochran's test.

    Each replicate a titration of its own, its residual ``r_r`` carries noise
    of a variance ``σ²`` common to all of them under the test's null and the
    residue of its own additions, of covariance ``G_r``
    (:func:`addition_signal_loading`, whitened as in :func:`inflation`). On
    an orthonormal basis ``Q_r`` of the residual space — the complement of
    the fitted columns ``[C | K]`` of the module docstring —

        t_r(σ²) = (Q_r' r_r)' (σ² I + Q_r' G_r Q_r)⁻¹ (Q_r' r_r)

    is a chi-squared variable on the ``n - p_r`` residual degrees of freedom
    in the linearised model, whatever ``G_r``; ``σ²`` is the pooled root of
    ``sum_r t_r(σ²) = sum_r (n - p_r)``, the Paule-Mandel equation of all the
    replicates together (:func:`paule_mandel`), between ``_PM_FLOOR`` of the
    smallest residual variance and the largest. Cochran's test compares the
    ``t_r``, written back in the units of a residual sum of squares as
    ``σ² t_r``.

    Parameters
    ----------
    rows : Sequence[tuple[Projection, ProjectedFit]]
        Every replicate's single-row projection and its own fit.
    additions : AdditionError
        The stated error of each addition, which every replicate carries on
        its own.
    titrant_stock : float, optional
        The titrant stock in M; ``None`` when no dilution is declared.

    Returns
    -------
    list[float] or None
        One value per replicate; ``None`` when one of them has no free Ka, no
        residual degree of freedom or no finite residual.
    """
    parts, variances = [], []
    for projection, fit in rows:
        found = _linearised(projection, fit)
        if found is None:
            return None
        residual, whiten, _, _, span, variance = found
        loading = whiten[:, np.newaxis] * addition_signal_loading(projection, fit.ka, None, additions, titrant_stock)
        added = (additions.sigma_pct / 100.0) ** 2 * (loading @ loading.T)
        parts.append((residual, residual_space(span, span.shape[1]), added))
        variances.append(variance)
    dof = sum(rest.shape[1] for _, rest, _ in parts)
    noise, forms = paule_mandel(parts, dof, max(variances), min(variances))
    return [noise * form for form in forms]


def _linearised(
    projection: Projection, fit: ProjectedFit
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, float] | None:
    """The linearised fit of the module docstring at *fit*: what every factor and the scatter of a replicate rest on.

    The whitened residual, the whitening, the estimator ``M`` and the model
    covariance ``(Q'Q)⁻¹`` of the free Ka in the units of the decades of their
    columns as normalised here, an orthonormal basis of the span of the fitted
    columns ``[C | K]``, and ``σ̂² = S / (n - p)``. ``None`` when no Ka is
    free, and when the fit leaves no residual degree of freedom or no finite
    residual.
    """
    if not projection.free_ka:
        return None
    if projection.signals.shape[0] != 1:
        raise ValueError(
            f'The inflation describes one signal; this projection holds {projection.signals.shape[0]} rows.'
        )
    coefficients = fit.coefficients[0]
    design = projection._design(fit.ka)
    whiten = projection._whiten
    residual = (projection.signals[0] - design @ coefficients) * whiten
    ka_columns = []
    for key in projection.free_ka:
        up, down = dict(fit.ka), dict(fit.ka)
        up[key] *= 10.0**_LOG_KA_STEP
        down[key] /= 10.0**_LOG_KA_STEP
        change = (projection._design(up) - projection._design(down)) @ coefficients
        ka_columns.append(whiten * change / (2.0 * _LOG_KA_STEP))
    ka_columns = np.column_stack(ka_columns)
    if not (np.isfinite(ka_columns).all() and np.isfinite(residual).all()):
        return None

    basis = _basis(projection.fitted_parameters(fit.ka).columns)
    partialled = ka_columns - basis @ (basis.T @ ka_columns)
    norms = np.linalg.norm(partialled, axis=0)
    partialled = partialled / np.where(norms > 0, norms, 1.0)
    model = np.linalg.pinv(partialled.T @ partialled, hermitian=True)
    estimator = model @ partialled.T
    span = _basis(np.hstack([basis, partialled]))
    n, p = residual.size, span.shape[1]
    if n <= p:
        return None
    variance = projection._floored(fit) / (n - p)
    if not variance > 0:
        return None
    return residual, whiten, estimator, model, span, variance


def _factors(
    projection: Projection,
    fit: ProjectedFit,
    law: NoiseLaw | None,
    curve: np.ndarray | None,
    additions: AdditionError | None,
    n_replicates: int,
    titrant_stock: float | None,
) -> tuple[list[np.ndarray], np.ndarray] | None:
    """The sandwich covariance of the free Ka at every accepted share, and the covariance the profile assumes.

    Both in units of the decades of the columns as normalised here, which
    cancel in every ratio of the two. ``None`` when nothing applies, and
    wherever :func:`_linearised` is.
    """
    shares = _shares(law)
    if shares is None and additions is None:
        return None
    found = _linearised(projection, fit)
    if found is None:
        return None
    residual, whiten, estimator, model, span, variance = found
    n, p = residual.size, span.shape[1]
    unexplained = 1.0 - np.sum(span**2, axis=1)

    added = np.zeros((n, n))
    beside = variance
    if additions is not None:
        divisor = n_replicates if additions.separate_titrations else 1
        loading = whiten[:, np.newaxis] * addition_signal_loading(projection, fit.ka, None, additions, titrant_stock)
        added = (additions.sigma_pct / 100.0) ** 2 / divisor * (loading @ loading.T)
        beside, _ = paule_mandel([(residual, residual_space(span, p), added)], n - p, variance)

    signal = projection.signals[0] if curve is None else np.asarray(curve, dtype=float)
    sandwich = []
    for share in shares if shares is not None else [None]:
        if share is None:
            shape = np.ones(n)
        else:
            shape = law.relative_variance(signal, share) / law.relative_variance(signal)
            shape = shape * (n - p) / float(unexplained @ shape)
        omega = np.diag(beside * shape) + added
        sandwich.append(estimator @ omega @ estimator.T)
    return sandwich, variance * model


def _shares(law: NoiseLaw | None) -> np.ndarray | None:
    """The shares the replicates accept, ``None`` when no law of positive share was read."""
    if law is None or not law.estimated or not law.share > 0:
        return None
    low, high = law.share_set
    inside = np.arange(np.ceil(low / _SHARE_STEP), np.floor(high / _SHARE_STEP) + 1) * _SHARE_STEP
    return np.unique(np.concatenate([[low, law.share, high], inside[(inside > low) & (inside < high)]]))


def _basis(columns: np.ndarray) -> np.ndarray:
    """An orthonormal basis of the span of *columns*, rank read at ``_RANK_RTOL``."""
    if columns.shape[1] == 0:
        return np.zeros((columns.shape[0], 0))
    u, s, _ = np.linalg.svd(columns, full_matrices=False)
    return u[:, : int(np.sum(s > s[0] * _RANK_RTOL))] if s[0] > 0 else np.zeros((columns.shape[0], 0))


def residual_space(columns: np.ndarray, rank: int) -> np.ndarray:
    """An orthonormal basis of the complement of the *rank* leading left singular directions of *columns*.

    For the columns a fit counts, the residual space: the directions of the
    signal no fitted parameter follows, ``n - rank`` of them.
    """
    return np.linalg.svd(columns, full_matrices=True)[0][:, rank:]


def paule_mandel(
    parts: Sequence[tuple[np.ndarray, np.ndarray, np.ndarray]], dof: int, largest: float, smallest: float | None = None
) -> tuple[float, list[float]]:
    """The noise variance ``σ²`` beside a known covariance, read on the residual space, and each part's form at it.

    Each part is a residual ``r`` — or several residuals of one covariance,
    rows of a ``(k, n)`` array — an orthonormal basis ``Q`` of its residual
    space (:func:`residual_space`) and the covariance ``G`` a known error adds
    to the residual, ``(n, n)``. With

        t(σ²) = (Q'r)' (σ² I + Q'G Q)⁻¹ (Q'r),

    summed over the rows of a part, ``σ²`` is the root of
    ``sum over parts t(σ²) = dof`` (Paule & Mandel 1982, J. Res. NBS 87:377).
    In the linearised model ``Q'r`` is ``Q'`` of the noise and of the known
    error alone, whatever the fit did, so each ``t`` is chi-squared on its
    residual degrees of freedom at the true ``σ²``. The root has to be read on
    that space: an error of the titrant additions moves the curve much as a
    Ka would, the fit follows most of it, and the remainder lies along
    ``(I - P) H``, which ``G`` taken whole hardly weighs down, so that on the
    whole residual the remainder counts as noise and the root comes out at
    1.3 to 3 times the noise (median) where the additions dominate it.

    The root is truncated to ``[_PM_FLOOR · smallest, largest]``, the residual
    variances with no ``G`` (*smallest* is *largest* when omitted): the
    numerical zero below, and above the variance the residual shows with no
    known error, which is the root where ``G`` is zero.

    Returns
    -------
    tuple[float, list[float]]
        ``σ²`` and ``t(σ²)`` of every part.
    """
    reduced = []
    for residual, rest, added in parts:
        values, vectors = np.linalg.eigh(rest.T @ added @ rest)
        projected = (vectors.T @ (rest.T @ np.asarray(residual).T)) ** 2
        if projected.ndim == 2:
            projected = projected.sum(axis=1)
        reduced.append((projected, np.maximum(values, 0.0)))

    def forms(noise: float) -> list[float]:
        return [float(np.sum(projected / (noise + values))) for projected, values in reduced]

    def excess(log_variance: float) -> float:
        return sum(forms(np.exp(log_variance))) - dof

    smallest = largest if smallest is None else smallest
    high = np.log(largest)
    low = np.log(smallest) + np.log(_PM_FLOOR)
    if excess(high) >= 0:
        noise = largest
    elif excess(low) <= 0:
        noise = smallest * _PM_FLOOR
    else:
        noise = float(np.exp(brentq(excess, low, high, xtol=1e-12)))
    return noise, forms(noise)

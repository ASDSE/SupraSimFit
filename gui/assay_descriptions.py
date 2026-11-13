"""Scientist-facing descriptions of each supported assay type.

Each entry maps an ``AssayType.name`` (enum member name) to a
``(title, html_body)`` tuple. The HTML body is rendered by
:class:`gui.widgets.info_button.InfoButton` inside a QDialog.

Content is targeted at a practising scientist, not a mathematician:
physics first, the model second, then practical tuning guidance.
"""

from __future__ import annotations

_GDA_HTML = """
<h3>Guest Displacement Assay (GDA)</h3>

<p><b>What the Experiment Does</b></p>
<p>Dye is titrated into a pre-equilibrated mixture of host and a competing
guest. The added dye competes with the guest for the host, so the observed
fluorescence (or absorbance) signal follows how much of it binds. By fitting
that curve you can extract the host&ndash;guest association constant
<i>K<sub>a,guest</sub></i>, provided the host&ndash;dye association constant
<i>K<sub>a,dye</sub></i> is known from a separate direct binding
experiment.</p>

<p><b>The Model</b></p>
<p>At each point the free concentrations of host <i>[H]</i>, dye <i>[D]</i>,
and guest <i>[G]</i> are obtained by solving the coupled mass-balance /
equilibrium equations:</p>
<p align="center">
  H + D &#x21CC; HD &nbsp;&nbsp;(K<sub>a,dye</sub> known)<br>
  H + G &#x21CC; HG &nbsp;&nbsp;(K<sub>a,guest</sub> fitted)
</p>
<p>with total conservation
<i>[H]<sub>0</sub> = [H] + [HD] + [HG]</i>,
<i>[D]<sub>0</sub> = [D] + [HD]</i>,
<i>[G]<sub>0</sub> = [G] + [HG]</i>.
The signal is the 4-parameter linear combination:</p>
<p align="center">
  <i>S = I<sub>0</sub> + I<sub>dye,free</sub> &middot; [D] +
     I<sub>dye,bound</sub> &middot; [HD]</i>
</p>

<p><b>Fitted Parameters</b></p>
<ul>
  <li><b>K<sub>a,guest</sub></b> &mdash; the quantity of interest; controls
      how much host the fixed guest holds, and so how much of the added dye
      finds a free binding site.</li>
  <li><b>I<sub>0</sub></b> &mdash; baseline offset (solvent/background).</li>
  <li><b>I<sub>dye,free</sub></b> &mdash; brightness coefficient of free dye.</li>
  <li><b>I<sub>dye,bound</sub></b> &mdash; brightness coefficient of the
      host&ndash;dye complex.</li>
</ul>

<p><b>Known Conditions</b></p>
<p>[H]<sub>0</sub>, [G]<sub>0</sub>, and K<sub>a,dye</sub> must be supplied;
the dye concentrations are the titrant series read from the data file.
GDA will only give a meaningful K<sub>a,guest</sub> if these inputs are
accurate &mdash; errors in K<sub>a,dye</sub> propagate directly into the
fitted K<sub>a,guest</sub>. How well each of them, and the titrant series, is
known belongs under <b>Input uncertainty</b>: state it and the fit may move that
input within what you stated, so the reported confidence interval covers the
entry error as well as the scatter of the data.</p>

<p><b>When to Use It</b></p>
<p>Use GDA when the guest is non-chromogenic (so a direct titration is
not feasible) but a known indicator dye is available. If you can titrate
the guest directly, prefer DBA or IDA.</p>
"""

_IDA_HTML = """
<h3>Indicator Displacement Assay (IDA)</h3>

<p><b>What the Experiment Does</b></p>
<p>A pre-formed host&ndash;dye (indicator) complex is titrated with a
competing guest. Binding of the guest to the host releases the dye, which
changes the optical signal. IDA is the most common assay for quantifying
host&ndash;guest binding with an indicator whose photophysics is already
known.</p>

<p><b>The Model</b></p>
<p>The equilibria and mass balances are identical to GDA; the distinction
is conventional &mdash; IDA emphasises the &ldquo;indicator&rdquo; role of
the dye. The signal model is:</p>
<p align="center">
  <i>S = I<sub>0</sub> + I<sub>dye,free</sub> &middot; [D] +
     I<sub>dye,bound</sub> &middot; [HD]</i>
</p>
<p>Free concentrations are obtained by solving the coupled host&ndash;dye
and host&ndash;guest equilibria at each guest concentration
[G]<sub>0</sub>.</p>

<p><b>Fitted Parameters</b></p>
<ul>
  <li><b>K<sub>a,guest</sub></b> &mdash; the target. Determines the midpoint
      and steepness of the displacement curve.</li>
  <li><b>I<sub>0</sub></b>, <b>I<sub>dye,free</sub></b>,
      <b>I<sub>dye,bound</sub></b> &mdash; signal coefficients. Any
      structural degeneracy with I<sub>0</sub> is fine: only
      K<sub>a,guest</sub> is the scientifically identifiable quantity.</li>
</ul>

<p><b>Known Conditions</b></p>
<p>You must know [H]<sub>0</sub>, [D]<sub>0</sub>, and K<sub>a,dye</sub>.
K<sub>a,dye</sub> is typically obtained from a prior DBA fit of the same
host&ndash;dye pair &mdash; which gives it a confidence interval of its own.
Enter that interval, and the uncertainty of the concentrations and of the
titrant series, under <b>Input uncertainty</b>: the fit may then move each input
within what you stated, and the reported interval for K<sub>a,guest</sub> covers
that freedom instead of assuming the numbers are exact.</p>

<p><b>When to Use It</b></p>
<p>IDA is the standard &ldquo;workhorse&rdquo; assay for measuring
binding constants of non-absorbing guests using a known indicator. If
your fit for K<sub>a,guest</sub> is poor, first check that the IDA
operating window is appropriate: K<sub>a,dye</sub> &middot; [H]<sub>0</sub>
should be of order 1&ndash;10 so the dye is neither fully free nor fully
bound at the start of the titration.</p>
"""

_DBA_HtoD_HTML = """
<h3>Direct Binding Assay &mdash; Host Titrated Into Dye (DBA H&rarr;D)</h3>

<p><b>What the Experiment Does</b></p>
<p>A fixed concentration of dye is held in the cuvette while host is
progressively added. The signal changes as more dye converts to the
host&ndash;dye complex. Fitting the titration curve yields the
host&ndash;dye association constant <i>K<sub>a,dye</sub></i>.</p>

<p><b>The Model (1:1 Host&ndash;Dye Binding)</b></p>
<p>At each point the free dye <i>[D]</i> and the complex <i>[HD]</i> are
obtained analytically from the quadratic arising from:</p>
<p align="center">
  H + D &#x21CC; HD, &nbsp;&nbsp;
  K<sub>a,dye</sub> = [HD] / ([H] [D])
</p>
<p>with conservation
<i>[H]<sub>0</sub> = [H] + [HD]</i> and
<i>[D]<sub>0</sub> = [D] + [HD]</i>. The signal model is the same
4-parameter linear combination used for IDA/GDA:</p>
<p align="center">
  <i>S = I<sub>0</sub> + I<sub>dye,free</sub> &middot; [D] +
     I<sub>dye,bound</sub> &middot; [HD]</i>
</p>

<p><b>Structural Degeneracy &mdash; Important</b></p>
<p>In DBA H&rarr;D, the three signal coefficients
(I<sub>0</sub>, I<sub>dye,free</sub>, I<sub>dye,bound</sub>) are not all
independently identifiable because [D]<sub>0</sub> is constant along the
titration. Only <i>K<sub>a,dye</sub></i> and the overall signal change
(saturation minus baseline) are reliably recovered. This is a property
of the experiment, not of the fitter.</p>

<p><b>Fitted Parameters</b></p>
<ul>
  <li><b>K<sub>a,dye</sub></b> &mdash; the quantity of interest. Determines
      the curvature of the titration.</li>
  <li><b>I<sub>0</sub>, I<sub>dye,free</sub>, I<sub>dye,bound</sub></b>
      &mdash; signal coefficients. Useful for reconstructing the fit curve
      but individually under-determined; do not over-interpret their
      absolute values.</li>
</ul>

<p><b>Known Conditions</b></p>
<p>The fixed dye concentration [D]<sub>0</sub> is the one condition you supply,
and the host concentrations are the titrant series. Both come from a weighing
and a dilution: state how well you know them under <b>Input uncertainty</b> and
the reported interval for K<sub>a,dye</sub> covers that error too.</p>

<p><b>When to Use It</b></p>
<p>Use this mode when it is experimentally easier to titrate the host
(e.g. a large cage molecule) into a fixed dye solution. If the dye is
the limiting reagent, DBA H&rarr;D is usually the most information-rich
geometry.</p>
"""

_DBA_DtoH_HTML = """
<h3>Direct Binding Assay &mdash; Dye Titrated Into Host (DBA D&rarr;H)</h3>

<p><b>What the Experiment Does</b></p>
<p>A fixed concentration of host is kept in the cuvette and dye is
titrated in. The signal changes as the added dye finds binding sites on
the host. Fitting yields the host&ndash;dye association constant
<i>K<sub>a,dye</sub></i>.</p>

<p><b>The Model</b></p>
<p>Same 1:1 equilibrium as the H&rarr;D mode, but with
[H]<sub>0</sub> fixed and [D]<sub>0</sub> varying. Free concentrations
are solved from the quadratic; the signal model is the same 4-parameter
linear combination.</p>
<p align="center">
  <i>S = I<sub>0</sub> + I<sub>dye,free</sub> &middot; [D] +
     I<sub>dye,bound</sub> &middot; [HD]</i>
</p>

<p><b>Signal Coefficients</b></p>
<p>Unlike DBA H&rarr;D, the dye concentration changes along the titration,
so the data can determine each signal coefficient as well as
<i>K<sub>a,dye</sub></i>. Where a design still fixes only a combination of
them, the summary marks those coefficients with *.</p>

<p><b>Known Conditions</b></p>
<p>The fixed host concentration [H]<sub>0</sub> is the one condition you supply,
and the dye concentrations are the titrant series. State how well you know them
under <b>Input uncertainty</b> and the reported interval for
K<sub>a,dye</sub> covers that error as well as the scatter of the data.</p>

<p><b>When to Use It</b></p>
<p>Use this mode when the host is the limiting / expensive reagent.
DBA D&rarr;H can also be more robust when dye solubility or background
fluorescence complicates the reversed geometry.</p>
"""

_DYE_ALONE_HTML = """
<h3>Dye Alone &mdash; Linear Calibration</h3>

<p><b>What the Experiment Does</b></p>
<p>A dilution series of dye (no host, no guest) is measured. The result
is a calibration line relating dye concentration to measured signal. The
fit parameters characterise the instrument response of the free dye.</p>

<p><b>The Model</b></p>
<p align="center">
  <i>S = slope &middot; [D] + intercept</i>
</p>

<p><b>Fitted Parameters</b></p>
<ul>
  <li><b>slope</b> &mdash; molar response of the instrument to free dye.
      Provides <i>I<sub>dye,free</sub></i> for subsequent DBA/IDA fits.</li>
  <li><b>intercept</b> &mdash; background at zero dye (solvent,
      autofluorescence, offset).</li>
</ul>

<p><b>When to Use It</b></p>
<p>Run this as a control before each IDA / DBA session to fix the
instrument baseline and confirm the dye is still behaving linearly in
the concentration range used. A non-linear calibration usually signals
aggregation, inner-filter effects, or detector saturation.</p>

<p><b>See Also &mdash; Dye-Alone Priors</b></p>
<p>The fit produced by this assay is reused downstream by the
<i>Parameter Bounds</i> panel: tick <b>Use dye-alone priors for signal
bounds</b> and load your calibration file to clamp I<sub>0</sub> and
I<sub>dye,free</sub> during subsequent IDA/DBA/GDA fits. Where the dye is
held fixed (IDA, DBA host-to-dye) this breaks the structural degeneracy in
the signal coefficients, and in any of these assays it can narrow the
K<sub>a</sub> interval.</p>
"""

_DBA_HG2_HTML = """
<h3>Stepwise 1:2 Host&ndash;Guest Binding (HG2)</h3>

<p><b>What the Experiment Does</b></p>
<p>Guest is titrated into a fixed concentration of host that can bind
<i>two</i> guests in succession. The observed signal changes as the HG and
HG<sub>2</sub> complexes accumulate.</p>

<p><b>The Model</b></p>
<p align="center">
  H + G &#x21CC; HG &nbsp;&nbsp;(K<sub>a(HG)</sub>)<br>
  HG + G &#x21CC; HG<sub>2</sub> &nbsp;&nbsp;(K<sub>a(HG&#x2082;)</sub>)
</p>
<p>with conservation
<i>[H]<sub>0</sub> = [H] + [HG] + [HG<sub>2</sub>]</i> and
<i>[G]<sub>0</sub> = [G] + [HG] + 2[HG<sub>2</sub>]</i>
(two guests per HG<sub>2</sub>). Free guest is solved at each point and the
signal is a per-species sum:</p>
<p align="center">
  <i>S = I<sub>0</sub> + I<sub>G</sub>[G] + I<sub>H</sub>[H] +
     I<sub>HG</sub>[HG] + I<sub>HG&#x2082;</sub>[HG<sub>2</sub>]</i>
</p>

<p><b>Fitted Parameters</b></p>
<ul>
  <li><b>K<sub>a(HG)</sub>, K<sub>a(HG&#x2082;)</sub></b> &mdash; the stepwise
      association constants.</li>
  <li><b>I<sub>0</sub>, I<sub>G</sub>, I<sub>HG</sub>,
      I<sub>HG&#x2082;</sub></b> &mdash; baseline and per-species signal
      coefficients.</li>
  <li><b>I<sub>H</sub></b> &mdash; free-host signal, pinned to zero by
      default.</li>
</ul>

<p><b>Identifiability</b></p>
<p>The two stepwise constants are commonly <b>not independently
determinable</b> from a single titration: a whole range of pairs describes the
data equally well. The <i>Identifiability</i> tab reports what the data do fix
&mdash; a 95&thinsp;% confidence interval for each constant, and the joint
region of the pair. The region is not the rectangle the two intervals span: it
stretches along the direction in which one constant compensates the other, and
rejects pairs that each interval on its own allows. Judge a reported
<i>pair</i> of constants against the region. Each single interval covers the
uncertainty you state for the entered inputs; the region of the pair holds them
at the values you entered.</p>

<p><b>Known Conditions</b></p>
<p>Only the fixed total host <i>[H]<sub>0</sub></i> is required. State how well
you know it, and the guest concentrations of the titrant series, under
<b>Input uncertainty</b> to have the reported intervals cover that error.</p>
"""

_DBA_H2G_HTML = """
<h3>Stepwise 2:1 Host&ndash;Guest Binding (H2G)</h3>

<p><b>What the Experiment Does</b></p>
<p>Guest is titrated into a fixed concentration of host where <i>two</i>
hosts can bind a single guest in succession. The observed signal changes as
the HG and H<sub>2</sub>G complexes accumulate. This is the 2:1 mirror of the
1:2 (HG2) model and uses the same solver.</p>

<p><b>The Model</b></p>
<p align="center">
  H + G &#x21CC; HG &nbsp;&nbsp;(K<sub>a(HG)</sub>)<br>
  HG + H &#x21CC; H<sub>2</sub>G &nbsp;&nbsp;(K<sub>a(H&#x2082;G)</sub>)
</p>
<p>with conservation
<i>[H]<sub>0</sub> = [H] + [HG] + 2[H<sub>2</sub>G]</i>
(two hosts per H<sub>2</sub>G) and
<i>[G]<sub>0</sub> = [G] + [HG] + [H<sub>2</sub>G]</i>.
Free host is solved at each point and the signal is a per-species sum:</p>
<p align="center">
  <i>S = I<sub>0</sub> + I<sub>G</sub>[G] + I<sub>H</sub>[H] +
     I<sub>HG</sub>[HG] + I<sub>H&#x2082;G</sub>[H<sub>2</sub>G]</i>
</p>

<p><b>Fitted Parameters</b></p>
<ul>
  <li><b>K<sub>a(HG)</sub>, K<sub>a(H&#x2082;G)</sub></b> &mdash; the stepwise
      association constants.</li>
  <li><b>I<sub>0</sub>, I<sub>G</sub>, I<sub>HG</sub>,
      I<sub>H&#x2082;G</sub></b> &mdash; baseline and per-species signal
      coefficients.</li>
  <li><b>I<sub>H</sub></b> &mdash; free-host signal, pinned to zero by
      default.</li>
</ul>

<p><b>Identifiability</b></p>
<p>As with the 1:2 case, the two stepwise constants are commonly <b>not
independently determinable</b> from a single titration. The
<i>Identifiability</i> tab reports a 95&thinsp;% confidence interval for each
constant and the joint region of the pair; judge a reported pair against that
region, which is the wider statement wherever the two constants trade off. Each
single interval covers the uncertainty you state for the entered inputs; the
region of the pair holds them at the values you entered.</p>

<p><b>Known Conditions</b></p>
<p>Only the fixed total host <i>[H]<sub>0</sub></i> is required. State how well
you know it, and the guest concentrations of the titrant series, under
<b>Input uncertainty</b> to have the reported intervals cover that error.</p>
"""

ASSAY_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    'GDA': ('Guest Displacement Assay (GDA)', _GDA_HTML),
    'IDA': ('Indicator Displacement Assay (IDA)', _IDA_HTML),
    'DBA_HtoD': ('Direct Binding Assay (Host \u2192 Dye)', _DBA_HtoD_HTML),
    'DBA_DtoH': ('Direct Binding Assay (Dye \u2192 Host)', _DBA_DtoH_HTML),
    'DYE_ALONE': ('Dye Alone (Linear Calibration)', _DYE_ALONE_HTML),
    'DBA_HG2': ('Stepwise 1:2 Host\u2013Guest Binding (HG2)', _DBA_HG2_HTML),
    'DBA_H2G': ('Stepwise 2:1 Host\u2013Guest Binding (H2G)', _DBA_H2G_HTML),
}

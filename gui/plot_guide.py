"""How to read each plot tab and the summary panel: the text of Help ▸ Reading the plots.

``PLOT_GUIDE`` maps a section key to a ``(title, html_body)`` tuple, in the order
the guide lists them; the first four keys are the plot tabs.
:class:`gui.dialogs.plot_guide_dialog.PlotGuideDialog` shows one section at a
time under ``DEMO_NOTE``. Every example quotes the Demo IDA data with the app's
default settings.
"""

from __future__ import annotations

FIT_CURVE = 'fit_curve'
DISTRIBUTIONS = 'distributions'
IDENTIFIABILITY = 'identifiability'
SENSITIVITY = 'sensitivity'
SUMMARY = 'summary'

DEMO_NOTE = (
    'Examples use <b>Demo IDA</b>: 7 of its 8 replicates averaged (Outlier Removal drops A), '
    'K<sub>a,dye</sub> 16.8 MM<sup>&minus;1</sup>, [Host]<sub>0</sub> 4.3 &micro;M, '
    '[Dye]<sub>0</sub> 6 &micro;M.'
)

_FIT_CURVE_HTML = """
<p><b>What you see</b></p>
<ul>
<li>Coloured points: your replicates, named A, B, &hellip; in the legend.</li>
<li>Grey crosses: replicates the fit did not use, either <i>dropped</i> (switched off, or removed by
Outlier Removal) or <i>left out of fit</i> (a per-replicate fit found no accepted fit for it).</li>
<li>Grey bars with caps: mean &plusmn; SD of the replicates the fit used (<i>Plot Style &#9656; Visibility
&#9656; Show average</i> adds a dashed line through the means).</li>
<li>Cyan dashed curve: the reported fit.</li>
<li>Fit Summary box: <i>estimate (min, max)</i> for each value, that is the reported fit&rsquo;s
value, then the lowest and highest among the accepted fits.</li>
</ul>
<p>An <i>attempt</i> is one optimiser run from a random start (Trials); an <i>accepted fit</i> is an
attempt that reaches Min R&sup2;.</p>

<p><b>How to read it</b></p>
<p>Good: the points scatter on both sides of the curve everywhere. Worrying: a run of points on one
side; a high R&sup2; does not rule that out. The (min, max) range shows how consistently the attempts
converge, not how precisely the data fix K<sub>a</sub>: see Identifiability.</p>

<p><b>Example</b></p>
<p>K<sub>a(G)</sub> = 3.14&times;10<sup>8</sup> M<sup>&minus;1</sup>, R&sup2; 0.9941, in every run.
Over six runs the range&rsquo;s upper end went from 3.14&times;10<sup>8</sup> to
1.00&times;10<sup>9</sup>, with 40 to 61 of 100 attempts accepted. At 10 of the 12 concentrations
all 7 replicates sit on the same side of the curve: a systematic miss.</p>
"""

_DISTRIBUTIONS_HTML = """
<p><b>What you see</b></p>
<p>One panel per fitted value and one for R&sup2; (tick RMSE below to add it). <i>Show as</i> picks
box plots or histograms. K<sub>a</sub> is on a log<sub>10</sub> scale by default.</p>
<ul>
<li>Dots: the accepted fits, spread sideways; for a per-replicate fit, one coloured column per
replicate.</li>
<li>Box: the middle half of the fits; whiskers reach up to 1.5 box heights beyond it.</li>
<li>Red line: the median of all accepted fits; diamonds: each replicate&rsquo;s median.</li>
<li>Gold ring: the reported fit. Click a dot to report that fit instead.</li>
<li>Histogram: the same fits in bins, bars growing to the right, replicates pooled.</li>
</ul>

<p><b>How to read it</b></p>
<p>Good: K<sub>a</sub> in one tight cluster. That shows the optimiser converges, not that
K<sub>a</sub> is precise. Expected: I<sub>0</sub>, I<sub>D</sub> and I<sub>HD</sub> spread widely; in
IDA and DBA the data fix only a combination of them. Worrying: K<sub>a</sub> in separate clusters
with similar R&sup2;. Check Identifiability and raise Trials.</p>

<p><b>Example</b></p>
<p>In one run all 61 accepted K<sub>a(G)</sub> lie within 1&thinsp;% of 3.14&times;10<sup>8</sup>
M<sup>&minus;1</sup>, while I<sub>0</sub> spans 0 to 7.3&times;10<sup>3</sup> a.u. In other runs a
few fits stop as far out as 1.0&times;10<sup>9</sup> and sit beyond the whisker.</p>
"""

_IDENTIFIABILITY_HTML = """
<p>This tab answers: <b>how far can K<sub>a</sub> move before the fit gets measurably worse?</b></p>

<p><b>What you see</b></p>
<ul>
<li>Line above the plot: the best fit, its R&sup2;, and the 95&thinsp;% confidence interval (CI)
with how far it reaches from the best fit.</li>
<li>Black line: the best R&sup2; reachable with K<sub>a</sub> held at each value. Attempts sit on or below
it, to within rounding.</li>
<li>Dotted line: the CI cut-off. Where the black line stays above it, the fit is not significantly
worse than the best (F test); the grey band spans that K<sub>a</sub> range.</li>
<li>Dashed line: Min R&sup2;. The right-hand axis names both lines.</li>
<li>Dots: the attempts, dark grey at or above Min R&sup2;, light grey below. The bars above and to
the right count them per bin in view.</li>
<li>A per-replicate fit adds a thin grey line per replicate. Each attempt fitted one replicate, so
compare it with that replicate&rsquo;s line; the black line and the CI use their average.</li>
</ul>
<p>The R&sup2; axis is linear and opens on the peak, the cut-off and Min R&sup2; (unless it is far from
them: a note says so). Scroll to zoom, drag to pan, right-click for View All.</p>

<p><b>How to read it</b></p>
<p>Good: a clear peak and a narrow band. Worrying: a flat line over a wide K<sub>a</sub> range, or
<i>open</i> at an end of the CI: the data cannot rule out K<sub>a</sub> up to your bound, so report
a limit.</p>
<p>The CI assumes the model and the inputs you entered are right. It uses the replicates&rsquo;
average, because replicates that miss the model in the same way are not independent evidence.</p>
<p>After a sensitivity run, a translucent blue cloud shows each sample&rsquo;s best fit. A sample
can sit above the black line, as it fits with its own changed inputs; that does not make them right,
since changed inputs can absorb a systematic miss. <i>Show sensitivity samples</i> hides the cloud;
<i>Colour by</i> shades it by one input&rsquo;s change (blue lower, red higher).</p>

<p><b>Example</b></p>
<p>Best fit 3.14&times;10<sup>8</sup> M<sup>&minus;1</sup> (R&sup2; 0.9941); CI
1.8&ndash;8.8&times;10<sup>8</sup> M<sup>&minus;1</sup> (&minus;44&thinsp;% / +182&thinsp;%), cut-off
0.9908. The best R&sup2; is 0.9925 at twice the best K<sub>a</sub> and 0.9868 at half: small R&sup2;
differences set a 5-fold interval, while most accepted fits agree within 1&thinsp;%.</p>
<p>The curve misses the replicates&rsquo; mean by 5.7&times;10<sup>3</sup> a.u. (RMSE) while they
scatter by about 1.0&times;10<sup>3</sup> a.u.: they depart from the model in the same way (see Fit
Curve). With &sigma; 5&thinsp;% on each input, all 11 samples reaching R&sup2; 0.9999 have
K<sub>a</sub> 1.2&ndash;1.7&times;10<sup>8</sup> M<sup>&minus;1</sup>, below the CI.</p>
"""

_SENSITIVITY_HTML = """
<p>This tab answers: <b>how much does K<sub>a</sub> change if the inputs you entered are slightly
wrong?</b> Each sample refits your data with every input you did not fix moved at random: a &sigma;
draws from a normal distribution, a range evenly between its ends.</p>

<p><b>K<sub>a</sub> histogram</b>: every sample&rsquo;s best K<sub>a</sub>. The dashed
<i>baseline</i> is the fit with the inputs as entered. The title gives the median and how many-fold
the middle 90&thinsp;% spans.</p>

<p><b>Sobol indices</b> split the variation of log<sub>10</sub> K<sub>a</sub> among the inputs.</p>
<ul>
<li>S<sub>1</sub> (first order, blue): that input alone.</li>
<li>S<sub>T</sub> (total, orange): alone plus together with other inputs.</li>
<li>Whiskers: 95&thinsp;% confidence intervals; more samples narrow them. An arrow marks a value off
the chart; <i>n/a</i>, too few fits.</li>
</ul>
<p>S<sub>T</sub> close to S<sub>1</sub>: the input acts alone; well above: through combinations;
near 0, whisker included: for the uncertainties you set, it could be treated as exact. If two
inputs&rsquo; whiskers overlap, their order is not settled: use a larger sample size.</p>

<p><b>K<sub>a</sub> vs each input</b>: each sample&rsquo;s K<sub>a</sub> against one input&rsquo;s
change in percent. Blue dots meet Min R&sup2;; grey dots, drawn behind, fall below it. A clear slope
means K<sub>a</sub> follows that input. A panel opens on the range you set, with its ends labelled,
or on &plusmn; the farthest draw for a &sigma;.</p>

<p><b>Heatmap</b>: two inputs stepped on a grid, one fit per cell, coloured by K<sub>a</sub> change
(blue lower, red higher), K<sub>a</sub> or R&sup2;. Hover to read a cell. Ringed: below Min R&sup2;;
empty: no fit. A range axis runs from <i>from</i> to <i>to</i>, a &sigma; axis over
&plusmn;2&sigma;. Worrying: a sharp edge or a patch of rings, where the fit may jump to another
solution.</p>

<p><b>Example</b></p>
<p>&sigma; 5&thinsp;% on each input, sample size 1024, which draws two sets of 1024 (2048 samples): median
3.06&times;10<sup>8</sup> M<sup>&minus;1</sup>, middle 90&thinsp;% within 1.9-fold; 488 samples below
Min R&sup2;.</p>
<p>S<sub>1</sub> / S<sub>T</sub>: Guest 0.57 / 0.61, [Host]<sub>0</sub> 0.16 / 0.23,
[Dye]<sub>0</sub> 0.14 / 0.14, K<sub>a,dye</sub> 0.06 / 0.06, whiskers within &plusmn;0.04. For
these uncertainties the titrant causes most of the spread, so a better titrant stock would narrow
K<sub>a</sub> most.</p>
<p>+1&thinsp;% Guest lowers K<sub>a</sub> by about 3&thinsp;%; +1&thinsp;% [Host]<sub>0</sub> or
[Dye]<sub>0</sub> raises it by about 1.5&thinsp;%. The draws reached 16.5&ndash;19.2&thinsp;%, so the
panels open there.</p>
"""

_SUMMARY_HTML = """
<p>The panel under the tabs summarises the fit; on the Ka Sensitivity tab, the samples.</p>

<p><b>Fitted Parameters</b></p>
<ul>
<li><i>Representative</i>: which accepted fit is reported: Best, Median or Worst R&sup2;, the
fit&rsquo;s own choice, or a dot clicked on Distributions.</li>
<li><i>Estimate</i>: that fit&rsquo;s value.</li>
<li><i>Median &plusmn; MAD</i>, <i>Mean &plusmn; SD</i>, <i>68% Range</i> (16th to 84th percentile)
and <i>Min-Max Range</i>: across the accepted fits. The log<sub>10</sub> K<sub>a</sub> row uses each
fit&rsquo;s own log value.</li>
</ul>
<p><b>Fit Quality</b>: <i>RMSE</i> is the typical distance between curve and data, in signal units;
<i>Fits passing</i> counts the attempts reaching Min R&sup2;.</p>

<p><b>How to read it</b></p>
<p>The spread columns show how consistently the attempts converge; the CI on Identifiability shows
how precisely the data fix K<sub>a</sub>. Worrying: few fits passing, say 5 / 100. Raise Trials or
check the bounds.</p>
<p>On Ka Sensitivity the Estimate is the fit with the inputs as entered, and the other columns cover
every sample&rsquo;s best fit, including those below Min R&sup2;. Rows marked * are values the data
fix only in combination: their spread, even 0 &plusmn; 0, says nothing about precision.</p>

<p><b>Example</b></p>
<p>RMSE 5.72&times;10<sup>3</sup> a.u. on signals up to 2.9&times;10<sup>5</sup> a.u., R&sup2;
0.9941. One run: 61 / 100 passing and a K<sub>a</sub> 68% range of [3.14&times;10<sup>8</sup>,
3.14&times;10<sup>8</sup>], against a CI of 1.8&ndash;8.8&times;10<sup>8</sup> M<sup>&minus;1</sup>.
Across the 2048 sensitivity samples it is [2.49&times;10<sup>8</sup>,
3.61&times;10<sup>8</sup>].</p>
"""

PLOT_GUIDE: dict[str, tuple[str, str]] = {
    FIT_CURVE: ('Fit Curve', _FIT_CURVE_HTML),
    DISTRIBUTIONS: ('Distributions', _DISTRIBUTIONS_HTML),
    IDENTIFIABILITY: ('Identifiability', _IDENTIFIABILITY_HTML),
    SENSITIVITY: ('Ka Sensitivity', _SENSITIVITY_HTML),
    SUMMARY: ('Summary panel', _SUMMARY_HTML),
}

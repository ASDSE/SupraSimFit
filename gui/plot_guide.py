"""How to read each plot tab and the summary panel: the text of Help ▸ Reading the plots.

``PLOT_GUIDE`` maps a section key to a ``(title, html_body)`` tuple, in the order
the guide lists them; the first three keys are the plot tabs.
:class:`gui.dialogs.plot_guide_dialog.PlotGuideDialog` shows one section at a
time under ``DEMO_NOTE``. Every example quotes the Demo IDA data with the app's
default settings.
"""

from __future__ import annotations

FIT_CURVE = 'fit_curve'
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
Outlier Removal) or <i>left out of fit</i> (their own fit needed a different K<sub>a</sub> from the
one the others share).</li>
<li>Grey bars with caps: mean &plusmn; SD of the replicates the fit used (<i>Plot Style &#9656; Visibility
&#9656; Show average</i> adds a dashed line through the means).</li>
<li>Cyan dashed curve: the fit &mdash; the model evaluated at the fitted values, against the average of
the replicates it used.</li>
<li>Fit Summary box: each association constant as <i>estimate</i> followed by its 95&thinsp;%
confidence interval in square brackets, the signal parameters as their fitted values, and
R&sup2;. A value marked * is one the data fix only in combination with the others.</li>
</ul>

<p><b>How to read it</b></p>
<p>Good: the points scatter on both sides of the curve everywhere. Worrying: a run of points on one
side; a high R&sup2; does not rule that out, and it means the model is missing something the data
contain. How precisely the data pin K<sub>a</sub> down is the interval, not R&sup2; &mdash; the
Identifiability tab shows where it comes from. The fit is deterministic: the same data, conditions
and bounds always give the same numbers.</p>

<p><b>Example</b></p>
<p>K<sub>a(G)</sub> = 3.14&times;10<sup>8</sup> M<sup>&minus;1</sup> [1.8&times;10<sup>8</sup>,
8.8&times;10<sup>8</sup>], R&sup2; 0.9941. At 10 of the 12 concentrations all 7 replicates sit on the
same side of the curve: a systematic miss, which no width of interval accounts for.</p>
"""

_IDENTIFIABILITY_HTML = """
<p>This tab answers: <b>how far can K<sub>a</sub> move before the fit gets measurably worse?</b>
One panel per association constant the model has, and for a model with two of them a third panel
for the pair.</p>

<p><b>What you see</b></p>
<ul>
<li>Line above the plot: the best fit, its R&sup2;, and the 95&thinsp;% confidence interval (CI)
with how far it reaches from the best fit, followed by the number of data points and fitted
parameters the test is worked out from.</li>
<li>Black line: the best R&sup2; reachable with that K<sub>a</sub> held at each value, every other
parameter refitted. It breaks where the binding model has no solution.</li>
<li>Dotted line: the CI cut-off. Where the black line stays above it, the fit is not significantly
worse than the best (F test); the grey band spans that K<sub>a</sub> range. The right-hand axis
names the cut-off.</li>
<li>Diamond: the best fit.</li>
<li>A per-replicate fit of a model with one K<sub>a</sub> adds a thin grey line per replicate: that
replicate on its own. The black line and the CI use their average.</li>
<li>Pair panel (two association constants): log<sub>10</sub> of one against log<sub>10</sub> of the
other, with the 95&thinsp;% region for the pair filled, the best fit marked, and the two single
intervals as faint bands. The region is wider than the two bands crossed whenever the two constants
trade off against each other.</li>
</ul>
<p>The R&sup2; axis is linear and opens on the peak and the cut-off. Scroll to zoom, drag to pan,
right-click for View All.</p>

<p><b>How to read it</b></p>
<p>Good: a clear peak and a narrow band. Worrying: a flat line over a wide K<sub>a</sub> range, or
<i>open</i> at an end of the CI: the data cannot rule out K<sub>a</sub> up to the bound you set, so
report a limit rather than a value. With two association constants an end is also open where the
fit is rejected only because the other constant has reached its bound. The line above the plot says
which end is open and what would close it.</p>
<p>The CI holds if the model is right, the conditions you entered are right, the true
K<sub>a</sub> lies inside the bounds it is searched in, and the scatter is independent from point to
point and of the same size at every point. It uses the replicates&rsquo; average, because replicates
that miss the model in the same way are not independent evidence. Where the points run to one side
of the curve, as in the example below, the model is missing something the data contain &mdash; the
scatter is not independent noise &mdash; and the interval is narrower than the data warrant.</p>
<p>After a sensitivity run, a translucent blue cloud shows each sample&rsquo;s best fit. A sample
can sit above the black line, as it fits with its own changed inputs; that does not make them right,
since changed inputs can absorb a systematic miss. <i>Show sensitivity samples</i> hides the cloud;
<i>Colour by</i> shades it by one input&rsquo;s change (blue lower, red higher).</p>

<p><b>Example</b></p>
<p>Best fit 3.14&times;10<sup>8</sup> M<sup>&minus;1</sup> (R&sup2; 0.9941); CI
1.8&ndash;8.8&times;10<sup>8</sup> M<sup>&minus;1</sup> (&minus;44&thinsp;% / +182&thinsp;%), cut-off
0.9908 from 12 data points and 3 fitted parameters. The best R&sup2; is 0.9925 at twice the best
K<sub>a</sub> and 0.9868 at half: small R&sup2; differences set a 5-fold interval.</p>
<p>The curve misses the replicates&rsquo; mean by 5.7&times;10<sup>3</sup> a.u. (RMSE) while they
scatter by about 1.0&times;10<sup>3</sup> a.u.: they depart from the model in the same way (see Fit
Curve), so the true uncertainty is wider than this interval.</p>
"""

_SENSITIVITY_HTML = """
<p>This tab answers: <b>how much does K<sub>a</sub> change if the inputs you entered are slightly
wrong?</b> Each sample refits your data &mdash; one complete, deterministic fit of the average of
the replicates the baseline used &mdash; with every input you did not fix moved at random: a
&sigma; draws from a normal distribution, a range evenly between its ends.</p>
<p>Each input is drawn on its own, so the result assumes their errors are unrelated. Inputs made
from one stock, pipetted with one pipette or read against one calibration move together; for those
the spread and the shares describe a different experiment from yours. The titrant moves as one
factor over the whole series &mdash; a stock or dilution error &mdash; so scatter from
point-to-point pipetting is not part of it.</p>

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
near 0, whisker included: for the uncertainties you set, its share is too small to measure here,
which is not the same as none. S<sub>T</sub> drawn below S<sub>1</sub> &mdash; which cannot really
happen, since S<sub>T</sub> covers S<sub>1</sub> &mdash; means the input acts almost entirely on its
own: the two are equal to within sampling noise, and either can come out on top in any run, at any
sample size. Where the gap is wider than the whiskers span, take that input&rsquo;s two indices as
unreliable.</p>
<p>Whiskers that clearly stand apart settle which input matters more. Overlapping whiskers are a
conservative sign: two 95&thinsp;% intervals can overlap while the difference between the indices is
still significant, so their order may hold &mdash; a larger sample size decides it.</p>
<p>A run fits <i>sample size &times; (k + 2)</i> samples for <i>k</i> inputs that vary. The eight
independent sample sets behind the whiskers cost accuracy: index by index, an index at 1024 carries
up to about five times the error of one undivided set of the same size. What narrows a whisker is a
larger sample size: at 4096 most indices are already at or below the error one undivided set of 1024
reaches. Prefer 2048 or 4096 when a whisker is too wide to act on.</p>

<p><b>K<sub>a</sub> vs each input</b>: each sample&rsquo;s K<sub>a</sub> against one input&rsquo;s
change in percent. A clear slope means K<sub>a</sub> follows that input. A panel opens on the range
you set, with its ends labelled, or on &plusmn; the farthest draw for a &sigma;.</p>

<p><b>Heatmap</b>: two inputs stepped on a grid, one fit per cell, coloured by K<sub>a</sub> change
(blue lower, red higher), K<sub>a</sub> or R&sup2;. Hover to read a cell. An empty cell is one the
binding model has no solution for. Worrying: a sharp edge, where K<sub>a</sub> jumps between
neighbouring cells.</p>

<p><b>Example</b></p>
<p>&sigma; 5&thinsp;% on each of the four inputs, sample size 1024, which fits 6144 samples: median
3.08&times;10<sup>8</sup> M<sup>&minus;1</sup> against a baseline of 3.14&times;10<sup>8</sup>,
middle 90&thinsp;% within 1.9-fold. Every sample produced a fit. The draws are fresh each run unless
you tick <i>Fixed seed</i>, so a repeat run lands near these numbers rather than on them.</p>
<p>S<sub>1</sub> / S<sub>T</sub>: Guest 0.58 / 0.62, [Host]<sub>0</sub> 0.18 / 0.23,
[Dye]<sub>0</sub> 0.13 / 0.14, K<sub>a,dye</sub> 0.06 / 0.06, whiskers within &plusmn;0.04. For
these uncertainties the titrant causes most of the spread, so a better titrant stock would narrow
K<sub>a</sub> most.</p>
<p>+1&thinsp;% Guest lowers K<sub>a</sub> by about 2.9&thinsp;%; +1&thinsp;% [Host]<sub>0</sub>
raises it by about 1.5&thinsp;%, [Dye]<sub>0</sub> by 1.4&thinsp;% and K<sub>a,dye</sub> by
1.0&thinsp;%. The draws reached &plusmn;16&ndash;21&thinsp;%, so the panels open there.</p>
"""

_SUMMARY_HTML = """
<p>The panel under the tabs summarises the fit; on the Ka Sensitivity tab, the samples.</p>

<p><b>Fitted Parameters</b></p>
<ul>
<li><i>Estimate</i>: the least-squares fit &mdash; for several replicates, the fit of the average of
the replicates that were used.</li>
<li><i>95&thinsp;% interval</i>: for each association constant, the values that still describe your
data (the Identifiability tab draws where it comes from). An open side is written in words, and a
K<sub>a</sub> you held fixed reads <i>fixed</i>.</li>
<li><i>Replicates: median</i> and <i>Replicates: min - max</i>: across the replicates&rsquo; own
fits, when each replicate was fitted separately and at least two entered the fit. That is how far
your replicates disagree, which is a different question from the interval.</li>
<li>The log<sub>10</sub>(K<sub>a</sub>) row is the row above read on a log scale, estimate and
interval alike.</li>
<li>Rows marked * are values the data fix only in combination: each is one member of a family that
draws the same curve, not a measurement of that one coefficient.</li>
</ul>
<p><b>Replicates</b> (per-replicate fits): one line per replicate you gave the fit &mdash; its own
K<sub>a</sub>, its own R&sup2;, its p-value in the shared-K<sub>a</sub> test, and whether it entered
the average or was left out. The test can only notice a replicate whose own data pin K<sub>a</sub>
down: where the replicates&rsquo; own K<sub>a</sub> values already spread over decades, a replicate
that disagrees will not stand out, and the min&ndash;max column is what tells you so.</p>
<p><b>Fit Quality</b>: <i>RMSE</i> is the typical distance between curve and data, in signal units;
<i>R&sup2;</i> the fraction of the data&rsquo;s variance the fit explains; <i>Replicates used</i>
how many of the replicates you switched on entered the fit.</p>

<p><b>How to read it</b></p>
<p>The interval says how precisely these data fix K<sub>a</sub>; the replicate columns say how
reproducible your replicates are; the Ka Sensitivity tab says how much the inputs you entered move
it. They answer three different questions, and a narrow one does not make the others narrow.</p>
<p>On Ka Sensitivity the Estimate is the fit with the inputs as entered, and the other columns cover
every sample&rsquo;s best fit. Rows marked * are values the data fix only in combination: their
spread, even 0 &plusmn; 0, says nothing about precision.</p>

<p><b>Example</b></p>
<p>RMSE 5.72&times;10<sup>3</sup> a.u. on signals up to 2.9&times;10<sup>5</sup> a.u., R&sup2;
0.9941, 7 of 7 replicates used; K<sub>a(G)</sub> = 3.14&times;10<sup>8</sup> M<sup>&minus;1</sup>
[1.8&times;10<sup>8</sup>, 8.8&times;10<sup>8</sup>].</p>
"""

PLOT_GUIDE: dict[str, tuple[str, str]] = {
    FIT_CURVE: ('Fit Curve', _FIT_CURVE_HTML),
    IDENTIFIABILITY: ('Identifiability', _IDENTIFIABILITY_HTML),
    SENSITIVITY: ('Ka Sensitivity', _SENSITIVITY_HTML),
    SUMMARY: ('Summary panel', _SUMMARY_HTML),
}

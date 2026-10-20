"""How to read each plot tab and the summary panel: the text of Help ▸ Reading the plots.

``PLOT_GUIDE`` maps a section key to a ``(title, html_body)`` tuple, in the order
the guide lists them; the first three keys are the plot tabs.
:class:`gui.dialogs.plot_guide_dialog.PlotGuideDialog` shows one section at a
time under ``DEMO_NOTE``. Every example quotes the Demo IDA data. Its numbers are
the fit at the inputs as entered, which the summary's *Conditional* column shows,
unless the example says it quotes the headline fit with the uncertainties Demo IDA
states.
"""

from __future__ import annotations

FIT_CURVE = 'fit_curve'
IDENTIFIABILITY = 'identifiability'
SENSITIVITY = 'sensitivity'
SUMMARY = 'summary'

DEMO_NOTE = (
    'Examples use <b>Demo IDA</b>: 7 of its 8 replicates averaged (Outlier Removal drops A), '
    'K<sub>a,dye</sub> 16.8 MM<sup>&minus;1</sup>, [Host]<sub>0</sub> 4.3 &micro;M, '
    '[Dye]<sub>0</sub> 6 &micro;M, with the input uncertainties Demo IDA states: &sigma; 10&thinsp;% on '
    'K<sub>a,dye</sub> and &sigma; 3&thinsp;% on [Host]<sub>0</sub>, [Dye]<sub>0</sub> and the titrant. '
    'Unless an example says otherwise, its numbers are the fit at the inputs as entered: the '
    '<i>Conditional on entered inputs</i> column and the black curve on the Identifiability tab, and every '
    'view once each row of Input Uncertainty is set to <i>fixed</i>.'
)

_FIT_CURVE_HTML = """
<p><b>What you see</b></p>
<ul>
<li>Coloured points: your replicates, named A, B, &hellip; in the legend.</li>
<li>Grey crosses: replicates the fit did not use, either <i>dropped</i> (switched off, or removed by
Outlier Removal) or <i>left out of fit</i> (with each replicate fitted separately, the test of the
replicates found that its own K<sub>a</sub> differs from the one the others share, or that it scatters
far more than the others).</li>
<li>Grey bars with caps: mean &plusmn; SD of the replicates the fit used (<i>Plot Style &#9656; Visibility
&#9656; Show average</i> adds a dashed line through the means).</li>
<li>Cyan dashed curve: the fit &mdash; the model evaluated at the fitted values, against the average of
the replicates it used. Where the fit moved an input, the curve is drawn at the moved inputs.</li>
<li>Fit Summary box: each association constant as <i>estimate</i>, then <i>95&thinsp;% CI</i> and its
confidence interval in square brackets, the signal parameters as their fitted values, and
R&sup2;. Where the fit moved an input, <i>Curve drawn at the fitted input shifts</i> follows. A saved figure carries both. The verdict, the marks on parameters and
intervals, and the fit at the entered inputs are in the summary table.</li>
</ul>

<p><b>The interval and the inputs</b></p>
<p>The interval is the range of K<sub>a</sub> your data do not reject. What it covers depends on
what you state under <i>Input Uncertainty</i> in the sidebar &mdash; how well you know the titrant
concentrations, <i>[Host]<sub>0</sub></i>, <i>[Dye]<sub>0</sub></i>, <i>K<sub>a,dye</sub></i>:</p>
<ul>
<li>Every input <i>fixed</i> (how the panel opens): the interval takes those numbers as exact. It
is the interval <i>conditional on the entered inputs</i>.</li>
<li>An uncertainty stated for an input: the fit may move that input inside it, and the interval
covers that freedom as well. It is usually wider &mdash; and can be narrower when moving an input
explains a miss the entered values could not. The summary shows the conditional interval beside it
so you can see what the inputs cost.</li>
</ul>
<p>The coloured line above the summary table gives the verdict in a few words; under the table,
<i>Model and inputs</i> says what the fit found: whether the curve misses the data by more than their
own scatter allows, and whether the inputs had to move further from your entered values than you
said they could. The two tests share one 5&thinsp;% level between them instead of taking 5&thinsp;%
each (Holm&rsquo;s procedure); how often the verdict then blames a correct model or correct inputs is
measured by the validation check <i>verdict-false-alarm</i>. Where no test finds anything, the report
says so and nothing more: that is no proof the model or the inputs are right. A test that could not
run &mdash; data with no scatter above rounding, too few points beyond the fitted parameters, or no
input stated with a &sigma; the data can check &mdash; is named with the reason. The wording says what
to check next. A conflict is a statement about the inputs <i>together</i> &mdash; the shift printed
against each one says where the fit put the correction, not which stock is off, because several
inputs move the curve almost alike.</p>

<p><b>How to read it</b></p>
<p>Good: the points scatter on both sides of the curve everywhere. Worrying: a run of points on one
side; a high R&sup2; does not rule that out, and it means the model is missing something the data
contain. How precisely the data pin K<sub>a</sub> down is the interval, not R&sup2; &mdash; the
Identifiability tab shows where it comes from. The fit is deterministic: the same data, conditions,
bounds and input uncertainties always give the same numbers.</p>

<p><b>Example</b></p>
<p>With every input as entered: K<sub>a(G)</sub> = 2.81&times;10<sup>8</sup> M<sup>&minus;1</sup>
[1.52&times;10<sup>8</sup>, 4.50&times;10<sup>8</sup>] &dagger;, R&sup2; 0.9906. At 11 of the 12 concentrations
all 7 replicates sit on the same side of the curve: a systematic miss, which no width of interval
accounts for. &dagger; marks an interval whose accepted K<sub>a</sub> come in separate stretches; the
Identifiability tab shows them.</p>
<p>The headline, with the uncertainties Demo IDA states: K<sub>a(G)</sub> = 1.59&times;10<sup>8</sup>
M<sup>&minus;1</sup> [1.14&times;10<sup>8</sup>, 2.08&times;10<sup>8</sup>], R&sup2; 0.999984, under the red
line <i>The inputs together are further from their entered values than you stated</i>. Moving the
inputs removes the miss, but only by moving them further than those uncertainties allow: check the
stocks and the stated uncertainties before trusting either number.</p>
"""

_IDENTIFIABILITY_HTML = """
<p>This tab answers: <b>how far can K<sub>a</sub> move before the fit gets measurably worse?</b>
One panel per association constant the model has, and for a model with two of them a third panel
for the pair.</p>

<p><b>What you see</b></p>
<ul>
<li>Lines above the plot: the best fit, its R&sup2;, and the 95&thinsp;% confidence interval (CI)
with how far it reaches from the best fit; where you stated an uncertainty for an input, the same
reading conditional on the entered inputs follows it. A grey line gives the number of data points
and fitted parameters the test is worked out from, and the last lines give the verdict.</li>
<li>Black line: the best R&sup2; reachable with that K<sub>a</sub> held at each value, every other
parameter refitted. It breaks where the binding model has no solution. With replicates the axis,
and every number read off it, is the <i>weighted</i> R&sup2;, and the tab says so: weighted R&sup2;
counts each titration point by how precise the replicates show it to be, while the R&sup2; under
Fit Quality counts every point equally. Both describe the same fit and they differ.</li>
<li>Dotted line: the CI cut-off. Where the black line stays above it, the fit is not significantly
worse than the best (F test); the grey band spans that K<sub>a</sub> range. The line steps down
where a signal parameter reaches its bound: a fit that has to hold one there gives up that
parameter as well as K<sub>a</sub>, so the test allows it a larger drop. The right-hand axis names
the cut-off where every signal parameter is free; where the line steps down, the legend says so, and
hovering over that axis explains the step.</li>
<li>Diamond: the best fit.</li>
<li>A per-replicate fit of a model with one K<sub>a</sub> adds a thin grey line per replicate: that
replicate on its own. The black line and the CI use their average.</li>
<li>Second curve, <i>with input uncertainties</i>: shown when you state an uncertainty for an input
under <i>Input Uncertainty</i>. At each K<sub>a</sub> the fit may also move those inputs inside what
you stated, so this curve runs at or above the black one and its band &mdash; the interval the app
reports &mdash; is usually the wider of the two. The black curve and the faint band under it are the
same profile with every input held exactly as entered. Where you state only the random error of each
addition, no input moves and there is no second curve: the cut-off of the one curve allows for
the error, and the coloured band &mdash; the interval the app reports &mdash; is drawn over the faint
band without it.</li>
<li>Pair panel (two association constants): log<sub>10</sub> of one against log<sub>10</sub> of the
other, with the 95&thinsp;% region for the pair filled, the best fit marked, and the two single
intervals as faint bands. The region is wider than the two bands crossed whenever the two constants
trade off against each other. This panel holds the inputs as entered, whatever uncertainty you state
for them; the two single intervals in the panels beside it are the ones that account for that. The
random error of each addition, where you state one, and a noise law the replicates leave uncertain
do widen the region and its two bands, and a note on the tab says by how much.</li>
</ul>
<p>The R&sup2; axis is linear and opens on the peak and the cut-off. Scroll to zoom, drag to pan,
right-click for View All.</p>

<p><b>How to read it</b></p>
<p>Good: a clear peak and a narrow band. Worrying: a flat line over a wide K<sub>a</sub> range, or an
open end of the CI, written in words &mdash; <i>no upper limit</i>, <i>no lower limit</i>, or <i>not
limited by the data</i> for both: the data cannot rule out K<sub>a</sub> up to the bound you set, so
report a limit rather than a value. With two association constants an end is also open where the
fit is rejected only because the other constant has reached its bound. A line starting
<i>Open:</i> says which end is open and what would close it.</p>
<p>The second constant of a two-step model (K<sub>a(HG₂)</sub>, K<sub>a(H₂G)</sub>) claims with a
closed lower end that the second binding step happens at all. That end is closed only where the data
reject the model without the step &mdash; the <i>one-step test</i>, at p&nbsp;&le;&nbsp;0.005 &mdash; and
the line under that constant&rsquo;s reading gives the test either way: <i>second binding step
supported</i>, with the p it was rejected at, or <i>not limited below</i>, because a model without the
second step fits nearly as well. Where the inputs were free to move, it is given at the entered inputs too,
the interval the panel of the pair is drawn at. Where the second constant is a hundred times or more
below the first, a closed interval of it misses the true value more often than 1 in 20 even after
the test: read it together with the joint region of the pair.</p>
<p>The CI holds if the model is right, the true K<sub>a</sub> lies inside the bounds it is searched
in, and the scatter is independent from point to point and as large at each point as the noise law
under Fit Quality says (the same at every point for a single titration). It uses
the replicates&rsquo; average, because replicates that miss the model in the same way are not
independent evidence. It also holds the conditions you entered to be right &mdash; exactly, unless
you state an uncertainty for them, in which case the reported interval covers that uncertainty
instead. Where the points run to one side of the curve, as in the example below, the model is
missing something the data contain &mdash; the scatter is not independent noise &mdash; and the
interval is narrower than the data warrant.</p>
<p>The verdict above the plot is the one under the summary table: no test found evidence against the
model or your inputs; a shift inside your stated uncertainties explains a miss; the inputs had to go
further than you allowed; no allowed shift rescues the model; or both of the last two, the inputs
named first. A conflict is about the inputs <i>together</i>; the shift listed against each one is
where the fit put the correction, not the stock that is off.</p>
<p>After a sensitivity run, a translucent blue cloud shows each sample&rsquo;s best fit. A sample
can sit above the black line, as it fits with its own changed inputs; that does not make them right,
since changed inputs can absorb a systematic miss. <i>Show sensitivity samples</i> hides the cloud;
<i>Colour by</i> shades it by one input&rsquo;s change (blue lower, red higher).</p>

<p><b>Example</b></p>
<p>Best fit 2.81&times;10<sup>8</sup> M<sup>&minus;1</sup> (weighted R&sup2; 0.9957); CI
[1.52&times;10<sup>8</sup>, 4.50&times;10<sup>8</sup>] M<sup>&minus;1</sup> (&minus;46&thinsp;% / +60&thinsp;%), cut-off
0.9918 from 12 data points and 3 fitted parameters. The cut-off sits lower than those alone would
put it: the 7 replicates leave the share of proportional noise anywhere between 0.63 and 1, and the
interval is widened (variance &times;1.57) to hold for every share they allow. The best weighted
R&sup2; is 0.9873 at twice the best K<sub>a</sub> and 0.9859 at half: small R&sup2; differences set a
3-fold interval. Below 1.6&times;10<sup>8</sup> M<sup>&minus;1</sup> the fit holds the signal offset
on zero, so the cut-off steps down to 0.9892 there. Above the step the curve crosses the cut-off that
holds while every signal parameter is free at 1.74&times;10<sup>8</sup> M<sup>&minus;1</sup>; below the
step it clears the lower cut-off again, from the step down to 1.52&times;10<sup>8</sup> M<sup>&minus;1</sup>.
The interval spans both stretches, and the K<sub>a</sub> between them are rejected.</p>
<p>The curve misses the replicates&rsquo; mean by 7.2&times;10<sup>3</sup> a.u. (RMSE) while they
scatter by about 1.0&times;10<sup>3</sup> a.u.: they depart from the model in the same way (see Fit
Curve), so the true uncertainty is wider than this interval.</p>
"""

_SENSITIVITY_HTML = """
<p>This tab answers: <b>how much does K<sub>a</sub> change if the inputs you entered are slightly
wrong, which error is responsible for most of it, and what would a better one buy?</b> Each sample
refits your data &mdash; one complete, deterministic fit of the average of the replicates the
baseline used &mdash; with the inputs moved by the error sources you stated: a &sigma; draws from a
normal distribution, a range evenly between its ends.</p>

<p><b>What is ranked: sources, not inputs</b></p>
<p>The sources come from <i>Input Uncertainty</i> in the sidebar, the same statement the fit&rsquo;s
own interval rests on; this panel sets only how the analysis is run. There are three kinds:</p>
<ul>
<li>an input&rsquo;s <b>own</b> uncertainty &mdash; the error that input alone has;</li>
<li>a <b>shared</b> source &mdash; one stock, one balance, one pipette behind two or more inputs,
which then move together by the same fraction. It is listed under the name you gave it and ranked as
one item, because it is one thing to act on;</li>
<li><b>Each addition (random)</b> &mdash; the scatter of the individual titrant additions. It moves
every titration point on its own, and all of those movements are reported as this one item.</li>
</ul>
<p>The sources are independent and multiply, so an input carrying both an entry of its own and a
shared source carries both errors. At least one source has to be stated, or there is no spread to
split. The dashed <i>baseline</i> is the fit with every input exactly as entered.</p>

<p>The analysis propagates the uncertainties you stated (GUM Supplement 1): every sample counts the
same, however well it fits the data. The input-aware interval on the Fit Curve tab also weighs what
the data say about the inputs, so the two can differ.</p>

<p><b>K<sub>a</sub> histogram</b>: every sample&rsquo;s best K<sub>a</sub>, each fitted with its
own drawn inputs and its own K<sub>a</sub> alone. The title gives the median and how many-fold the
middle 90&thinsp;% spans. This spread is not a confidence interval: it says how far the inputs move
K<sub>a</sub>, while the interval on the Fit Curve tab weighs that against how well the data pin
K<sub>a</sub> down at all.</p>

<p><b>Sobol indices</b> split the variation of log<sub>10</sub> K<sub>a</sub> among the sources.</p>
<ul>
<li>S<sub>1</sub> (first order, blue): that source alone.</li>
<li>S<sub>T</sub> (total, orange): alone plus together with other sources.</li>
<li>Whiskers: 95&thinsp;% confidence intervals; more samples narrow them. An arrow marks a value off
the chart; <i>n/a</i>, too few fits.</li>
</ul>
<p>S<sub>T</sub> close to S<sub>1</sub>: the source acts alone; well above: through combinations;
near 0, whisker included: for the uncertainties you set, its share is too small to measure here,
which is not the same as none. S<sub>T</sub> drawn below S<sub>1</sub> &mdash; which cannot really
happen, since S<sub>T</sub> covers S<sub>1</sub> &mdash; means the source acts almost entirely on
its own: the two are equal to within sampling noise, and either can come out on top in any run, at
any sample size. Where the gap is wider than the whiskers span, take that source&rsquo;s two indices
as unreliable.</p>
<p>Whiskers that clearly stand apart settle which source matters more. Overlapping whiskers are a
conservative sign: two 95&thinsp;% intervals can overlap while the difference between the indices is
still significant, so their order may hold &mdash; a larger sample size decides it.</p>
<p>A run fits <i>sample size &times; (g + 2)</i> samples for <i>g</i> reported sources, plus two
refits per input for the elasticities below. The eight independent sample sets behind the whiskers
cost accuracy: index by index, an index at 1024 carries up to about five times the error of one
undivided set of the same size. What narrows a whisker is a larger sample size: at 4096 most indices
are already at or below the error one undivided set of 1024 reaches. Prefer 2048 or 4096 when a
whisker is too wide to act on. A run you stop keeps the sample sets that finished, and the tab says
how many of the eight its numbers rest on.</p>

<p><b>The uncertainty budget</b></p>
<p>Under the bars, for each association constant, the same run read as absolute numbers rather than
shares. The line above the table &mdash; <i>Spread of log<sub>10</sub>(K<sub>a</sub>) from the stated
input uncertainties, 1 SD</i> &mdash; is how far the stated uncertainties move the constant: in
decades, and as the factor K<sub>a</sub> spreads by, with the 95&thinsp;% interval of the
analysis&rsquo; own sampling error. The input-aware interval on the Fit Curve tab uses the same
uncertainties but also weighs what the data say about the inputs, so the two can differ; this tab
propagates them with every draw counted the same (GUM Supplement 1).</p>
<p>The table splits that spread by source:</p>
<ul>
<li><i>Stated uncertainty</i> &mdash; what you entered, in percent of the entered value however it
was stated, so the column compares.</li>
<li><i>Elasticity</i> &mdash; how many percent K<sub>a</sub> moves per percent the source moves,
measured by refitting a small step either side. A negative value means K<sub>a</sub> moves the other
way. A shared source&rsquo;s elasticity is the sum of the elasticities of the inputs it moves, which
is where cancellation becomes visible. A source behind every concentration has elasticity &minus;1
in direct binding; in a displacement assay it is s(K<sub>a,dye</sub>) &minus; 1, so it cancels only
as far as the elasticity to K<sub>a,dye</sub> is close to 1 (strong dye binding), and if
K<sub>a,dye</sub> was itself measured with the same stock it is &minus;1 there too. The Elasticity
column shows the value for your data.</li>
<li><i>Share of variance S<sub>1</sub></i> &mdash; the first-order index: the share of the spread
this source explains on its own.</li>
<li><i>Variance</i> &mdash; that share as an absolute number, in decades&sup2;. The column and the
interactions row together make the square of the spread above. A share is relative to that one
run&rsquo;s own total, so it is the variance, not the share, that compares between two analyses.</li>
<li><i>Spread if exact</i> &mdash; what would be left if this source were known exactly. It follows
from the first-order index, which is the one that answers that question.</li>
</ul>
<p>A share and a variance are estimates, so a source too small for this run to measure can come out
slightly negative, and its interval can reach below zero. Read that as <i>not distinguishable from
none</i>: the source explains no part of the spread the analysis can separate from its own sampling
error. A larger sample size shrinks both.</p>
<p><i>Interactions</i> is what no single source explains on its own: one minus the sum of the
first-order shares. It is an estimate like the rest, so it can come out slightly negative when every
source acts on its own.</p>
<p><b>Fits that run to the edge of the K<sub>a</sub> bounds</b> are reported above the table, because
the budget below them is then about that edge rather than about your inputs. A constant gets a
reason in place of its indices, budget, what-if and elasticities when its fit at the entered inputs
ran to an edge of its bounds, when its interval at the entered inputs is open, or when its refits
do not follow the inputs smoothly (they break a scaling law every binding model obeys) &mdash; the
<i>Identifiability</i> tab is where such a fit is read. If instead a share of the samples ran there, the tab keeps the numbers
and says how many did: each of those fits sits decades from the rest and pushes the spread and the
budget up, which means the uncertainties you stated reach into a region where the data stop pinning
K<sub>a</sub> down.</p>
<p><b>What if</b> &mdash; the row under the table asks what reducing one source would buy: pick the
source, set the uncertainty you could reach (a reduction only), and the sentence gives the spread
before and after, which source would then be the largest item, and a cross-check. The spread after
is read from the samples you already have, re-weighted towards the narrower distribution, so it
rests on no assumption about how K<sub>a</sub> depends on the source; it is given with the number of
samples that effectively carry the weight, and a first-order formula follows it as the cross-check.
Where too few samples carry the weight, or you take the source as exact and leave none to re-weight,
the formula gives the spread instead and the sentence says so. No fit is run for a what-if.</p>
<p>The random error of each addition is part of the reported interval when stated under Input
Uncertainty; here it is sampled and ranked against the other sources. With <i>m</i> replicates
made as separate titrations it is drawn at &sigma;/&radic;<i>m</i>, the error of their average;
replicates stated as repeated reads of one titration share their additions, and it is drawn at
&sigma;.</p>
<p><i>Export</i> &#9656; <i>Export All&hellip;</i> writes the whole table, the spread, the
elasticity of every input and the run&rsquo;s seed as <i>Ka uncertainty budget (CSV)</i>.</p>

<p><b>K<sub>a</sub> vs each source</b>: each sample&rsquo;s K<sub>a</sub> against one source&rsquo;s
change in percent. A clear slope means K<sub>a</sub> follows that source. A panel opens on the range
you set, with its ends labelled, or on &plusmn; the farthest draw for a &sigma;. The additions have
no single offset, so they have no panel.</p>

<p><b>Heatmap</b>: two inputs stepped on a grid, one fit per cell, coloured by K<sub>a</sub> change
(blue lower, red higher), K<sub>a</sub> or R&sup2;. Hover to read a cell. An empty cell is one the
binding model has no solution for. Worrying: a sharp edge, where K<sub>a</sub> jumps between
neighbouring cells. The axes are inputs, each swept over its own stated range.</p>

<p><b>Example</b></p>
<p>The uncertainties Demo IDA states, nothing shared, sample size 1024, which costs 6152 fits: median
2.81&times;10<sup>8</sup> M<sup>&minus;1</sup> against a baseline of 2.81&times;10<sup>8</sup>, middle
90&thinsp;% within 1.8-fold, a spread of 0.077 decades (&times;/&divide; 1.19). Every sample produced a
fit. The draws are fresh each run unless you tick <i>Fixed seed</i>, so a repeat run lands near these
numbers rather than on them.</p>
<p>S<sub>1</sub> / S<sub>T</sub>: Guest (the titrant) 0.44 / 0.44, K<sub>a,dye</sub> 0.29 / 0.30,
[Host]<sub>0</sub> 0.22 / 0.22, [Dye]<sub>0</sub> 0.04 / 0.04, whiskers within &plusmn;0.03. For these
uncertainties the titrant causes most of the spread, so a better titrant stock would narrow
K<sub>a</sub> most; K<sub>a,dye</sub> comes second although K<sub>a</sub> follows it only one for one,
because its stated &sigma; is the largest.</p>
<p>+1&thinsp;% Guest lowers K<sub>a</sub> by about 4.0&thinsp;%; +1&thinsp;% [Host]<sub>0</sub>
raises it by about 2.8&thinsp;%, [Dye]<sub>0</sub> by 1.1&thinsp;% and K<sub>a,dye</sub> by
0.96&thinsp;%. The draws reached about &plusmn;33&thinsp;% for K<sub>a,dye</sub> and
&plusmn;10&ndash;13&thinsp;% for the others, so the panels open there. A source shared by the host and
the dye stock would carry the sum of the first two, 3.9; one common to all three concentrations would
carry 2.8 + 1.1 &minus; 4.0 &asymp; 0: it cancels here because the elasticity to K<sub>a,dye</sub> is
close to 1. Were K<sub>a,dye</sub> measured with that same stock, the source would move it the other
way as well and carry exactly &minus;1, as the same source does in a direct-binding assay.</p>
"""

_SUMMARY_HTML = """
<p>The panel under the tabs summarises the fit; on the Ka Sensitivity tab, the samples.</p>

<p><b>Fitted Parameters</b></p>
<ul>
<li><i>Estimate</i>: the least-squares fit &mdash; for several replicates, the fit of the average of
the replicates that were used. Where you stated an uncertainty for an input, it is the fit with that
input moved to where the data put it, within what you stated.</li>
<li><i>95&thinsp;% interval</i>: for each association constant, the values that still describe your
data (the Identifiability tab draws where it comes from). An open side is written in words, and a
K<sub>a</sub> you held fixed reads <i>fixed</i>. Where you stated an uncertainty for an input, this
interval covers it too.</li>
<li><i>Conditional on entered inputs</i>: the same interval with every input held exactly at the
value you entered and no error of the additions. The column appears when you stated an uncertainty
for at least one input or a random error of each addition, because otherwise it is the column before
it.</li>
<li><i>Single-replicate fits</i>, the line under the table: the median and range of the
replicates&rsquo; own fits, each made with the inputs as entered, when each replicate was fitted
separately and at least two entered the fit. That is how far your replicates disagree, which is a
different question from the interval, so a single replicate&rsquo;s value can fall outside it. A
replicate whose own fit ran to a bound of the K<sub>a</sub> search is counted, not summarised.</li>
<li>The coloured line above the table is the verdict in a few words. Grey: no test found evidence
against the model or the entered inputs, or a test could not run and the line says so. Amber: the
data fit once the inputs move within their uncertainties. Red: the inputs together are further from
their entered values than you stated, the curve misses the data by more than their scatter allows,
or both.</li>
<li>An estimate that ran onto a bound of the K<sub>a</sub> search reads <i>not limited below</i> (or
<i>above</i>) and the closed end of the interval, or <i>not limited by the data</i> where neither end
is closed: that bound is not a measurement.</li>
<li>The log<sub>10</sub>(K<sub>a</sub>) row is the row above read on a log scale, estimate and
interval alike.</li>
<li>Rows marked * are values the data fix only in combination: each is one member of a family that
draws the same curve, not a measurement of that one coefficient.</li>
</ul>
<p><b>Replicates</b> (per-replicate fits): one line per replicate you gave the fit &mdash; its own
K<sub>a</sub>, its own R&sup2;, its p-value in the shared-K<sub>a</sub> test, and whether it entered
the average or was left out. With three replicates or more, the test starts from the majority whose
own K<sub>a</sub> lie closest to their median and takes back every other replicate the fit of that
set does not reject; a replicate that scatters far more about its own curve than the others do is
left out as well, and the test never leaves out half of them or more. Where you stated a random error
of each addition and the replicates are separate titrations, both steps allow for each
replicate&rsquo;s own additions. The test can only notice a replicate
whose own data pin K<sub>a</sub> down: where the replicates&rsquo; own K<sub>a</sub> values already
spread over decades, a replicate that disagrees will not stand out, and the single-replicate line
under the table is what tells you so.</p>
<p><b>Fit Quality</b>: <i>RMSE</i> is the typical distance between curve and data, in signal units;
<i>R&sup2;</i> the fraction of the data&rsquo;s variance the fit explains; <i>Noise</i> how large
your scatter is and how it grows with the signal; <i>Replicates used</i> how many of the replicates
you switched on entered the fit.</p>
<p>The noise law behind that row is read from your replicates: how far each of them falls from the
curve it traces itself, written as a constant part in signal units plus a part proportional to the
signal. The fit weights the titration points by it, read at the fitted curve &mdash; a point the
replicates show to be twice as precise counts four times &mdash; which is why the Identifiability tab calls its axis
<i>weighted R&sup2;</i>: weighted R&sup2; counts each point by that precision, while the R&sup2;
here counts every point equally. One titration cannot show how the noise varies with the signal, so
it is fitted with the noise taken as constant, and the row says so. Where the noise really is
proportional to the signal, that costs precision at the low end of the curve and gives an interval
somewhat wider than replicates would have earned.</p>
<p><b>Model and inputs</b>: whether the curve misses the data by more than the replicates&rsquo; own
scatter allows (where they showed a noise law, its p-value is simulated from the fitted curve and that
law; with one signal, whether the residuals change sign as often as noise would; either way with the
random error of each addition, where you stated one),
where the fit put each input it was free to move and how far that is against what you stated, and a
sentence saying what the two together mean and what to check. The shifts say where the correction
landed, not which input is wrong: several of them move the curve almost alike.</p>

<p><b>How to read it</b></p>
<p>The interval says how precisely these data fix K<sub>a</sub>, given what you said you know about
the inputs; the single-replicate line says how reproducible your replicates are; the Ka Sensitivity tab
splits the movement of K<sub>a</sub> among the error sources you stated. They answer three different questions, and a
narrow one does not make the others narrow.</p>
<p>On Ka Sensitivity the Estimate is the fit with the inputs as entered, and the other columns cover
every sample&rsquo;s best fit. Rows marked * are values the data fix only in combination: their
spread, even 0 &plusmn; 0, says nothing about precision.</p>

<p><b>Example</b></p>
<p>With every input as entered: RMSE 7.24&times;10<sup>3</sup> a.u. on signals up to
2.9&times;10<sup>5</sup> a.u., R&sup2; 0.9906, 7 of 7 replicates used; K<sub>a(G)</sub> =
2.81&times;10<sup>8</sup> M<sup>&minus;1</sup> [1.52&times;10<sup>8</sup>, 4.50&times;10<sup>8</sup>] &dagger;.
With the uncertainties Demo IDA states, <i>Fit Quality</i> describes the headline fit instead: RMSE
300 a.u. and R&sup2; 0.999984, while the <i>Conditional on entered inputs</i> column keeps the interval
above.</p>
"""

PLOT_GUIDE: dict[str, tuple[str, str]] = {
    FIT_CURVE: ('Fit Curve', _FIT_CURVE_HTML),
    IDENTIFIABILITY: ('Identifiability', _IDENTIFIABILITY_HTML),
    SENSITIVITY: ('Ka Sensitivity', _SENSITIVITY_HTML),
    SUMMARY: ('Summary panel', _SUMMARY_HTML),
}

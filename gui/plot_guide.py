"""How to read each plot view and Fit details: the text of Help ▸ Reading the plots.

``PLOT_GUIDE`` maps a section key to a ``(title, html_body)`` tuple, in the order
the guide lists them; the first three keys are the plot tabs.
:class:`gui.dialogs.plot_guide_dialog.PlotGuideDialog` shows one section at a
time under ``DEMO_NOTE``. Every example quotes the Demo IDA data. Its numbers are
the fit at the inputs as entered, which the *Inputs as entered* row of Fit results shows,
unless the example says it quotes the headline fit with the uncertainties Demo IDA
states.
"""

from __future__ import annotations

FIT_CURVE = 'fit_curve'
CONFIDENCE = 'confidence'
SENSITIVITY = 'sensitivity'
SUMMARY = 'summary'

DEMO_NOTE = (
    'Examples use <b>Demo IDA</b>: 7 of its 8 replicates averaged (Outlier Removal drops A), '
    'K<sub>a,dye</sub> 16.8 MM<sup>&minus;1</sup>, [Host]<sub>0</sub> 4.3 &micro;M, '
    '[Dye]<sub>0</sub> 6 &micro;M, with the input uncertainties Demo IDA states: &sigma; 10&thinsp;% on '
    'K<sub>a,dye</sub> and &sigma; 3&thinsp;% on [Host]<sub>0</sub>, [Dye]<sub>0</sub> and the titrant. '
    'Unless an example says otherwise, its numbers are the fit at the inputs as entered: the '
    '<i>Inputs as entered</i> row of the interval chart in Fit results and the <i>Inputs as entered</i> '
    'reading of Ka confidence, and every view once each row of Input uncertainty is set to <i>fixed</i>.'
)

_FIT_CURVE_HTML = """
<p><b>What you see</b></p>
<ul>
<li>Points without bars: the replicates the fit used, named A, B, &hellip; in Measurements.</li>
<li>Crosses: replicates the fit did not use, either switched off (by you, or by Outlier Removal) or
<i>left out by the fit</i> (with each replicate fitted separately, the test of the replicates found
that its own K<sub>a</sub> differs from the one the others share, or that it scatters far more than
the others). The legend names which.</li>
<li>Points with bars: mean &plusmn; SD of the replicates the fit used, drawn in the colour of the
text. <i>Display</i> in Fit details, or the replicate-display tool above the plot, shows the
replicates, the mean or both.</li>
<li>Solid curve: the fit &mdash; the model evaluated at the fitted values, against the average of
the replicates it used. Where the fit moved an input, the curve is drawn at the moved inputs, and
the plot&rsquo;s heading says so.</li>
<li>Above the plot: each association constant with its 95&thinsp;% interval, and the interval chart
that sets the reading reported beside the one at the inputs as entered. <i>Fit details</i> holds the
signal parameters, R&sup2;, the tests and where the fit put the inputs. A saved figure carries each
fit&rsquo;s binding constants, intervals and R&sup2; above the plot, and says where the curve is drawn
at moved inputs.</li>
<li>Dashed curves: other fits shown with the reported one, such as the fits of an imported results
file; a note above the plot gives each one&rsquo;s numbers.</li>
</ul>
<p><i>Plot appearance</i> sets the size of the replicate and mean points, the mark and colour of the
replicate points, the colour and width of the curve, the width of the error bars, and the size of the axis text of this
plot, in Measurements and in a saved figure too. The means and their error bars keep the colour of the
text.</p>

<p><b>The interval and the inputs</b></p>
<p>The interval is the range of K<sub>a</sub> your data do not reject. What it covers depends on
what you state under <i>Input uncertainty</i> in the sidebar &mdash; how well you know the titrant
concentrations, <i>[Host]<sub>0</sub></i>, <i>[Dye]<sub>0</sub></i>, <i>K<sub>a,dye</sub></i>:</p>
<ul>
<li>Every input <i>fixed</i> (how the panel opens): the interval takes those numbers as exact. It
is the interval <i>conditional on the entered inputs</i>.</li>
<li>An uncertainty stated for an input: the fit may move that input inside it, and the interval
covers that freedom as well. It is usually wider &mdash; and can be narrower when moving an input
explains a miss the entered values could not. The interval chart shows the conditional interval
beside it so you can see what the inputs cost.</li>
</ul>
<p>A callout above the plot names a warning; <i>Diagnostics</i> in Fit details marks each test, with
its full sentence on hover, and so says what the fit found: whether the curve misses the data by more than their
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
contain. How precisely the data pin K<sub>a</sub> down is the interval, not R&sup2; &mdash; Ka
confidence shows where it comes from. The fit is deterministic: the same data, conditions,
bounds and input uncertainties always give the same numbers.</p>

<p><b>Example</b></p>
<p>With every input as entered: K<sub>a(G)</sub> = 2.81&times;10<sup>8</sup> M<sup>&minus;1</sup>
[1.52&times;10<sup>8</sup>, 4.50&times;10<sup>8</sup>] &dagger;, R&sup2; 0.9906. At 11 of the 12 concentrations
all 7 replicates sit on the same side of the curve: a systematic miss, which no width of interval
accounts for. &dagger; (<i>Split</i> on the interval chart) marks an interval whose accepted
K<sub>a</sub> come in separate stretches; Ka confidence shows them.</p>
<p>The headline, with the uncertainties Demo IDA states: K<sub>a(G)</sub> = 1.59&times;10<sup>8</sup>
M<sup>&minus;1</sup> [1.14&times;10<sup>8</sup>, 2.08&times;10<sup>8</sup>], R&sup2; 0.999984, under the callout
<i>Inputs conflict</i>: together, the inputs moved further from their entered values than you stated. Moving the
inputs removes the miss, but only by moving them further than those uncertainties allow: check the
stocks and the stated uncertainties before trusting either number.</p>
"""

_CONFIDENCE_HTML = """
<p>This view answers: <b>how far can K<sub>a</sub> move before the data reject the fit?</b> One
profile plot per association constant the model has, and for a model with two of them the joint
region of the pair below them.</p>

<p><b>What you see</b></p>
<ul>
<li>Above the plots: each association constant in its two readings side by side &mdash;
<i>Input-aware</i>, the interval the app reports, with the inputs free to move inside the
uncertainties you stated, and <i>Inputs as entered</i>, every input taken as exact &mdash; each with
its estimate, its 95&thinsp;% interval and how far each end lies from the estimate. Where every input
is entered as exact there is one reading, <i>Inputs as entered</i>. <i>Split</i> marks an interval
whose accepted K<sub>a</sub> come in separate stretches.</li>
<li>Curves: the profile of each reading &mdash; at each K<sub>a</sub>, the best fit any setting of the
other parameters reaches with K<sub>a</sub> held there &mdash; Input-aware in the accent colour,
Inputs as entered in grey. A curve breaks where the binding model has no solution.</li>
<li>Up the plot, the <b>scaled drop</b>: how far the fit at that K<sub>a</sub> falls from its best,
as a share of the drop its own 95&thinsp;% test allows there. 0 is the best fit (the diamond) and 1
is the cut-off, the one dotted line. Where a curve is at or below 1, its reading accepts that
K<sub>a</sub>. Each curve is read against its own test &mdash; the residual for Inputs as entered, the
residual with a penalty for each input&rsquo;s move for Input-aware &mdash; so both cross the line at 1
exactly where their intervals end.</li>
<li>A dotted riser: where the fit at a K<sub>a</sub> has to hold a signal parameter at its bound, it
gives up that parameter as well as K<sub>a</sub>, the test allows it a larger drop, and the curve
steps down.</li>
<li>Strip under the plot: the K<sub>a</sub> each reading accepts, one bar per stretch. The shaded
band behind the curves is the reported interval.</li>
<li>Card at the top right: point at the plot to read each curve&rsquo;s scaled drop at that
K<sub>a</sub>, and whether each reading accepts it. Without the pointer it reads the reported
estimate. The enlarge tool gives the plots the whole canvas.</li>
<li>Joint region (two association constants): log<sub>10</sub> of one against log<sub>10</sub> of the
other, the 95&thinsp;% region for the pair filled, the best fit marked, and the interval of each
constant on its own as a faint band. The region is wider than the two bands crossed whenever the two
constants trade off against each other. It holds the inputs as entered, whatever uncertainty you
state for them; a stated random error of each addition and a noise law the replicates leave uncertain
widen it, and <i>Notes</i> says by how much.</li>
</ul>
<p><i>Notes</i>, the side panel, holds the input shifts of a conflict, a split interval, the sides the
data leave open, the test of a second binding step, what the intervals rest on and what widened
them.</p>

<p><b>How to read it</b></p>
<p>Good: a curve that climbs steeply on both sides of its diamond and a short bar. Worrying: a curve
that stays under 1 to the edge of the plot, or an open end written in words &mdash; <i>no upper
limit</i>, <i>no lower limit</i>, or <i>not limited by the data</i> for both: the data cannot rule out
K<sub>a</sub> up to the bound you set, so report a limit rather than a value. With two association
constants an end is also open where the fit is rejected only because the other constant has reached
its bound. <i>Open sides</i> in Notes says which end is open and what would close it.</p>
<p>The second constant of a two-step model (K<sub>a</sub> HG₂, K<sub>a</sub> H₂G) claims with a closed
lower end that the second binding step happens at all. That end is closed only where the data reject
the model without the step &mdash; the <i>one-step test</i>, at p&nbsp;&le;&nbsp;0.005 &mdash; and
<i>Second binding step</i> in Notes gives the test either way: <i>second binding step supported</i>,
with the p it was rejected at, or <i>not limited below</i>, because a model without the second step
fits nearly as well. Where the inputs were free to move, it is given at the entered inputs too, the
footing of the joint region. Where the second constant is a hundred times or more below the first, a
closed interval of it misses the true value more often than 1 in 20 even after the test: read it
together with the joint region.</p>
<p>The interval holds if the model is right, the true K<sub>a</sub> lies inside the bounds it is
searched in, and the scatter is independent from point to point and as large at each point as the
noise law under Fit quality says (the same at every point for a single titration). It uses the
replicates&rsquo; average, because replicates that miss the model in the same way are not
independent evidence. It also holds the conditions you entered to be right &mdash; exactly, unless
you state an uncertainty for them, in which case the reported interval covers that uncertainty
instead. Where the points run to one side of the curve, as in the example below, the model is
missing something the data contain and the interval is narrower than the data warrant.</p>
<p>A conflict is about the inputs <i>together</i>; the shift listed against each one in Notes is where
the fit put the correction, not the stock that is off.</p>

<p><b>Example</b></p>
<p>Inputs as entered: best fit 2.81&times;10<sup>8</sup> M<sup>&minus;1</sup>, interval
[1.52&times;10<sup>8</sup>, 4.50&times;10<sup>8</sup>] M<sup>&minus;1</sup> (&minus;46&thinsp;% / +60&thinsp;%),
worked out from 12 data points and 3 fitted parameters. It is wider than those alone would make it:
the 7 replicates leave the share of proportional noise anywhere between 0.63 and 1, and the interval
is widened (variance &times;1.57) to hold for every share they allow. At twice the best K<sub>a</sub> the curve stands at 2.15, at half
at 1.52: both rejected. Below 1.6&times;10<sup>8</sup> M<sup>&minus;1</sup> the fit holds the signal
offset on zero, so the test allows a larger drop and the curve steps down. Above the step it meets the
line at 1 at 1.74&times;10<sup>8</sup> M<sup>&minus;1</sup>; below the step it is under 1 again, from
the step down to 1.52&times;10<sup>8</sup> M<sup>&minus;1</sup>. The interval spans both stretches, and
the K<sub>a</sub> between them are rejected: <i>Split</i>.</p>
<p>The curve misses the replicates&rsquo; mean by 7.2&times;10<sup>3</sup> a.u. (RMSE) while they
scatter by about 1.0&times;10<sup>3</sup> a.u.: they depart from the model in the same way (see Fit
results), so the true uncertainty is wider than this interval.</p>
"""

_SENSITIVITY_HTML = """
<p>This view answers: <b>how much does K<sub>a</sub> change if the inputs you entered are slightly
wrong, which error is responsible for most of it, and what would a better one buy?</b> Each sample
refits your data &mdash; one complete, deterministic fit of the average of the replicates the fit at
the inputs as entered used &mdash; with the inputs moved by the error sources you stated: a &sigma;
draws from a normal distribution, a range evenly between its ends. The sample with no offset at all
is the fit at the inputs you entered.</p>

<p><b>What is ranked: sources, not inputs</b></p>
<p>The sources come from <i>Input uncertainty</i> in the sidebar, the same statement the fit&rsquo;s
own interval rests on; <i>Analysis settings</i> sets only how the analysis is run, and lists the
sources it varies. There are three kinds:</p>
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
split.</p>

<p><b>The spread and the samples</b></p>
<p>Each binding constant opens with its <i>spread from the stated inputs</i>: one standard deviation
of log<sub>10</sub> K<sub>a</sub>, as the factor K<sub>a</sub> spreads by (&times;/&divide;) and in
decades, centred on the fit at the inputs as entered. Hover over it for the 95&thinsp;% interval of
the analysis&rsquo; own sampling error. Beside it, the histogram of every sample&rsquo;s K<sub>a</sub>,
the middle 90&thinsp;% solid. Two readings of the fit are marked on it: <i>Inputs as entered</i>, a
dashed line with its interval as a bracket, where the samples centre; and <i>Input-aware</i>, the
interval the app reports, as the accent line and band. The analysis propagates the uncertainties you
stated (GUM Supplement 1): every sample counts the same, however well it fits the data. The
input-aware interval also weighs what the data say about the inputs, so the two can differ &mdash;
the spread here is not a confidence interval. Where the fit reports an input conflict, a callout says
so: the samples centre on the inputs as entered, so they show how far the stated inputs move
K<sub>a</sub>, not where it lies.</p>
<p><i>Plot against each source &rarr;</i> opens a window of small plots, one per source: each
sample&rsquo;s K<sub>a</sub> against that source&rsquo;s draw, in percent of the entered value. A clear
trend means K<sub>a</sub> follows that source. The additions are one draw per titration point, so
they have no plot of their own.</p>

<p><b>Share of the variance, by source</b> splits the variation of log<sub>10</sub> K<sub>a</sub>
among the sources, largest first.</p>
<ul>
<li>S<sub>1</sub> (first order, the solid bar): that source alone.</li>
<li>S<sub>T</sub> (total, the outlined bar): alone plus together with other sources.</li>
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
whisker is too wide to act on. A run you stop keeps the sample sets that finished, and the view says
how many of the eight its numbers rest on. <i>Fixed seed</i> repeats a run exactly; <i>This run</i>
gives the seed every run used.</p>

<p><b>The variance budget</b></p>
<p>Under the bars, the same run read as absolute numbers rather than shares, one row per source:</p>
<ul>
<li><i>Stated</i> &mdash; what you entered, in percent of the entered value however it was stated, so
the column compares.</li>
<li><i>Elasticity</i> &mdash; how many percent K<sub>a</sub> moves per percent the source moves,
measured by refitting a small step either side. A negative value means K<sub>a</sub> moves the other
way. A shared source&rsquo;s elasticity is the sum of the elasticities of the inputs it moves, which
is where cancellation becomes visible. A source behind every concentration has elasticity &minus;1
in direct binding; in a displacement assay it is s(K<sub>a,dye</sub>) &minus; 1, so it cancels only
as far as the elasticity to K<sub>a,dye</sub> is close to 1 (strong dye binding), and if
K<sub>a,dye</sub> was itself measured with the same stock it is &minus;1 there too. The Elasticity
column shows the value for your data.</li>
<li><i>Variance</i> &mdash; the variance this source explains on its own, in decades&sup2; (the
column&rsquo;s header gives the power of ten its numbers share): its share S<sub>1</sub> as an absolute
number. A share is relative to that one run&rsquo;s own total, so it is the variance, not the share,
that compares between two analyses.</li>
<li><i>Spread if exact</i> &mdash; what would be left if this source were known exactly. It follows
from the first-order index, which is the one that answers that question.</li>
</ul>
<p>The bracket after each number is its 95&thinsp;% sampling interval. A share and a variance are
estimates, so a source too small for this run to measure can come out slightly negative, and its
interval can reach below zero. Read that as <i>not distinguishable from none</i>. A larger sample
size shrinks both. <i>Interactions</i> is what no single source explains on its own, as a variance;
it is an estimate like the rest, so it can come out slightly negative when every source acts on its
own. <i>All sources</i> is the whole variance: the rows above it and <i>Interactions</i> add up to
it, the square of the spread at the top.</p>
<p><b>Fits that run to the edge of the K<sub>a</sub> bounds</b> are counted in a callout above the
shares, because the numbers below are then about that edge rather than about your inputs. A constant
gets a callout in place of its indices, budget, what-if and elasticities when its fit at the entered
inputs ran to an edge of its bounds, when its interval at the entered inputs is open, or when its
refits do not follow the inputs smoothly (they break a scaling law every binding model obeys)
&mdash; the <i>Ka confidence</i> view is where such a fit is read. If instead a share of the samples
ran there, the view keeps the numbers and says how many did: each of those fits sits decades from the
rest and pushes the spread and the budget up, which means the uncertainties you stated reach into a
region where the data stop pinning K<sub>a</sub> down.</p>
<p><b>What if one source were known better</b> &mdash; choose a source and the uncertainty you could
reach (a reduction only), and the sentence gives the spread before and after, which source would then
be the largest item, and a cross-check. The spread after is read from the samples you already have,
re-weighted towards the narrower distribution, so it rests on no assumption about how K<sub>a</sub>
depends on the source; it is given with the number of samples that effectively carry the weight, and
a first-order formula follows it as the cross-check. Where too few samples carry the weight, or you
take the source as exact and leave none to re-weight, the formula gives the spread instead and the
line says so. No fit is run for a what-if.</p>
<p>The random error of each addition is part of the reported interval when stated under Input
uncertainty; here it is sampled and ranked against the other sources. With <i>m</i> replicates
made as separate titrations it is drawn at &sigma;/&radic;<i>m</i>, the error of their average;
replicates stated as repeated reads of one titration share their additions, and it is drawn at
&sigma;.</p>
<p><i>Export</i> &#9656; <i>Export several&hellip;</i> writes the whole budget, the elasticity of
every input and the run&rsquo;s seed as <i>Ka uncertainty budget (CSV)</i>.</p>

<p><b>Heatmap</b>: two inputs stepped on a grid (11 &times; 11, 21 &times; 21 or 31 &times; 31 cells,
one fit each), K<sub>a</sub> coloured on a perceptual scale from dark violet (low) to yellow (high),
with its colour bar. Each axis is in its input&rsquo;s unit &mdash; the titrant, a series, in percent
of the concentrations entered &mdash; and spans its range, or &plusmn;1, &plusmn;2 or &plusmn;3
&sigma; for an input stated as a &sigma;, chosen beside the axis; an axis that would reach zero
is refused before any fit. The diamond marks the inputs as entered. Point at a cell to read its
inputs, K<sub>a</sub>, its change from the entered point and R&sup2; in the card; an empty cell is one
the binding model has no solution for. Worrying: a sharp edge, where K<sub>a</sub> jumps between
neighbouring cells.</p>

<p><i>Display</i>, in the side panel, draws every K<sub>a</sub> axis on a log<sub>10</sub> or a linear
scale.</p>

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
<p><i>Fit details</i>, the side panel of Fit results, holds everything the headline above the plot
does not.</p>

<p><b>Fit quality</b>: <i>R&sup2;</i> is the fraction of the data&rsquo;s variance the fit explains;
<i>RMSE</i> the typical distance between curve and data, in signal units; <i>Replicates used</i> how
many of the replicates loaded entered the fit, with what became of the others (switched off by you or
by Outlier Removal, or left out by the fit); <i>Noise</i> how large your scatter is and how it grows
with the signal.</p>
<p>The noise law behind that stat is read from your replicates: how far each of them falls from the
curve it traces itself, written as a constant part in signal units plus a part proportional to the
signal. The fit weights the titration points by it, read at the fitted curve &mdash; a point the
replicates show to be twice as precise counts four times &mdash; and every interval is cut on that
weighted residual, while the R&sup2; here counts every point equally. One titration cannot show how the noise varies with the signal, so
it is fitted with the noise taken as constant, and the stat reads <i>Not estimated</i>. Where the noise really is
proportional to the signal, that costs precision at the low end of the curve and gives an interval
somewhat wider than replicates would have earned.</p>

<p><b>Replicates</b> (each replicate fitted separately): one row per replicate you gave the fit &mdash;
its own K<sub>a</sub>, its p-value in the shared-K<sub>a</sub> test, and <i>left out</i> under its
letter where the fit left it out; the R&sup2; of its own fit, and why it was left out, in its
tooltip. With three replicates
or more, the test starts from the majority whose own K<sub>a</sub> lie closest to their median and
takes back every other replicate the fit of that set does not reject; a replicate that scatters far
more about its own curve than the others do is left out as well, and the test never leaves out half
of them or more. Where you stated a random error of each addition and the replicates are separate
titrations, both steps allow for each replicate&rsquo;s own additions. The test can only notice a
replicate whose own data pin K<sub>a</sub> down: where the replicates&rsquo; own K<sub>a</sub> values
already spread over decades, a replicate that disagrees will not stand out, and the
<i>Single-replicate fits</i> line under the headline &mdash; the median and range of the
replicates&rsquo; own fits, each made with the inputs as entered &mdash; is what tells you so. A
replicate whose own fit ran to a bound of the K<sub>a</sub> search is counted there, not
summarised.</p>

<p><b>Diagnostics</b>: each test with its mark and p-value &mdash; whether the curve misses the data by
more than the replicates&rsquo; own scatter allows (where they showed a noise law, its p-value is
simulated from the fitted curve and that law; with one signal, whether the residuals change sign as
often as noise would; either way with the random error of each addition, where you stated one), at
the inputs as entered and, where the fit could move them, at the moved inputs, and whether the inputs
together moved further than you stated. A test that could not run reads as the reason. Hover over a
test for its full sentence: its statistic and, for the test of the inputs, where the fit put each
input it was free to move. The shifts say where the correction landed, not which input is wrong:
several of them move the curve almost alike.</p>

<p><b>Parameters</b>: every fitted value with its unit. An estimate that ran onto a bound of the
K<sub>a</sub> search reads <i>not limited below</i> (or <i>above</i>) and the closed end of the
interval, or <i>not limited by the data</i> where neither end is closed: that bound is not a
measurement. Rows marked * are values the data fix only in combination: each is one member of a
family that draws the same curve, not a measurement of that one coefficient; the footnote names the
total whose balance ties them, and hovering over a starred name says more. A note under the table
says where a signal parameter ended on a bound you entered.</p>

<p><b>Input shifts</b>: where the fit put each input it was free to move, as a bar in &sigma; against
the &plusmn;1 &sigma; band and as a percentage of the entered value. An input stated as a range has
no &sigma;, so its row says instead whether the fit left it inside its range or took it to an
edge.</p>

<p><b>Display</b>: what the titration plot shows of the replicates &mdash; the replicates and their
mean &plusmn; SD, the mean alone, or the replicates alone.</p>

<p><b>How to read it</b></p>
<p>The interval says how precisely these data fix K<sub>a</sub>, given what you said you know about
the inputs; the single-replicate line says how reproducible your replicates are; Sensitivity
splits the movement of K<sub>a</sub> among the error sources you stated. They answer three different questions, and a
narrow one does not make the others narrow.</p>

<p><b>Example</b></p>
<p>With every input as entered: RMSE 7.24&times;10<sup>3</sup> a.u. on signals up to
2.9&times;10<sup>5</sup> a.u., R&sup2; 0.9906, 7 of 8 replicates used; K<sub>a(G)</sub> =
2.81&times;10<sup>8</sup> M<sup>&minus;1</sup> [1.52&times;10<sup>8</sup>, 4.50&times;10<sup>8</sup>] &dagger;.
With the uncertainties Demo IDA states, <i>Fit quality</i> describes the headline fit instead: RMSE
300 a.u. and R&sup2; 0.999984, while the <i>Inputs as entered</i> row of the interval chart keeps the
interval above.</p>
"""

PLOT_GUIDE: dict[str, tuple[str, str]] = {
    FIT_CURVE: ('Fit results', _FIT_CURVE_HTML),
    CONFIDENCE: ('Ka confidence', _CONFIDENCE_HTML),
    SENSITIVITY: ('Sensitivity', _SENSITIVITY_HTML),
    SUMMARY: ('Fit details', _SUMMARY_HTML),
}

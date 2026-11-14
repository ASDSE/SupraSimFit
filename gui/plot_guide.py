"""The text of Help ▸ Reading the plots: what each plot shows and how to read it.

``PLOT_GUIDE`` maps the name of each view with a plot — the session's views and the
Simulation window — to its section as HTML, in the order the guide lists them.
:class:`gui.dialogs.plot_guide_dialog.PlotGuideDialog` shows one section at a time.

Every section with a plot Demo IDA fills (:meth:`gui.fitting_session.FittingSession.load_demo_ida`)
ends on an example that reads the demo's numbers, held in :data:`DEMO` as the app writes
them; ``tests/integration/test_plot_guide_demo.py`` works them out again from a demo fit.
"""

from __future__ import annotations

#: Demo IDA's numbers as the views write them: its fit, Ka profile, a Sensitivity indices run
#: at Fixed seed 0 and N = 1024, and the Simulation window as it opens.
DEMO: dict[str, str] = {
    'loaded': '8',
    'off': 'A',
    'used': '7 of 8',
    'aware': '1.59\u202f×\u202f10⁸',
    'aware_interval': '1.14 – 2.08\u202f×\u202f10⁸ M⁻¹',
    'entered': '2.81\u202f×\u202f10⁸',
    'entered_interval': '1.52 – 4.50\u202f×\u202f10⁸ M⁻¹',
    'conflict': 'Inputs conflict',
    'p_moved': 'p = 0.32',
    'p_entered': 'p ≤ 0.005',
    'gap': '1.56 – 1.74\u202f×\u202f10⁸ M⁻¹',
    'card_aware': '0.00',
    'card_entered': '1.39',
    'seed': '0',
    'n': '1024',
    'spread': '×/÷\u00a01.19',
    'decades': '1 SD · 0.077 decades',
    'centre': '2.81\u202f×\u202f10⁸ M⁻¹',
    'shares': 'Guest (titrant) 0.45, K<sub>a,dye</sub> 0.30, [Host]<sub>0</sub> 0.22, [Dye]<sub>0</sub> 0.036',
    'top': 'Guest (titrant)',
    'exact': '0.0573',
    'sim_x': 'Guest 3.00 µM',
    'sim_hg': '2.60',
    'sim_hd': '1.68',
    'sim_g': '0.400',
}

_MEASUREMENTS = """
<p>The <b>Titration</b> plot shows the raw signal of every replicate against the titrant
concentration, as loaded.</p>
<ul>
<li>Dots: the replicates the fit will use, named A, B, &hellip; in the Files table.</li>
<li>Crosses: replicates switched off, by you under <i>Replicates</i> or by <i>Outlier removal</i>.
The legend names them.</li>
<li><i>Display unit</i>, in the plot header, sets the unit of the x axis only; the concentrations
are read in the unit set under <i>Concentrations</i>.</li>
</ul>
<p>Replicates that agree lie on top of each other. One that runs apart from the rest is the one to
check, or to switch off.</p>
<p><b>Example: Demo IDA</b> (Tools &#9656; Demo IDA) loads {loaded} replicates. <i>Outlier removal</i>
switches {off} off, so {off} is drawn as crosses and the others as dots; Fit details then counts
{used} replicates used.</p>
"""

_FIT_RESULTS = """
<p>The headline gives each binding constant with its 95&thinsp;% interval: the range of
K<sub>a</sub> the data do not reject. It is <i>Input-aware</i> where you stated an uncertainty
under Input uncertainty &mdash; the fit may then move the inputs inside it, and the interval
covers that &mdash; and <i>Inputs as entered</i> where every input is fixed. The interval chart
draws both readings on one K<sub>a</sub> axis; <i>Split</i> marks an interval whose accepted
K<sub>a</sub> come in separate stretches.</p>

<p><b>Titration</b></p>
<ul>
<li>Dots: the replicates the fit used.</li>
<li>Crosses: replicates the fit did not use &mdash; switched off, or left out by the fit when each
replicate is fitted separately. The legend says which.</li>
<li>Points with bars: the mean &plusmn; SD of the replicates the fit used.</li>
<li>Solid curve: the fit. Where the fit moved the inputs, the curve is drawn at the moved inputs
and the plot header says so.</li>
<li>Dashed curves: other fits shown with the reported one, such as those of an imported results
file.</li>
</ul>
<p>Good: the points scatter on both sides of the curve everywhere. Worrying: a run of points on
one side &mdash; the model misses something the data contain, however high R&sup2; is. How
precisely the data fix K<sub>a</sub> is the interval, not R&sup2;.</p>

<p><b>Fit details</b></p>
<ul>
<li><i>Fit quality</i>: R&sup2;, RMSE, the replicates used, and the noise the replicates show
&mdash; a constant part in a.u. plus a part proportional to the signal &mdash; by which the fit
weights the points.</li>
<li><i>Replicates</i>: each replicate&rsquo;s own fit, where each is fitted separately.</li>
<li><i>Diagnostics</i>: whether the curve misses the data by more than their scatter allows, and
whether the inputs together moved further than you stated. A test that could not run gives its
reason.</li>
<li><i>Parameters</i>: every fitted value with its unit. A starred value is fixed by the data only
together with the others starred.</li>
<li><i>Input shifts</i>: where the fit put each input it could move, in &sigma; and in percent of
the entered value. A shift says where the fit put the correction, not which input is wrong:
several inputs move the curve almost alike.</li>
</ul>

<p><b>Example: Demo IDA.</b> The headline reads K<sub>a</sub> guest {aware} M⁻¹, 95&thinsp;%
interval {aware_interval}, <i>Input-aware</i>; <i>Inputs as entered</i> gives {entered}
M⁻¹, {entered_interval}, marked <i>Split</i>. The callout <i>{conflict}</i> says the inputs
together moved further than you stated. Under Diagnostics the curve fits the data with the inputs
moved ({p_moved}) and misses them at the inputs as entered ({p_entered}).</p>
"""

_KA_CONFIDENCE = """
<p>One profile plot per binding constant: how far K<sub>a</sub> can move before the data reject
the fit.</p>
<ul>
<li>Curves: <i>Input-aware</i> in the accent colour, <i>Inputs as entered</i> in grey, each
estimate a diamond.</li>
<li>Up the plot, the <b>scaled drop</b>: how far the fit at that K<sub>a</sub> falls from its
best, as a share of the drop its own 95&thinsp;% test allows. The dotted line at 1 is the
cut-off: where a curve is at or below it, that reading accepts the K<sub>a</sub>, so each curve
crosses 1 exactly where its interval ends.</li>
<li>Dotted riser: where the fit at a K<sub>a</sub> holds a signal parameter on its bound, the test
allows a larger drop and the curve steps down.</li>
<li>Shaded band: the reported interval. Strip under the plot: the K<sub>a</sub> each reading
accepts, one bar per stretch.</li>
<li>Card at the top right: each curve&rsquo;s scaled drop at the K<sub>a</sub> under the pointer,
and whether each reading accepts it; without the pointer, at the reported estimate.</li>
<li>Joint region, with two binding constants: the pairs the data accept together, the best fit
marked and each constant&rsquo;s own interval a faint band. It reaches beyond the bands where the
two constants trade off against each other.</li>
</ul>
<p>Good: a curve that climbs steeply on both sides of its diamond. Worrying: a curve that stays
under 1 to the edge of the plot &mdash; the data do not limit K<sub>a</sub> on that side, and the
reading says <i>not limited below</i> or <i>above</i>. <i>Notes</i>, the side panel, says what
the intervals rest on and what would close an open side.</p>

<p><b>Example: Demo IDA.</b> The <i>Input-aware</i> curve has its diamond at {aware} M⁻¹ and crosses 1 at
the ends of its interval, {aware_interval}. The <i>Inputs as entered</i> curve, diamond at
{entered} M⁻¹, rises above 1 again over {gap}: the gap that makes its interval <i>Split</i>. Without
the pointer the card reads {card_aware} for Input-aware and {card_entered} for Inputs as entered: at
the reported estimate one reading accepts K<sub>a</sub> and the other rejects it.</p>
"""

_SENSITIVITY = """
<p>Each sample refits your data with the inputs moved by the error sources stated under Input
uncertainty: a &sigma; drawn from a normal distribution, a range evenly between its ends. Every
sample counts the same however well it fits, so the spread shows how far the stated inputs move
K<sub>a</sub>; it is not a confidence interval.</p>

<p><b>Sensitivity indices</b></p>
<ul>
<li>Spread from the stated inputs: one standard deviation of log<sub>10</sub> K<sub>a</sub>, as a
&times;/&divide; factor and in decades, centred on the fit at the inputs as entered.</li>
<li>Histogram: every sample&rsquo;s K<sub>a</sub>, the middle 90&thinsp;% solid; the
<i>Input-aware</i> reading as the accent line and band, <i>Inputs as entered</i> as the dashed
line and bracket.</li>
<li>Share of the variance, by source: S<sub>1</sub> (solid bar) is what a source explains alone,
S<sub>T</sub> (outlined bar) alone and together with the others; the whiskers are their
95&thinsp;% intervals. S<sub>T</sub> close to S<sub>1</sub>: the source acts alone. Near 0,
whisker included: too small to measure at this sample size.</li>
<li>Variance budget, one row per source: <i>Stated</i>, what you entered, in percent;
<i>Elasticity</i>, the percent K<sub>a</sub> moves per percent the source moves;
<i>Variance</i>, what the source explains alone, in decades&sup2;; <i>Spread if exact</i>, what
would be left were the source known exactly. <i>Interactions</i> is what no source explains
alone, <i>All sources</i> the whole variance.</li>
<li>What if one source were known better: the spread before and after reducing one source, read
from the samples already drawn.</li>
<li><i>Plot against each source &rarr;</i>: each sample&rsquo;s K<sub>a</sub> against that
source&rsquo;s draw. A trend marks a source that matters.</li>
</ul>

<p><b>Heatmap</b>: two inputs stepped on a grid, one fit per cell, K<sub>a</sub> coloured from
dark violet (low) to yellow (high) with its colour bar. The diamond marks the inputs as entered;
the card reads the cell under the pointer. An empty cell is one the binding model has no solution
for. Worrying: a sharp edge, where K<sub>a</sub> jumps between neighbouring cells.</p>

<p><b>Example: Demo IDA</b>, <i>Sensitivity indices</i> with <i>Fixed seed</i> on at {seed} and
N = {n}. The spread of K<sub>a</sub> guest from the stated inputs is {spread} ({decades}) around
{centre}, the fit at the inputs as entered. S<sub>1</sub> ranks the sources {shares}. Were the
first, {top}, known exactly, <i>Spread if exact</i> says {exact} decades would be left.</p>
"""

_PLOT_APPEARANCE = """
<p>The titration plot as Fit results draws it, styled by this session&rsquo;s settings in the
side panel: the size of the replicate and mean points, the replicate mark and colour, the colour
and width of the curve, the width of the error bars and the size of the axis text. They apply
to the titration plot in Measurements and Fit results, and to a figure saved from it. The means
and their error bars keep the colour of the text.</p>
<p>Ka confidence, Sensitivity and the Simulation window take no appearance setting.</p>
"""

_SIMULATION = """
<p>The titration a binding model predicts, with the equations the fit uses.</p>
<ul>
<li><b>Titration</b>: the model as a continuous curve, the simulated replicates as dots at the
measurement points, an overlaid file as rings.</li>
<li><b>Species</b>: the concentration of each species on the same x axis, one colour per binding
partner &mdash; solid for a complex, dashed for a free species. The row above it reads each
species at the concentration under the pointer.</li>
</ul>
<p><b>Noise</b>: each simulated point gets random noise with
&sigma; = &radic;(floor&sup2; + (proportional &times; signal)&sup2;) &mdash; a constant part in
a.u. and a part that grows with the signal, the law the fit reads off measured replicates.
<i>Read from overlaid data</i> takes both parts from an overlaid file with two or more
replicates. Without noise, one noise-free replicate is simulated.</p>
<p><b>Fixed totals</b> stay constant until you choose <i>Are diluted</i>: each addition then
dilutes every total the titrant stock does not hold by the titrant concentration over the
stock, as the fit does with the same stock.</p>
<p><i>Fit in new session</i> opens the data as shown in a new session and fits it. The values you
simulated with are not passed to the fit, so it searches as it does on measured data.</p>

<p><b>Example: Demo IDA.</b> The window opens on IDA at Demo IDA&rsquo;s <i>Inputs as entered</i> fit,
K<sub>a</sub> guest {entered} M⁻¹. The species row opens at {sim_x}: HG {sim_hg}, HD
{sim_hd} and G {sim_g} µM, so most of the guest added is bound.</p>
"""

PLOT_GUIDE: dict[str, str] = {
    'Measurements': _MEASUREMENTS.format(**DEMO),
    'Fit results': _FIT_RESULTS.format(**DEMO),
    'Ka confidence': _KA_CONFIDENCE.format(**DEMO),
    'Sensitivity': _SENSITIVITY.format(**DEMO),
    'Plot appearance': _PLOT_APPEARANCE,
    'Simulation': _SIMULATION.format(**DEMO),
}

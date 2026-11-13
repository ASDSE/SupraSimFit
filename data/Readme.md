# Meta Data

**The concentrations in all data files are in Molar**

## DBA System Information (host-to-dye)
- $[D_0]$ = $151 \times 10^{-6}$ $M$
- $[H_0]$ = $840 \times 10^{-6}$ $M$

## GDA System Information
- $[H_0]$ (CB7) = $50 \times 10^{-6}$ $M$
- $[G_0]$ (nButanol):  $292 \times 10^{-6}$ $M$
- $K_{a(Dye)}$ = $33 \times 10^3$ $M^{-1}$

**Dye-Alone Measurement (for this GDA System):**
- $I_0$ = 29 a.u.
- $I_{dye, free}$ = $3.52 \times 10^6$ a.u. $M^{-1}$
- Dye type: TNS

Note: The values of $I_0$ and $I_{dye, free}$ can be entered as bounds (value ± tolerance) under Binding model (or with *Bounds from dye alone…* there), which constrains the fit to them. In a GDA the dye is titrated, so the data determine every signal coefficient beside $K_{a(Guest)}$, but only loosely: a change of $K_{a(Guest)}$ is partly taken up by the coefficients. Holding the two the dye-alone measurement provides narrows the confidence interval of the association constant. A coefficient that ends on such a bound is held there, and the summary says which.

## IDA System Information
- $K_{a(Dye)}$ = $1.68 \times 10^7$ $M^{-1}$
- $[H_0]$ = $4.3 \times 10^{-6}$ $M$
- $[D_0]$ = $6 \times 10^{-6}$ $M$
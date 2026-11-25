"""Synthetic-data generators, scoring and the result store behind the app's quoted rates.

Every coverage, false-alarm and power figure the documents and the paper state
is produced here: :mod:`validation.scenarios` names the titrations,
:mod:`validation.generate` builds one dataset per (scenario, seed),
:mod:`validation.score` fits it through the application's own pipeline,
:mod:`validation.store` keeps one row per (scenario, seed, code hash), and
:mod:`validation.tables` renders the stored rows. ``python -m validation`` runs
and renders them; ``validation/README.md`` states what each check claims.
"""

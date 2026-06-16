"""ispipeline — shared Icelandic text-correction pipeline for the Metill estate.

This package consolidates the previously-forked ``corrections/`` trees of
esbvaktin and althingi into a single, eval-gated library. Consumers pin it by
git ref (the iseval pattern) and enable only the domain layers they need:

    from ispipeline import correct_icelandic
    correct_icelandic(text, mode="full", layers=["eu_terms"])      # civic register
    correct_icelandic(text, mode="full", layers=["ministers"])     # parliamentary register

Every layer degrades gracefully when the optional ``icelandic`` extra
(GreynirCorrect / Icegrams / BÍN) is absent.

The public surface is assembled in the merge phase (see
``docs/plans/2026-06-16-ispipeline-extraction.md``). Until then this module
exposes only the version.
"""

__version__ = "0.1.0"

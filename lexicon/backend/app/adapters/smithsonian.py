"""Smithsonian Open Access (api): sense images, only usage.access == CC0.

Pictures bind to sense ids, so -- like wikimedia_commons -- the field
pipeline asks nothing here; app.images calls the Open Access API directly
(search_smithsonian / ingest_smithsonian).
"""

from __future__ import annotations

from .base import Context, SourceAdapter


class Smithsonian(SourceAdapter):
    key = "smithsonian"

    def lookup(self, field_key: str, ctx: Context):
        return []

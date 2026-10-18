"""Openverse (api): sense images, last-resort search across its many
providers (catalog: 須回原站核對授權 -- re-checked with Openverse's own
index right before downloading, never trusted from the search result alone).

Pictures bind to sense ids, so -- like wikimedia_commons -- the field
pipeline asks nothing here; app.images calls the Openverse API directly
(search_openverse / ingest_openverse).
"""

from __future__ import annotations

from .base import Context, SourceAdapter


class Openverse(SourceAdapter):
    key = "openverse"

    def lookup(self, field_key: str, ctx: Context):
        return []

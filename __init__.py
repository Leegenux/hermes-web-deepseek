"""DeepSeek web provider — user plugin entry point.

NOTE: a user plugin is imported as ``hermes_plugins.<slug>`` with the plugin
directory as its package search path, so the provider MUST be imported
RELATIVELY. The absolute form shown in the current developer docs
(``from plugins.web.deepseek.provider import ...``) resolves only for bundled
plugins and silently registers nothing here — see upstream issue #132334.
"""

from __future__ import annotations

from .provider import DeepSeekWebSearchProvider


def register(ctx) -> None:
    ctx.register_web_search_provider(DeepSeekWebSearchProvider())

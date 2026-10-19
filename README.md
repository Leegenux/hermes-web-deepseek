# hermes-web-deepseek

DeepSeek **Search + Fetch** backend for [Hermes Agent](https://github.com/NousResearch/hermes-agent) —
routes the built-in `web_search` / `web_extract` tools through
`https://api.deepseek.com/v1/tools/{search,fetch}`. No core changes, no wrapper skill.

## What it gives you

- **search** — DeepSeek's own index, up to 50 results per query, `position`-ordered
- **extract** — server-side page fetch returning Markdown, up to 5 URLs concurrently
- Per-URL failure isolation, one retry on `408/429/5xx`, cancel-aware, honest
  `supports_search()` / `supports_extract()`

## What DeepSeek opened up (2026-10-17 changelog)

From [api-docs.deepseek.com/updates](https://api-docs.deepseek.com/updates/) —
*"Opening up the in-house search API"*:

> DeepSeek's web and API search capabilities are powered by our in-house DeepSeek
> search engine, which reliably handles hundreds of millions of search requests from
> around the world every day. DeepSeek Search is an AI-native general-purpose search
> engine that indexes hundreds of billions of web pages, supports multilingual
> search, and returns highly relevant, authoritative, and timely results in real
> time. It filters SEO spam, GEO manipulation, and low-quality AIGC through strict
> detection mechanisms.

That is the capability this plugin exposes to Hermes: the same engine behind
DeepSeek's own web/APP search, reachable as `web_search` / `web_extract`.

Search queries forward their syntax intact, so the vendor's operators work
unchanged: `site:`, `-site:`, `"exact phrase"`, `-term`, `lang:zh,en`,
`after:2025-01-01`, `before:2026-06-01`.

Results also carry `rerank_score`, `authority` (0–4), `date` and `site_name`; this
provider maps `summary` → `description` and drops the rest, because Hermes'
`web_search` row shape is `title/url/description/position`.

## Install

```bash
hermes plugins install web-deepseek        # once the catalog entry is merged
```

Manual drop-in:

```bash
git clone https://github.com/Leegenux/hermes-web-deepseek \
  "$(hermes config env-path | xargs dirname)/plugins/web/deepseek"
hermes plugins enable web-deepseek
```

Put `DEEPSEEK_API_KEY` in `.env` (the same key the model API uses), then select it:

```bash
hermes config set web.search_backend deepseek-web
hermes config set web.extract_backend deepseek-web
# or both at once
hermes config set web.backend deepseek-web
```

The provider id is **`deepseek-web`** — not `deepseek`, which another catalog entry
already registers (two providers cannot share an id; whichever loads last wins).

A gateway restart applies new plugin code; a fresh CLI session reads it automatically.

## Cost and disclosure

- **$0.75 per 1,000 successful requests, per endpoint** (Search and Fetch billed
  separately, per the [official billing table](https://api-docs.deepseek.com/guides/search#billing)).
  A request is billable only when it returns HTTP 200 **and** produces a result —
  failed requests, empty result sets and timeouts are free. `count` does not affect
  the price.
- **5 QPS per account per endpoint**, search and fetch metered independently; Fetch
  additionally has a **per-domain QPS limit**, so a burst against one host can return
  `429` (the provider retries once). The provider runs at most 5 concurrent fetches,
  which is exactly the account budget.
- Credentials: only `DEEPSEEK_API_KEY`, sent as a Bearer token to
  `api.deepseek.com`. Nothing is stored by the plugin.

## Limitations (vendor-side, not fixable here)

- **Markdown only.** `fetch` has no HTML/text variant, so `web_extract(format="html")`
  silently returns Markdown. The `format` kwarg is accepted and ignored on purpose.
- **Static HTML only.** JavaScript-rendered pages and sites with anti-bot walls fail:
  知乎 / X (Twitter) / nytimes.com all returned `HTTP 404` in testing, while
  GitHub, arxiv, python docs, cloudflare blog and cls.cn worked.
- Requests originate from DeepSeek's servers, not yours — so local DNS/proxy problems
  don't affect it, but sites that block DeepSeek's crawler will fail.

## Development

Offline self-check (no network, no API key):

```bash
cd <this repo> && PYTHONPATH=<hermes install dir> python provider.py
# demo ok: search mapping, per-URL errors, order, timeouts, interrupt
```

Catalog admission check:

```bash
hermes plugins validate <this repo>
```

## License

MIT — see [LICENSE](LICENSE).

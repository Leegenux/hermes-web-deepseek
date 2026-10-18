# hermes-web-deepseek

DeepSeek **Search + Fetch** backend for [Hermes Agent](https://github.com/NousResearch/hermes-agent) —
routes the built-in `web_search` / `web_extract` tools through
`https://api.deepseek.com/v1/tools/{search,fetch}`. No core changes, no wrapper skill.

## What it gives you

- **search** — DeepSeek's own index, up to 50 results per query, `position`-ordered
- **extract** — server-side page fetch returning Markdown, up to 5 URLs concurrently
- Per-URL failure isolation, one retry on `408/429/5xx`, cancel-aware, honest
  `supports_search()` / `supports_extract()`

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
hermes config set web.search_backend deepseek
hermes config set web.extract_backend deepseek
# or both at once
hermes config set web.backend deepseek
```

A gateway restart applies new plugin code; a fresh CLI session reads it automatically.

## Cost and disclosure

- **5 CNY per 1,000 successful requests, per endpoint.** Every `web_search` /
  `web_extract` call is a separate server-side request to `api.deepseek.com` and is
  billed by DeepSeek.
- **5 QPS per account**, search and fetch counted separately. The provider runs at
  most 5 concurrent fetches, which is exactly that budget.
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

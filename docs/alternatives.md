# Alternative trials, 2026-10-30

The task is to retain dates declared by two existing XML files, join explicit URL/file mappings, and report both file hashes, both dates, provenance and incomplete coverage. This is a comparison task rather than a date-generation task.

## Trials before implementation

| Alternative | Attempt and observation | Fit for this task |
| --- | --- | --- |
| [SitemapKit sitemap diff](https://sitemapkit.com/tools/sitemap-diff) | Read its live page and downloaded the shipped `sitemap-diff` JavaScript. The form takes two XML inputs; its CSV fields are status, URL, changed fields and before/after lastmod. Browser automation was unavailable, so an interactive run remains unverified. | Useful for the XML half. No mapped content-file input or per-side content hash in the inspected interface/code. |
| [contentgate lastmod guard](https://github.com/adsandcode/contentgate/blob/main/src/contentgate/guards/lastmod.py) | Downloaded the Python module through GitHub's API and called `resolve` for Alpha, Beta, Gamma and Delta. With previous date 2026-10-29 and today 2026-10-30 it returned new dates 30, 29, 30, 29, respectively. | It chooses dates from normalized content and previous state. It does not consume the two existing sitemaps. In particular, the fixture's declared Beta date advances even though this resolver retains 29. |
| [content-hash-sitemap](https://github.com/KS-DB-Merge-Tools/content-hash-sitemap) | Downloaded and executed `generate_sitemap` against an isolated copy of the four files. It printed `updated files: 4` and wrote `sitemap.xml` and `file_info.json`. | It generates an XML and updates hash/date state, instead of preserving and comparing the two supplied XML files. |
| [Reference script](../scripts/reference.py) | Ran against the two generated local manifests, XML files and four file pairs. | Produces exactly one row in each quadrant. It lacks ambiguity handling, hardened reads, coverage reporting, resource limits and stability checks. |

The external Python modules ran only against disposable fixture copies. Their implementations are not vendored or reused by this package. The observations above do not establish that no other tool solves the task, and SitemapKit's interactive behavior was not verified.

## Reproduction

Run the commands in [development.md](development.md). The reference output is:

```text
https://example.test/alpha bytes-changed/date-unchanged
https://example.test/beta bytes-unchanged/date-changed
https://example.test/delta bytes-unchanged/date-unchanged
https://example.test/gamma bytes-changed/date-changed
```

The second fixture keeps those four pairs and adds Epsilon plus Missing, whose declared file is absent. The CLI must retain the two review candidates while marking incomplete coverage.

## Evidence and interpretation

The supplied 2026-10-30 research brief reports attention to technical SEO tooling, including [claude-seo](https://github.com/AgriciDaniel/claude-seo). That is category interest, not measured demand for this CLI. The frequency of mismatched snapshot observations, user time saved and willingness to pay have not been measured.

[Google Search Central](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap#additional-notes-about-xml-sitemaps), read on 2026-10-30, describes lastmod in terms of significant updates. The [sitemap protocol](https://www.sitemaps.org/protocol.html#xmlTagDefinitions), read on the same date, permits omission of lastmod and supports datetime precision beyond this first version. Neither turns a byte mismatch into proof that a declared date is incorrect. The fixture is synthetic; no indexing or ranking outcome was measured.

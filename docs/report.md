# Report contract, version 1

`lastmod-ledger compare before.json after.json --json` writes one JSON object to stdout. Errors also use JSON when `--json` is present. Text input errors go to stderr. CLI syntax errors use exit 3, and help uses exit 0.

| Exit | Status | Meaning |
| --- | --- | --- |
| 0 | complete | All enumerated URLs have unambiguous files and comparable dates; no discordant pairs |
| 1 | review | Complete comparison with one or more discordant pairs |
| 2 | incomplete | Coverage gaps or an empty comparison; review candidates remain in the report |
| 3 | input-error | Unreadable/invalid manifest or sitemap, rejected XML, or a top-level resource limit |

No exit status approves a deployment or certifies a site's dates. A fatal input error has `schema_version`, `status`, `exit_code`, and `error`, without partial results. Per-file failures retain results for other pairs and use exit 2.

## Results and counts

`results` contains one row for every exact decoded URL in either sitemap or manifest. Each row has:

- `url`: exact decoded XML or JSON value, without trimming, canonicalization or URL normalization.
- `presence`: `common`, `added`, `removed`, or `manifest-only`, based on XML membership.
- `before` and `after`: arrays of XML entries and manifest mappings, with issues. Duplicates retain all occurrences.
- `bytes_equal`, `dates_equal`: independently observed booleans, or null when unknown. File mappings must be unambiguous for byte comparison. Date comparison can still be known when the file is absent.
- `result`: one of the four quadrant names, or null if either comparison is unavailable.
- `review`: true only for a discordant quadrant.

`counts.urls = len(results) = sum(counts.presence.values())`.

`counts.compared = sum(counts.quadrants.values())`.

`counts.urls = counts.compared + counts.uncompared`.

`review_candidates = count(results where review is true)`.

`counts.incomplete_rows` counts rows without a quadrant or with coverage issues. It can overlap `compared`: an ignored extension can leave the base date/byte comparison observable while extension coverage remains incomplete. Added/removed URLs always lack a two-sided comparison and cause exit 2. A row can contain multiple issues; issue counts are not URL counts.

## Provenance and coverage

`coverage.before` and `coverage.after` retain every parsed top-level XML entry, including entries without usable loc values, and every manifest mapping. Each XML entry includes its tag, decoded `locs`, decoded literal `lastmods`, `date_status`, extensions and issues. XML source paths use prefix `s` for `http://www.sitemaps.org/schemas/sitemap/0.9`. `entry` is the one-based top-level child position; `xpath` is a structural locator, not a line number. JSON pointers are zero-based, such as `/files/0`.

Each successful observation includes its path, full SHA-256, exact byte size, stat identity and `stable`. Manifest and XML files are hashed too. Stat metadata is used only for detecting concurrent changes. Failed reads have no hash observation. A later change sets `stable: false`; the historical observed hash remains visible but is excluded from comparison. Changing a manifest or XML after reading invalidates comparisons involving that snapshot. Checks cannot establish an atomic snapshot or detect every possible change after the final check.

Dates are literal decoded element text. Whitespace is retained, so padded dates do not silently become valid. `date_status` is `date`, `missing`, `invalid`, `ambiguous`, or `outside-subset`. Valid W3C datetime forms with minute/second precision and timezone, and valid year/month precision, are outside the full-date subset. Invalid dates are entry-level coverage issues, not proof of an SEO violation. Missing `lastmod` is permitted by the sitemap protocol but leaves date comparison unavailable.

Indexes are parsed but not followed. Unknown top-level elements and extension elements are retained as out of scope. Standard `priority` and `changefreq` are ignored; only direct sitemap-namespace `loc` and `lastmod` are inspected. The command does not perform full XSD, host-consistency or URL-policy validation. URLs must be absolute HTTP(S) values without credentials or whitespace to be usable; Unicode values are retained literally.

## Bounds and reads

Limits apply to each manifest, sitemap and content read, with a shared byte budget for the command. Repeated mappings of the same file each consume the read budget. XML depth is capped at 32 and nodes at `20 * max_entries + 1`. Limits are positive integers. JSON duplicate object keys are rejected. Gzip input, wrong namespaces, malformed XML, DTDs and entity declarations are input errors. Predefined XML escapes such as `&amp;` are decoded normally.

Directory traversal uses file descriptors and `O_NOFOLLOW` for every path component. Regular-file checks reject directories, devices and FIFOs. This implementation targets POSIX systems with these facilities. A path through a symlinked parent is rejected even if its target is a regular file.

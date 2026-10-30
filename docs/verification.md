# Verification, 2026-10-30

The local release candidate was tested on macOS with Python 3.9.6.

| Check | Observed result |
| --- | --- |
| Clean copy installation, `python -m pip install '.[test]'` | Wheel built and installed successfully |
| `python -m pytest -q` from a clean clone | 56 passed |
| Four-pair demo | Exit 1, four URLs compared, two review candidates, one pair in each quadrant |
| Coverage demo | Exit 2, six URLs, four compared, two added/uncompared, two review candidates retained |
| Identical snapshot comparison | Exit 0, four unchanged-byte/unchanged-date pairs |
| Deliberate implementation mutations | Tests rejected XML-only comparison, files-only comparison and missing-file-as-empty behavior |
| Input integrity | Manifest, XML and file SHA-256 values unchanged after CLI comparisons |
| Fixture regeneration | Reproduces identical files and reference quadrant counts |
| Independent newcomer review | Clean installation, 56 tests and additional boundary cases passed; no blocking functional defect found |
| Package build | Source archive and universal Python wheel built successfully |
| pipx installation of local wheel | Installed version 0.1.0; manifest comparison ran from a separate consumer directory |
| README | 688 words |
| VHS demo | 1320 x 1260, 409 frames, 16.36 seconds; both runs visually inspected |

The VHS tape executed the CLI against checked-in fixtures. The normal recorder's browser launch failed in the restricted environment. Recording succeeded with VHS 0.12.1 using a local headless launcher adaptation and single-process Chromium. No terminal output was fabricated or replaced.

The independent reviewer followed the README and linked development instructions before inspecting implementation. Separate cases covered dates, duplicate mappings and XML URLs, omitted files and dates, namespace/DTD rejection, exact escaped queries, Unicode, empty comparisons, limits and symlinked parents. The suite additionally uses deterministic injected concurrent changes and checks hashes, sizes, provenance and count relationships.

## Remaining external checks

The exact GitHub pipx installation command was attempted with pipx. GitHub returned repository-not-found; the API returned HTTP 404. Public installation cannot be verified until the repository is available. Local clone and wheel installations passed.

CI is configured for Linux and macOS on Python 3.9, 3.12 and 3.14. Remote CI was not run, and those additional Python/platform combinations were not tested locally. The interactive SitemapKit trial remains unverified; its page and shipped code were inspected as recorded in [alternatives.md](alternatives.md).

No live site, indexing result, ranking effect or commercial demand was measured. Concurrent-change detection is bounded observation, not atomicity. Tests do not establish correctness under every possible race or full sitemap-schema conformance.

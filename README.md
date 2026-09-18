# The Supplier Blindspot

**Supplier intelligence for Arora Traders** — a 34-supplier scorecard, rupee-quantified losses, inference of the supplier behind untraced customer returns, and printable negotiation briefs, built from three years of transaction data. Upload your own six CSVs and the same analysis runs on them.

> MCCIA Applied AI Studio · Problem Statement 4

| | |
|---|---|
| **Live app** | _add deployed URL_ |
| **Approach document** | [`web/public/approach.pdf`](web/public/approach.pdf) (generated) |
| **Negotiation briefs** | [`web/public/briefs/`](web/public/briefs/) — five 2-page A4 PDFs |

## Results

| | |
|---|---|
| Bottom three (D5) | **VS19 Thakur Steel, VS03 Tata Steel Service, VS12 Nutan Tubes** — 9% of spend, 54% of all quantified losses |
| Short delivery + returns, all suppliers (the rubric's formula) | ₹15.99 Cr over 3 years |
| Untraced returns attributed | 140 of 380; **5.3%** of return value misallocated under cross-validation, vs 47.9% for the problem statement's most-recent-batch rule |
| Blind validation | The sealed `is_underperformer` column was never used; our bottom three match it **3/3**, 69 score points clear of the next supplier |
| Weight robustness | Bottom three identical under all 5 weightings tested |
| Sanity check | Excess leakage of the bottom three is 0.95% of spend → **₹7.9–9.7 L/year** at the PS's stated ₹70–85 L/month procurement, inside its ₹8–12 L estimate |

## Run it

```bash
# 1. Analysis: raw CSVs in, every output out (~10 s; PDFs need Edge or Chrome)
pip install -r requirements-dev.txt
python -m pipeline.preflight      # optional: data audit, prints every assumption check
python -m pipeline.run            # scorecard, attribution, JSON, CSVs, briefs, approach PDF
python -m pytest                  # 40 tests: pipeline, web contract, upload API
python -m evaluation.run          # synthetic datasets with a known answer -> evaluation/REPORT.md
ruff check pipeline tests

# 2. Web app
cd web
npm install
npm run dev                       # http://localhost:5173
npm run check                     # Biome lint + TypeScript
npm run build                     # static site in web/dist
npm run pipeline                  # re-run the Python analysis from here

# 3. Upload API (for the Upload page) -- run alongside `npm run dev`
cd ..
uvicorn api.main:app --port 8000  # interactive docs at http://localhost:8000/docs
```

Open **http://localhost:5173/#/upload**, drop in six CSVs (any file names) or pick a generated sample, and every page switches to that analysis. A banner shows which dataset you're viewing, with a shareable link and a button back to the assignment data.

On a new dataset: drop the six CSVs (any file names) into `pipeline/data/raw/` or pass `--raw path/`, then run the same command. Suppliers, materials and thresholds are discovered; the model refits. `--no-pdf` skips browser printing.

## How it works

```
CSVs ─► 01 load ─► 02 join ─► 03 attribute ─► 04 rupees ─► 05 score ─► 06 validate ─► 07 briefs ─► 08 export
         │          │          │                 │             │            │               │             │
   signature   row-count   logistic ranker   rubric formula  shrinkage,   weight sweep,   A4 HTML →     JSON → React app
   detection,  asserted    over suppliers,   verbatim; peer  0–100,       sealed-label    PDF           CSV → output/
   answer key  joins       causal features,  benchmark +     per material check
   sealed                  grouped CV        FDR-tested premium
```

| Module | Responsibility |
|---|---|
| [`pipeline/config.py`](pipeline/config.py) | Every tunable, with its reasoning. No dataset-specific values anywhere. |
| [`pipeline/load.py`](pipeline/load.py) | Identify files by columns, coerce types, fail on mixed units / missing files, seal the answer key. |
| [`pipeline/prepare.py`](pipeline/prepare.py) | One row per PO; every join asserts its row count; recompute payment lateness. |
| [`pipeline/attribute.py`](pipeline/attribute.py) | Supplier attribution for untraced returns + validation against baselines. |
| [`pipeline/money.py`](pipeline/money.py) | ₹ per order and per supplier; peer price benchmark; premium significance test. |
| [`pipeline/score.py`](pipeline/score.py) | Scorecard, per-material view, weight stability, blind validation, D5 alternatives. |
| [`pipeline/brief.py`](pipeline/brief.py) | Negotiation brief content and PDF rendering. |
| [`pipeline/report.py`](pipeline/report.py) | The approach document, generated from the same run. |
| [`api/`](api/) | FastAPI upload service: receives CSVs, runs the same `pipeline.run()` in a sandboxed folder per analysis, serves the resulting JSON and briefs. Size limits, validated ids, automatic expiry. |
| [`web/`](web/) | Vite + React + TypeScript + Tailwind. Bundles the assignment results; the Upload page fetches any other analysis from the API in the same shape. |

### Key decisions

- **The rubric's formula is the headline.** `invoice_amount_billed − quantity_received × unit_price_quoted` per order, plus attributed return value. Rejected material, handling cost and price premium are quantified in a separate, labelled tier.
- **Attribution is a ranking over suppliers, not a batch lookup.** Returns carry no PO or batch, and on labelled data the recorded supplier is rarely the latest batch's supplier. Features are computed only from deliveries before the return date; the label-derived feature is rebuilt inside each CV fold. Recorded returns are claimed in briefs; inferred ones are shown as estimates only.
- **No unsupported price claims.** The market index covers 6 of 18 materials and sits far below what every supplier charges, so the benchmark is other suppliers' prices for the same material and quarter. Premiums are tested (Benjamini–Hochberg); none survives, so ₹0 is charged.
- **Evidence-weighted scoring.** Empirical-Bayes shrinkage stops thin histories dominating; `years_of_relationship` is never read (and a test proves it).
- **Static web app.** Every number is precomputed, so the deployed site does no computation, loads instantly and cannot fail at runtime.

## Tested beyond the assignment data

[`evaluation/`](evaluation/) generates datasets in the assignment's schema where the answer is planted — which suppliers are bad and how, and the true supplier behind every return, including those blanked out — then runs the pipeline unchanged and scores it. See [`evaluation/REPORT.md`](evaluation/REPORT.md).

| Scenario | Offenders found | Hidden-return value misallocated (model vs PS rule) | ₹ vs truth |
|---|---|---|---|
| Larger panel (70 suppliers, 14k orders), subtler offenders | 5/5 | 14.5% vs 21.6% | exact |
| Each offender fails one way; one bad on a single material | 4/4, right dimension each time; single-material offender flagged only there | 12.0% vs 21.6% | exact |
| Sparse & messy (15% labelled, duplicates, broken dates, tiny suppliers) | 3/3; unlucky 2-order supplier not condemned | 13.8% vs 26.4% | exact |
| Control: nobody is bad | 0 false alarms | 19.2% vs 23.2% | exact |
| Two suppliers go bad only in the final year | 4/4; both late deteriorators flagged, year view shows ₹24 L/yr → ₹1.6–1.9 Cr | 14.2% vs 22.4% | exact |
| Assignment-like returns at scale (120 suppliers, 30k orders) | 6/6 | 15.1% vs 22.8% | exact |
| Indian spreadsheet exports (DD/MM/YYYY, 12,34,567.89, BOM, extra columns) | 3/3, identical to clean files | 15.7% vs 28.5% | exact |
| A small supplier (12 orders) that is genuinely bad | 3/3; ranked last of 40 — small-supplier protection doesn't hide real failure | 16.8% vs 24.3% | exact |
| Returns recorded selectively (90% for problem suppliers, 45% for others) | 3/3 | **29.4% vs 17.1% — the model is worse here** | exact |

The last row is a real limitation, stated on the site: if recorded returns aren't typical of unrecorded ones, the estimate leans towards the suppliers who get recorded more, and no method can detect that from the data alone. That is why briefs only ever claim recorded returns. `python -m evaluation.audit` separately recomputes every headline figure from the raw CSVs without using the pipeline, and checks the site matches (28/28).

The harness found weaknesses the assignment data could not reveal — relative scaling that condemned someone even on a clean panel, a biased price test, an attribution model that could underperform a simple exposure rule on sparse labels, and a loader that misread Indian-format amounts and could misread DD/MM dates. All were fixed and are covered by tests.

## Integration

The pipeline and the web app share one contract: [`web/src/lib/types.ts`](web/src/lib/types.ts).
[`tests/test_contract.py`](tests/test_contract.py) parses those interfaces and fails if any required field is
missing from the pipeline's output, or if the JSON committed under `web/src/data/` is stale relative to a fresh run.
CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs ruff + pytest and Biome + tsc + build on every push.

Bundle: app code and overview data load in ~29 KB gzipped; React ships as a separately cached vendor chunk; per-supplier
detail and the returns table load only with the pages that use them.

## Deploy

Two independent pieces. The web app works on its own (assignment results are bundled); the API adds uploads.

**Web app.** The hosted build runs only `npm run build`, so the pipeline's outputs (`web/src/data/`, `web/public/briefs/`, `web/public/approach.pdf`) are committed. Set `VITE_API_URL` to the API's URL to enable uploads.

- **Netlify** — import the repo; [`netlify.toml`](netlify.toml) sets base `web`, publish `dist`.
- **Vercel** — import the repo, set Root Directory to `web`; [`web/vercel.json`](web/vercel.json) does the rest.
- **Anywhere else** — `cd web && npm run build` and upload `web/dist/`. Hash routing means no rewrite rules are needed.

**API.** [`render.yaml`](render.yaml) deploys it on Render (free tier; it sleeps when idle, so the first upload after a while takes ~30–50 s to wake it). Set `SI_CORS_ORIGINS` to the web app's URL. Other settings (`SI_MAX_FILE_MB`, `SI_TTL_MINUTES`, `SI_PDF`, …) are in [`api/settings.py`](api/settings.py).

## Data

The six source CSVs are in [`pipeline/data/raw/`](pipeline/data/raw/) and the problem statement is in [`docs/problem_statement.pdf`](docs/problem_statement.pdf).

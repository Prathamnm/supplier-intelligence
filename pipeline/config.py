"""Every tunable constant in the project lives here.

Design rule: no magic numbers anywhere else in the codebase, and no
dataset-specific values at all -- no supplier IDs, no material names,
no thresholds derived from looking at these particular CSVs. Swap in a
different dataset and the pipeline discovers its own suppliers,
categories and distributions.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------- paths

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "pipeline" / "data" / "raw"
TEMPLATES = ROOT / "pipeline" / "templates"

# The web app imports the JSON at build time; briefs are static files
# served next to it.
WEB = ROOT / "web"
WEB_DATA = WEB / "src" / "data"
WEB_BRIEFS = WEB / "public" / "briefs"

# A copy of every output, independent of the web app, for reviewers who
# only want the numbers.
OUT = ROOT / "output"

# Expected source files. Detection is by column signature (see load.py),
# not by filename, so these are defaults rather than requirements.
FILES = {
    "purchase_orders": "purchase_orders.csv",
    "goods_receipts": "goods_receipts.csv",
    "customer_returns": "customer_returns.csv",
    "market_price_index": "market_price_index.csv",
    "payment_records": "payment_records.csv",
    "supplier_master": "supplier_master.csv",
}

# ------------------------------------------------------------- leakage

# The answer key. Dropped at load time, never seen by any scoring or
# modelling code, and re-read only at the very end for blind validation.
LABEL_COLUMN = "is_underperformer"

# -------------------------------------------------------------- loading

# A required date or number column with more than this share of values that
# cannot be parsed stops the run: continuing would produce confident nonsense.
MAX_UNPARSEABLE_SHARE = 0.05
# Orders missing a quantity, price or amount are left out, up to this share;
# beyond it the export itself is suspect and the run stops.
MAX_INCOMPLETE_SHARE = 0.10
# Attribution builds one row per (return, supplier) pair and memory grows with it:
# ~130k pairs peak near 300 MB, ~460k near 550 MB. The hosted API sets a cap
# (SI_MAX_PAIRS) that fits its 512 MB; run locally, there is no limit.
MAX_CANDIDATE_PAIRS = int(os.environ.get("SI_MAX_PAIRS", "0")) or None
# Scores compare suppliers with each other, so fewer than this is not a panel.
MIN_SUPPLIERS = 3

# ---------------------------------------------------------- attribution

# Every supplier that delivered anything before the return date is a
# candidate. These windows shape the per-candidate features only.
MATERIAL_SHARE_WINDOW_DAYS = 180   # "how much of this material on our floor was theirs"
RECENCY_HALFLIFE_DAYS = 90         # recency = exp(-days since their last batch / this)

# Below this many labelled returns there is not enough signal to fit a
# model; the pipeline falls back to the most-recent-batch rule and says
# so loudly in the output.
MIN_LABELLED_FOR_TRAINING = 10
LOW_CONFIDENCE_LABELLED = 50

# Candidate weights for blending the learned model with plain exposure;
# the one with the lowest held-out log loss is used.
BLEND_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)

# Laplace smoothing for the supplier return-propensity prior.
PRIOR_SMOOTHING = 1.0

CV_FOLDS = 5
RANDOM_SEED = 42

# ------------------------------------------------------------- money

# Cost of processing a customer return -- inspection, restocking,
# freight -- as a multiple of material value. Reported as a separate,
# clearly-labelled tier: the rubric's figure uses material value only.
RETURN_HANDLING_FACTOR = 0.15

# Peer benchmark: median price quoted by *other* suppliers for the same
# material in the same period. Falls back to the whole history when a
# period has too few other suppliers to be meaningful.
PEER_PERIOD = "Q"
MIN_PEERS = 3

# A supplier's price premium is only charged in rupees when it is
# statistically distinguishable from zero after correcting for testing
# every supplier at once (Benjamini-Hochberg false discovery rate).
PREMIUM_FDR = 0.05

# A published index is shown as context only when it sits within this
# band of what the panel actually transacts.
INDEX_SANITY_HIGH = 1.5
INDEX_SANITY_LOW = 0.67

# ----------------------------------------------------------- scorecard

# The four dimensions named in the problem statement. Nothing else
# enters the score -- in particular not years_of_relationship, which the
# brief explicitly forbids as a positive factor.
WEIGHTS = {
    "short_delivery": 0.30,
    "quality_rejection": 0.25,
    "price_premium": 0.20,
    "late_delivery": 0.25,
}

# Alternative weightings used to show the bottom-3 ranking does not
# depend on the choice above.
WEIGHT_SCENARIOS = {
    "equal": {"short_delivery": .25, "quality_rejection": .25,
              "price_premium": .25, "late_delivery": .25},
    "money_heavy": {"short_delivery": .40, "quality_rejection": .30,
                    "price_premium": .20, "late_delivery": .10},
    "service_heavy": {"short_delivery": .20, "quality_rejection": .20,
                      "price_premium": .15, "late_delivery": .45},
    "price_heavy": {"short_delivery": .20, "quality_rejection": .20,
                    "price_premium": .45, "late_delivery": .15},
}

# Empirical-Bayes shrinkage strength, in orders. A rate is pulled toward
# the panel (or the supplier's own overall rate, for a category cell)
# until there are enough orders to have earned the reading:
#     (n * observed + k * prior) / (n + k)
SHRINKAGE_K = 5

# Scoring scale. Each dimension is measured in robust standard deviations
# from the typical supplier (median, MAD). A dimension scores 100 at or
# better than typical and 0 at this many units worse:
ZERO_AT_UNITS = 6.0

# ...where a unit is never smaller than a difference that matters to a
# buyer. Without this floor, a panel where everyone is near-identical
# would turn trivial noise into "failures".
MATERIALITY = {
    "short_delivery": 0.25,     # percentage points of ordered quantity
    "late_delivery": 0.5,       # days
    "quality_rejection": 0.25,  # percentage points of received quantity
    "price_premium": 1.0,       # percentage points over peers
}

# Status bands. "act" needs an overall score this low, or any single
# dimension this far gone -- a pure overcharger is not excused by being
# on time.
BAND_ACT_SCORE = 40
BAND_ACT_DIMENSION = 10
BAND_WATCH_SCORE = 70
BAND_WATCH_DIMENSION = 50

# Fewer orders than this and the supplier / category cell is flagged
# low-confidence rather than ranked with the same authority.
MIN_ORDERS_FOR_CONFIDENCE = 5

# A category is called out as a problem for a supplier when its shrunk
# rate is at least this multiple of the panel rate for that category.
CATEGORY_FLAG_MULTIPLE = 2.0

# ------------------------------------------------------------- output

# Where the project lives, quoted in the approach document.
# The business in the assignment data. Briefs name it only for that data;
# an uploaded dataset gets a neutral header.
COMPANY = "Arora Traders"

LIVE_URL = "https://supplier-intelligence-iota.vercel.app"
REPO_URL = "https://github.com/Prathamnm/supplier-intelligence"

TOP_N_BRIEFS = 5          # D4: negotiation briefs
TOP_N_REPLACE = 3         # D5: suppliers to replace
ALTERNATIVES_PER_CATEGORY = 2
EVIDENCE_POS_PER_BRIEF = 5

# Suggested late-delivery penalty for the brief's contract ask, as a
# fraction of order value per day late. A negotiating position, not a
# computed loss -- it is never added to any rupee total.
# A price ask is only worth raising when the supplier's median for a
# material sits at least this far above the panel median.
MIN_PRICE_ASK_PCT = 2.0

LATE_PENALTY_PER_DAY = 0.005
LATE_PENALTY_CAP = 0.05

# --------------------------------------------------------- validation

# The problem statement estimates a Rs 8-12L annual loss across the
# three underperformers. Reported next to our independent figure.
PS_ANNUAL_LOSS_LOW = 8_00_000
PS_ANNUAL_LOSS_HIGH = 12_00_000

# The problem statement's stated procurement, Rs 70-85L a month. The
# supplied data transacts far more than that, so our loss *rate* (as a
# share of spend) is scaled to this band to compare like with like.
PS_MONTHLY_PROCUREMENT_LOW = 70_00_000
PS_MONTHLY_PROCUREMENT_HIGH = 85_00_000

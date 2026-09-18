"""Stages 05-06 -- aggregate fairly, score, rank, recommend.

Scorecard (D2). Four dimensions, exactly the ones the problem statement
names, each a rate so a large supplier is not penalised for being large:

    short_delivery     quantity not delivered / quantity ordered
    late_delivery      average days late per order (the share of orders
                       late is reported too, but almost every supplier is
                       late by a day or two, so it barely separates them)
    quality_rejection  (rejected at our inspection + returned by our
                        customers, attributed) / quantity received
    price_premium      average premium over peer suppliers, same material
                        and quarter

years_of_relationship is not read anywhere in this module.

Fairness. Rates are pulled toward the panel average in proportion to how
little evidence a supplier has (empirical-Bayes shrinkage), so three bad
orders from a tiny supplier cannot put them at the bottom of the table.
Price premium is shrunk by its own noise: when the spread between
suppliers is no bigger than the order-to-order noise would produce, the
premium carries no information and every supplier scores alike on it.

Each dimension is scored by how far a supplier sits from the typical
supplier, in robust standard deviations (never smaller than a difference
that matters commercially): 100 at or better than typical, 0 at six units
worse. Unlike scaling to the panel's best and worst, this cannot turn
noise into failures -- on a panel where nobody is bad, nobody scores 0.
Scores are combined with the weights in config.py. The bottom
of the ranking is re-derived under four alternative weightings to show
the conclusion does not depend on that choice.

Blind validation. After the ranking is frozen, the sealed answer key is
opened for the first and only time and compared with the bottom three.

Recommendation (D5). The bottom three are recommended for replacement.
For each, every material they supply is re-sourced to the best-scoring
alternatives already on the panel for *that material*, with the rupee
leakage the switch would have avoided.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from pipeline import config
from pipeline.quality import Quality

STAGE = "05-score"

DIMENSIONS = ["short_delivery", "late_delivery", "quality_rejection", "price_premium"]

# The raw measurement behind each dimension (percent, except late
# delivery which is days).
METRIC = {
    "short_delivery": "short_delivery_pct",
    "late_delivery": "mean_days_late",
    "quality_rejection": "quality_rejection_pct",
    "price_premium": "price_premium_pct",
}

DIMENSION_LABELS = {
    "short_delivery": "Short delivery",
    "late_delivery": "Late delivery",
    "quality_rejection": "Quality",
    "price_premium": "Price",
}


@dataclass
class Scorecard:
    suppliers: pd.DataFrame
    categories: pd.DataFrame
    stability: dict = field(default_factory=dict)
    validation: dict = field(default_factory=dict)
    replacements: list = field(default_factory=list)


# ---------------------------------------------------------------- helpers

def _shrink(rate: pd.Series, n: pd.Series, prior: pd.Series | float,
            k: float = config.SHRINKAGE_K) -> pd.Series:
    return (n * rate + k * prior) / (n + k)


def _shrink_by_noise(mean: pd.Series, se: pd.Series) -> pd.Series:
    """James-Stein style: keep only the between-supplier signal.

    tau^2 = variance of supplier means beyond what sampling noise alone
    explains. If it is zero, the premiums are indistinguishable from
    noise and all collapse to the panel mean.
    """
    grand = mean.mean()
    tau2 = max(float(mean.var(ddof=1) - (se ** 2).mean()), 0.0)
    weight = tau2 / (tau2 + se ** 2) if tau2 > 0 else pd.Series(0.0, index=mean.index)
    return grand + weight * (mean - grand)


def _robust_scale(values: pd.Series, dim: str) -> tuple[float, float]:
    """Centre and unit for a dimension: median, and MAD-based SD floored at materiality."""
    med = float(values.median())
    mad = float((values - med).abs().median()) * 1.4826
    return med, max(mad, config.MATERIALITY[dim])


def _score_dim(values: pd.Series, centre: float, unit: float) -> pd.Series:
    """100 at or better than typical, falling to 0 at ZERO_AT_UNITS worse."""
    z = (values - centre) / unit
    return (100 * (1 - z.clip(lower=0) / config.ZERO_AT_UNITS)).clip(0, 100)


def _band(total: float, dims: list[float]) -> str:
    worst = min(dims)
    if total < config.BAND_ACT_SCORE or worst <= config.BAND_ACT_DIMENSION:
        return "act"
    if total < config.BAND_WATCH_SCORE or worst < config.BAND_WATCH_DIMENSION:
        return "watch"
    return "good"


def _composite(dim_scores: pd.DataFrame, weights: dict) -> pd.Series:
    return sum(dim_scores[f"score_{d}"] * w for d, w in weights.items())


# ------------------------------------------------------------- scorecard

def build(totals: pd.DataFrame, orders: pd.DataFrame, cats: pd.DataFrame,
          q: Quality) -> pd.DataFrame:
    s = totals.copy().set_index("supplier_id")

    late = orders.groupby("supplier_id").agg(
        supplier_name=("supplier_name", "first"),
        late_orders=("is_late", "sum"),
        mean_days_late=("days_late_delivery", lambda x: x.clip(lower=0).mean()),
        mean_days_late_when_late=("days_late_delivery", lambda x: x[x > 0].mean()),
        max_days_late=("days_late_delivery", "max"),
        arora_paid_days_late=("payment_days_late_computed", "mean"),
    )
    s = s.join(late)
    s["mean_days_late_when_late"] = s["mean_days_late_when_late"].fillna(0)

    # Raw rates, in percent.
    s["short_delivery_pct"] = 100 * s["qty_short"] / s["qty_ordered"]
    s["late_orders_pct"] = 100 * s["late_orders"] / s["orders"]
    s["receiving_rejection_pct"] = 100 * s["qty_rejected"] / s["qty_received"]
    s["customer_return_pct"] = 100 * s["qty_returned"] / s["qty_received"]
    s["quality_rejection_pct"] = s["receiving_rejection_pct"] + s["customer_return_pct"]
    s["price_premium_pct"] = s["premium_mean_pct"]

    n = s["orders"]
    for d in ["short_delivery", "late_delivery", "quality_rejection"]:
        raw = s[METRIC[d]]
        panel = float((raw * n).sum() / n.sum())
        s[f"{d}_adj"] = _shrink(raw, n, panel)
    se = (s["premium_ci_high"] - s["premium_ci_low"]) / (2 * 1.96)
    s["price_premium_adj"] = _shrink_by_noise(s["premium_mean_pct"], se)

    for d in DIMENSIONS:
        centre, unit = _robust_scale(s[f"{d}_adj"], d)
        s[f"score_{d}"] = _score_dim(s[f"{d}_adj"], centre, unit)
    s["score"] = _composite(s, config.WEIGHTS)

    s["rank"] = s["score"].rank(ascending=False, method="first").astype(int)  # 1 = best
    s["risk_rank"] = s["score"].rank(ascending=True, method="first").astype(int)  # 1 = worst
    s["low_confidence"] = s["orders"] < config.MIN_ORDERS_FOR_CONFIDENCE
    s["band"] = [_band(r["score"], [r[f"score_{d}"] for d in DIMENSIONS]) for _, r in s.iterrows()]

    # Which dimensions drive each supplier's score down, worst first.
    def _drivers(row: pd.Series) -> list[str]:
        gaps = {d: 100 - row[f"score_{d}"] for d in DIMENSIONS}
        return [d for d, g in sorted(gaps.items(), key=lambda kv: -kv[1]) if g >= 50]
    s["drivers"] = s.apply(_drivers, axis=1)

    q.info(STAGE, "Scorecard built",
           f"{len(s)} suppliers scored on {len(DIMENSIONS)} dimensions "
           f"(weights {config.WEIGHTS}); shrinkage k={config.SHRINKAGE_K} orders. "
           f"years_of_relationship not used.")
    return s.reset_index().sort_values("risk_rank").reset_index(drop=True)


def category_scorecard(cats: pd.DataFrame, suppliers: pd.DataFrame) -> pd.DataFrame:
    """Supplier x material view -- the multi-category requirement.

    Each cell's rates are shrunk toward that supplier's own overall rate,
    so a single bad order in a thin category does not dominate, and then
    compared with the panel's rate for the same material.
    """
    c = cats.copy()
    sup = suppliers.set_index("supplier_id")

    c["short_delivery_pct"] = 100 * c["qty_short"] / c["qty_ordered"]
    c["late_orders_pct"] = 100 * c["late_orders"] / c["orders"]
    c["quality_rejection_pct"] = 100 * (c["qty_rejected"] + c["qty_returned"]) / c["qty_received"]
    c["price_premium_pct"] = 100 * c["premium_pct"]

    for d in ["short_delivery", "late_delivery", "quality_rejection", "price_premium"]:
        m = METRIC[d]
        own = c["supplier_id"].map(sup[m])
        c[f"{d}_adj"] = _shrink(c[m].fillna(own), c["orders"], own)
        tot = c.groupby("material_id")
        panel = (c[m] * c["orders"]).groupby(c["material_id"]).transform("sum") \
            / tot["orders"].transform("sum")
        c[f"{d}_panel"] = panel

    for d in DIMENSIONS:
        col = f"{d}_adj"
        # Same centre and unit as the supplier-level score, so a material
        # cell and its supplier are on one scale.
        centre, unit = _robust_scale(sup[col], d)
        c[f"score_{d}"] = _score_dim(c[col], centre, unit)
    c["score"] = _composite(c, config.WEIGHTS)

    flags = []
    for _, r in c.iterrows():
        f = [d for d in ["short_delivery", "late_delivery", "quality_rejection"]
             if r[f"{d}_panel"] > 0 and r[f"{d}_adj"] >= config.CATEGORY_FLAG_MULTIPLE * r[f"{d}_panel"]]
        flags.append(f)
    c["flags"] = flags
    c["leakage"] = c["short_loss"] + c["reject_loss"] + c["return_loss"]
    c["leakage_per_lakh"] = np.where(c["spend"] > 0, c["leakage"] / c["spend"] * 1e5, 0)
    c["low_confidence"] = c["orders"] < config.MIN_ORDERS_FOR_CONFIDENCE
    return c


# ------------------------------------------------------------ robustness

def stability(s: pd.DataFrame) -> dict:
    """Does the bottom of the table survive other weightings?"""
    k = config.TOP_N_REPLACE
    base = set(s.nsmallest(k, "score")["supplier_id"])
    scenarios = {"base": {"weights": config.WEIGHTS, "bottom": sorted(base), "same_as_base": True}}
    ranks = {}
    for name, w in config.WEIGHT_SCENARIOS.items():
        sc = _composite(s, w)
        bottom = set(s.loc[sc.nsmallest(k).index, "supplier_id"])
        scenarios[name] = {"weights": w, "bottom": sorted(bottom),
                           "same_as_base": bottom == base}
        ranks[name] = dict(zip(s["supplier_id"], sc.rank(ascending=True).astype(int), strict=True))
    stable = all(v["same_as_base"] for v in scenarios.values())
    return {"k": k, "stable": stable, "scenarios": scenarios, "risk_ranks": ranks}


def blind_validation(s: pd.DataFrame, sealed: dict[str, bool], q: Quality) -> dict:
    """Open the sealed answer key -- only now, after ranking is final."""
    if not sealed:
        return {"available": False}
    flagged = sorted(k for k, v in sealed.items() if v)
    k = len(flagged)
    bottom = list(s.nsmallest(k, "score")["supplier_id"])
    hits = sorted(set(bottom) & set(flagged))
    positions = {sid: int(s.loc[s["supplier_id"] == sid, "rank"].iloc[0])
                 for sid in flagged if sid in set(s["supplier_id"])}
    result = {
        "available": True,
        "flagged": flagged,
        "our_bottom": bottom,
        "hits": hits,
        "precision": len(hits) / k if k else None,
        "flagged_ranks": positions,
        "n_suppliers": int(len(s)),
        # Score margin between our bottom k and the next supplier up.
        "gap_to_next": float(s.nsmallest(k + 1, "score")["score"].iloc[-1]
                             - s.nsmallest(k, "score")["score"].iloc[-1]) if 0 < k < len(s) else None,
    }
    q.info("06-validate", "Blind validation",
           f"The dataset's own `is_underperformer` flag marks {flagged}. Our "
           f"bottom {k}, computed without it: {bottom}. {len(hits)}/{k} match.")
    return result


# -------------------------------------------------------- recommendation

def recommend(s: pd.DataFrame, c: pd.DataFrame) -> list[dict]:
    """D5 -- who to replace, and with whom, material by material."""
    replace = list(s.nsmallest(config.TOP_N_REPLACE, "score")["supplier_id"])
    pool = c[~c["supplier_id"].isin(replace) & ~c["low_confidence"]]
    names = s.set_index("supplier_id")["supplier_name"]
    overall = s.set_index("supplier_id")

    out = []
    for sid in replace:
        mine = c[c["supplier_id"] == sid].sort_values("spend", ascending=False)
        materials = []
        for _, m in mine.iterrows():
            alts = (pool[pool["material_id"] == m["material_id"]]
                    .sort_values(["score", "leakage_per_lakh"], ascending=[False, True])
                    .head(config.ALTERNATIVES_PER_CATEGORY))
            best_rate = alts["leakage_per_lakh"].iloc[0] / 1e5 if len(alts) else 0.0
            avoidable = max(m["leakage"] - best_rate * m["spend"], 0.0)
            materials.append({
                "material": m["material_id"],
                "orders": int(m["orders"]),
                "spend": float(m["spend"]),
                "leakage": float(m["leakage"]),
                "avoidable": float(avoidable),
                "alternatives": [{
                    "supplier_id": a["supplier_id"],
                    "supplier_name": names.get(a["supplier_id"], a["supplier_id"]),
                    "score": float(a["score"]),
                    "orders": int(a["orders"]),
                    "short_pct": float(a["short_delivery_pct"]),
                    "days_late": float(a["mean_days_late"]),
                    "quality_pct": float(a["quality_rejection_pct"]),
                    "median_price": float(a["median_price"]),
                } for _, a in alts.iterrows()],
            })
        row = overall.loc[sid]
        out.append({
            "supplier_id": sid,
            "supplier_name": names.get(sid, sid),
            "score": float(row["score"]),
            "rank": int(row["rank"]),
            "total_impact": float(row["total_impact"]),
            "rubric_core_total": float(row["rubric_core_total"]),
            "avoidable_total": float(sum(m["avoidable"] for m in materials)),
            "drivers": list(row["drivers"]),
            "materials": materials,
        })
    return out

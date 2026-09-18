"""Stage 03 -- supplier attribution for unlabelled customer returns.

The problem: customer_returns.csv records what came back and when, but
for roughly a third of rows nobody wrote down which supplier's material
it was. There is no po_id or batch number on a return, so this cannot be
solved with a join -- not even for the rows that *are* labelled.

What the data says (the approach document has the numbers): the supplier
recorded on a labelled return is rarely the one whose batch of that
material arrived most recently. The problem statement's suggested rule
therefore performs poorly, and the signal that does predict the source
is the supplier's own receiving history -- whose material failed our
inspection, arrived short, arrived late.

The approach:

1. Candidates. Every supplier that had delivered anything before the
   return date. One row per (return, supplier).

2. Features. Six numbers per candidate, each computed *causally* --
   only from goods receipts dated on or before the return, so the model
   never sees the future:
     recency             how recently their last batch of this material arrived
     material_share      their share of this material received in the window
     rejection_rate      share of their deliveries rejected at our inspection
     short_rate          share of ordered quantity they failed to deliver
     late_days           average days late
     return_prior        returns per 1,000 MT previously traced to them
   The return prior uses labels, so under cross-validation it is rebuilt
   inside every fold from the training returns only.

3. Model. Logistic regression on the pairs, normalised per return so
   each return's probabilities sum to one (a conditional-logit style
   ranker). Seven numbers, fitted in well under a second.

   The model's probabilities are blended with plain exposure (each
   supplier's recent share of that material), with the mix chosen by
   held-out log loss -- so it can never do worse than that simple rule
   on the labelled data, and falls back to it when there is no signal.

4. Validation. 5-fold cross-validation grouped by return, on the
   labelled returns: hide the answer, predict, compare. Reported next to
   three baselines -- including the most-recent-batch rule the problem
   statement describes -- on two metrics: whether the right supplier is
   ranked first / in the top three, and how much return value ends up
   allocated to the wrong supplier in aggregate. The second is the one
   the rupee totals depend on.

Recorded returns are always assigned 100% to their recorded supplier.
Inferred returns carry the full probability distribution: the rupee
totals split their value by probability, and the brief names the top
supplier with its confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from pipeline import config
from pipeline.quality import Quality

STAGE = "03-attribute"

FEATURES = [
    "recency",
    "material_share",
    "rejection_rate",
    "short_rate",
    "late_days",
    "return_prior",
]

FEATURE_LABELS = {
    "recency": "How recently their last batch of this material arrived",
    "material_share": "Their share of this material received in the prior window",
    "rejection_rate": "Share of their deliveries rejected at our inspection",
    "short_rate": "Share of ordered quantity they failed to deliver",
    "late_days": "Average days late on delivery",
    "return_prior": "Returns previously traced to them, per 1,000 MT supplied",
}


@dataclass
class Attribution:
    """Everything stage 03 produces."""

    pairs: pd.DataFrame        # return_id, supplier_id, probability, source
    per_return: pd.DataFrame   # one row per return: pick, confidence, top-3
    metrics: dict = field(default_factory=dict)
    baselines: dict = field(default_factory=dict)
    coefficients: dict = field(default_factory=dict)
    calibration: list = field(default_factory=list)
    method: str = "model"      # "model" or "fallback"


# --------------------------------------------------------------- features

def _cum_at(dates: np.ndarray, cum: np.ndarray, when: np.ndarray) -> np.ndarray:
    """Cumulative value of a running total as of each date in `when`."""
    idx = np.searchsorted(dates, when, side="right")
    padded = np.concatenate([[0.0], cum])
    return padded[idx]


def build_candidates(returns: pd.DataFrame, fact: pd.DataFrame,
                     q: Quality) -> pd.DataFrame:
    """Every (return, supplier) pairing with its causal features.

    Vectorised per supplier and per (supplier, material): cost is linear
    in returns x suppliers, so it stays fast on much larger panels.
    """
    rec = fact.dropna(subset=["receipt_date", "quantity_received"]).copy()
    rec = rec.sort_values("receipt_date")
    rec["short_qty"] = (rec["quantity_ordered"] - rec["quantity_received"]).clip(lower=0)
    rec["late_days_pos"] = rec["days_late_delivery"].clip(lower=0).fillna(0)
    rec["rejection_qty"] = rec["rejection_qty"].fillna(0)

    rts = returns[["return_id", "return_date", "material_id"]].copy()
    rts["material_id"] = rts["material_id"].astype(str)
    when = rts["return_date"].to_numpy("datetime64[ns]")
    window = np.timedelta64(config.MATERIAL_SHARE_WINDOW_DAYS, "D")

    frames = []
    for sup, g in rec.groupby("supplier_id"):
        d = g["receipt_date"].to_numpy("datetime64[ns]")
        n = _cum_at(d, np.arange(1, len(g) + 1, dtype=float), when)
        recv = _cum_at(d, g["quantity_received"].cumsum().to_numpy(), when)
        ordered = _cum_at(d, g["quantity_ordered"].cumsum().to_numpy(), when)
        frames.append(pd.DataFrame({
            "return_id": rts["return_id"].to_numpy(),
            "supplier_id": sup,
            "n_prior": n,
            "received_prior": recv,
            "rejection_rate": np.divide(
                _cum_at(d, g["rejection_qty"].cumsum().to_numpy(), when), recv,
                out=np.zeros_like(recv), where=recv > 0),
            "short_rate": np.divide(
                _cum_at(d, g["short_qty"].cumsum().to_numpy(), when), ordered,
                out=np.zeros_like(ordered), where=ordered > 0),
            "late_days": np.divide(
                _cum_at(d, g["late_days_pos"].cumsum().to_numpy(), when), n,
                out=np.zeros_like(n), where=n > 0),
        }))
    pairs = pd.concat(frames, ignore_index=True)
    pairs = pairs[pairs["n_prior"] > 0]

    # Material-specific features: recency and share of the recent window.
    rec["material_id"] = rec["material_id"].astype(str)
    mat_rows = []
    for (sup, mat), g in rec.groupby(["supplier_id", "material_id"]):
        sel = rts["material_id"].to_numpy() == mat
        if not sel.any():
            continue
        w = when[sel]
        d = g["receipt_date"].to_numpy("datetime64[ns]")
        cum = g["quantity_received"].cumsum().to_numpy()
        in_window = _cum_at(d, cum, w) - _cum_at(d, cum, w - window)
        last_idx = np.searchsorted(d, w, side="right") - 1
        days_since = np.where(
            last_idx >= 0,
            (w - d[np.clip(last_idx, 0, None)]) / np.timedelta64(1, "D"),
            np.inf)
        mat_rows.append(pd.DataFrame({
            "return_id": rts["return_id"].to_numpy()[sel],
            "supplier_id": sup,
            "mat_qty_window": in_window,
            "days_since_material": days_since,
        }))
    mat = pd.concat(mat_rows, ignore_index=True) if mat_rows else pd.DataFrame(
        columns=["return_id", "supplier_id", "mat_qty_window", "days_since_material"])

    pairs = pairs.merge(mat, on=["return_id", "supplier_id"], how="left")
    pairs["mat_qty_window"] = pairs["mat_qty_window"].fillna(0.0)
    pairs["days_since_material"] = pairs["days_since_material"].fillna(np.inf)
    total = pairs.groupby("return_id")["mat_qty_window"].transform("sum")
    pairs["material_share"] = np.where(total > 0, pairs["mat_qty_window"] / total, 0.0)
    pairs["recency"] = np.exp(-pairs["days_since_material"] / config.RECENCY_HALFLIFE_DAYS)

    reachable = pairs["return_id"].nunique()
    if reachable < len(rts):
        q.warn(STAGE, "Unattributable returns",
               f"{len(rts) - reachable} returns pre-date every delivery in the "
               f"data and cannot be attributed.",
               rows_affected=len(rts) - reachable, action="excluded from allocation")

    q.info(STAGE, "Candidates built",
           f"{len(pairs):,} (return, supplier) pairs across {reachable} returns "
           f"-- {len(pairs) / max(reachable, 1):.1f} candidate suppliers per return. "
           f"All features use only deliveries dated on or before the return.")
    return pairs.reset_index(drop=True)


def _add_prior(pairs: pd.DataFrame, labels: pd.Series,
               volume: pd.Series) -> pd.DataFrame:
    """Return propensity from a given set of labelled returns.

    Kept as a function of an explicit label set so cross-validation can
    rebuild it from each training fold alone -- the held-out returns'
    own labels never feed the feature that predicts them.
    """
    counts = labels.value_counts()
    a = config.PRIOR_SMOOTHING
    per_kt = (pairs["supplier_id"].map(counts).fillna(0) + a) / (
        pairs["supplier_id"].map(volume).fillna(0) / 1000 + a)
    return pairs.assign(return_prior=np.log(per_kt))


# ------------------------------------------------------------- evaluation

def _normalise(df: pd.DataFrame, col: str) -> pd.Series:
    total = df.groupby("return_id")[col].transform("sum")
    n = df.groupby("return_id")[col].transform("count")
    return np.where(total > 0, df[col] / total.where(total > 0, 1), 1.0 / n)


def _score(df: pd.DataFrame, prob: str, truth: pd.Series) -> dict:
    """Ranking accuracy and aggregate misallocation for one method."""
    d = df[["return_id", "supplier_id", prob]].copy()
    d["rank"] = d.groupby("return_id")[prob].rank(ascending=False, method="first")
    d = d.merge(truth.rename("truth"), left_on="return_id", right_index=True)
    hit = d[d["supplier_id"] == d["truth"]]
    n = len(truth)

    predicted = d.groupby("supplier_id")[prob].sum()
    actual = truth.value_counts()
    sups = predicted.index.union(actual.index)
    misalloc = float((predicted.reindex(sups, fill_value=0)
                      - actual.reindex(sups, fill_value=0)).abs().sum() / 2 / n)

    return {
        "top1": float((hit["rank"] == 1).sum() / n),
        "top3": float((hit["rank"] <= 3).sum() / n),
        "mrr": float((1 / hit["rank"]).sum() / n),
        "misallocation": misalloc,
        "n": int(n),
    }


def _one_hot(df: pd.DataFrame, col: str) -> pd.Series:
    """Turn a score into a hard pick -- how a rule-based baseline allocates."""
    out = pd.Series(0.0, index=df.index)
    out.loc[df.groupby("return_id")[col].idxmax()] = 1.0
    return out


def _new_model():
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=1000, random_state=config.RANDOM_SEED),
    )


def _cross_validate(train: pd.DataFrame, truth: pd.Series,
                    volume: pd.Series) -> tuple[dict, pd.DataFrame]:
    groups = train["return_id"]
    n_splits = min(config.CV_FOLDS, groups.nunique())
    oof = np.zeros(len(train))

    for tr, te in GroupKFold(n_splits=n_splits).split(train, train["label"], groups):
        fold_ids = train.iloc[tr]["return_id"].unique()
        fold = _add_prior(train, truth[truth.index.isin(fold_ids)], volume)
        model = _new_model()
        model.fit(fold.iloc[tr][FEATURES], fold.iloc[tr]["label"])
        oof[te] = model.predict_proba(fold.iloc[te][FEATURES])[:, 1]

    scored = train.assign(p_raw=oof)
    scored["p_learned"] = _normalise(scored, "p_raw")
    scored["p_exposure"] = _normalise(scored, "material_share")

    # Guard against a model that learns noise: blend it with plain exposure
    # (who supplied most of this material recently) and let held-out log
    # loss pick the mix. Where the learned signal is real the blend stays
    # at the model; where it is not, it falls back towards exposure.
    alpha = _best_alpha(scored, truth)
    scored["p_model"] = alpha * scored["p_learned"] + (1 - alpha) * scored["p_exposure"]
    metrics = _score(scored, "p_model", truth)
    metrics["cv_folds"] = n_splits
    metrics["blend_alpha"] = alpha
    metrics["learned_only"] = _score(scored, "p_learned", truth)
    return metrics, scored


def _best_alpha(scored: pd.DataFrame, truth: pd.Series) -> float:
    hit = scored["supplier_id"].to_numpy() == scored["return_id"].map(truth).to_numpy()

    def nll(a: float) -> float:
        p = a * scored["p_learned"] + (1 - a) * scored["p_exposure"]
        return float(-np.log(np.clip(p[hit], 1e-9, None)).mean())

    return min(config.BLEND_GRID, key=nll)


def _baselines(train: pd.DataFrame, truth: pd.Series) -> dict:
    b = train.copy()
    # The rule the problem statement describes: whoever delivered this
    # material most recently.
    b["ps_rule"] = _one_hot(b.assign(r=b["recency"]), "r")
    # Split by who supplied most of this material recently.
    b["by_volume"] = _normalise(b, "material_share")
    b["uniform"] = 1.0 / b.groupby("return_id")["supplier_id"].transform("count")
    return {
        "most_recent_batch": {
            "label": "Most recent batch of that material (the rule in the problem statement)",
            **_score(b, "ps_rule", truth)},
        "volume_share": {"label": "Split by share of that material supplied",
                         **_score(b, "by_volume", truth)},
        "uniform": {"label": "Equal split across all suppliers",
                    **_score(b, "uniform", truth)},
    }


def _calibration(scored: pd.DataFrame, truth: pd.Series) -> list[dict]:
    """Does '60% confident' mean right 60% of the time?"""
    top = (scored.sort_values("p_model", ascending=False)
           .groupby("return_id").first())
    top["hit"] = top["supplier_id"] == truth.reindex(top.index)
    bins = pd.cut(top["p_model"], [0, .1, .2, .3, .5, 1.0])
    out = []
    for b, g in top.groupby(bins, observed=True):
        out.append({"bin": f"{b.left:.0%}-{b.right:.0%}", "n": int(len(g)),
                    "predicted": float(g["p_model"].mean()),
                    "observed": float(g["hit"].mean())})
    return out


# -------------------------------------------------------------------- run

def run(returns: pd.DataFrame, fact: pd.DataFrame, q: Quality) -> Attribution:
    pairs = build_candidates(returns, fact, q)

    labelled = returns.dropna(subset=["supplier_id_traced"])
    truth_all = labelled.set_index("return_id")["supplier_id_traced"]
    volume = fact.groupby("supplier_id")["quantity_received"].sum()

    pairs = pairs.merge(returns[["return_id", "supplier_id_traced"]],
                        on="return_id", how="left")
    pairs["label"] = (pairs["supplier_id"] == pairs["supplier_id_traced"]).astype(int)

    train = pairs[pairs["return_id"].isin(truth_all.index)].copy()
    covered = train.groupby("return_id")["label"].max()
    train = train[train["return_id"].isin(covered[covered == 1].index)].reset_index(drop=True)
    truth = truth_all[truth_all.index.isin(train["return_id"])]

    q.count("returns_total", len(returns))
    q.count("returns_labelled", len(labelled))
    q.count("returns_blank", len(returns) - len(labelled))
    q.count("returns_trainable", len(truth))

    if len(truth) < config.MIN_LABELLED_FOR_TRAINING:
        return _fallback(pairs, returns, q, len(truth))

    metrics, scored = _cross_validate(train, truth, volume)
    baselines = _baselines(train, truth)
    calibration = _calibration(scored, truth)

    final = _add_prior(pairs, truth, volume)
    model = _new_model()
    model.fit(final.loc[final["return_id"].isin(truth.index), FEATURES],
              final.loc[final["return_id"].isin(truth.index), "label"])
    final["p_raw"] = model.predict_proba(final[FEATURES])[:, 1]
    alpha = metrics["blend_alpha"]
    final["model_probability"] = (alpha * _normalise(final, "p_raw")
                                  + (1 - alpha) * _normalise(final, "material_share"))

    coefs = {f: float(c) for f, c in zip(FEATURES, model[-1].coef_[0], strict=True)}

    if len(truth) < config.LOW_CONFIDENCE_LABELLED:
        q.warn(STAGE, "Small training set",
               f"Only {len(truth)} usable labelled returns. Attribution is "
               f"flagged low-confidence throughout.")

    best = min(baselines.values(), key=lambda b: b["misallocation"])
    q.info(STAGE, "Attribution model trained",
           f"Logistic regression on {len(train):,} pairs from {len(truth)} "
           f"labelled returns, {metrics['cv_folds']}-fold CV grouped by return; "
           f"blend weight on the model {metrics['blend_alpha']:.2f}. "
           f"Top-1 {metrics['top1']:.1%}, top-3 {metrics['top3']:.1%}; "
           f"{metrics['misallocation']:.1%} of return value misallocated in "
           f"aggregate vs {best['misallocation']:.1%} for the best baseline "
           f"and {baselines['most_recent_batch']['misallocation']:.1%} for the "
           f"problem statement's most-recent-batch rule.")

    return Attribution(
        pairs=_finalise_pairs(final, returns),
        per_return=_per_return(final, returns),
        metrics=metrics, baselines=baselines, coefficients=coefs,
        calibration=calibration, method="model")


def _fallback(pairs: pd.DataFrame, returns: pd.DataFrame, q: Quality,
              n_labelled: int) -> Attribution:
    """Not enough labels to learn from -- use the rule and say so."""
    q.warn(STAGE, "Model not trained",
           f"Only {n_labelled} labelled returns, below the minimum of "
           f"{config.MIN_LABELLED_FOR_TRAINING}. Falling back to the "
           f"most-recent-batch rule described in the problem statement. "
           f"No accuracy figure can be reported.",
           action="rule-based attribution")
    pairs = pairs.copy()
    pairs["model_probability"] = _one_hot(pairs.assign(r=pairs["recency"]), "r")
    return Attribution(pairs=_finalise_pairs(pairs, returns),
                       per_return=_per_return(pairs, returns),
                       metrics={"method": "most_recent_batch_rule"},
                       method="fallback")


def _finalise_pairs(pairs: pd.DataFrame, returns: pd.DataFrame) -> pd.DataFrame:
    """Recorded returns: 100% to the recorded supplier. Inferred: the model."""
    recorded = returns.dropna(subset=["supplier_id_traced"])
    hard = pd.DataFrame({
        "return_id": recorded["return_id"].to_numpy(),
        "supplier_id": recorded["supplier_id_traced"].to_numpy(),
        "probability": 1.0,
        "source": "recorded",
    })
    blank_ids = set(returns.loc[returns["supplier_id_traced"].isna(), "return_id"])
    soft = pairs.loc[pairs["return_id"].isin(blank_ids),
                     ["return_id", "supplier_id", "model_probability"]]
    soft = soft.rename(columns={"model_probability": "probability"})
    soft = soft[soft["probability"] > 0].assign(source="inferred")
    return pd.concat([hard, soft], ignore_index=True)


def _per_return(pairs: pd.DataFrame, returns: pd.DataFrame) -> pd.DataFrame:
    """One row per return: the supplier for the brief, and how sure we are."""
    ranked = pairs.sort_values(["return_id", "model_probability"],
                               ascending=[True, False])
    top3 = (ranked.groupby("return_id").head(3)
            .groupby("return_id")
            .apply(lambda g: [{"supplier_id": s, "p": round(float(p), 4)}
                              for s, p in zip(g["supplier_id"], g["model_probability"], strict=True)],
                   include_groups=False)
            .rename("top3"))
    first = ranked.groupby("return_id").first()[["supplier_id", "model_probability"]]

    out = returns.set_index("return_id").join(first).join(top3)
    out["source"] = np.where(out["supplier_id_traced"].notna(), "recorded", "inferred")
    out["supplier_attributed"] = out["supplier_id_traced"].fillna(out["supplier_id"])
    out["confidence"] = np.where(out["source"] == "recorded", 1.0,
                                 out["model_probability"])
    out["model_agrees"] = np.where(out["source"] == "recorded",
                                   out["supplier_id"] == out["supplier_id_traced"],
                                   np.nan)
    return out.drop(columns=["supplier_id"]).reset_index()

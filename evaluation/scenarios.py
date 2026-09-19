"""The evaluation scenarios: who is planted as bad, and how.

Plain data with no heavy imports, so the upload API can list the sample
datasets instantly; generate.py turns a scenario into CSVs.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Profile:
    """How one supplier behaves. Defaults are a normal, decent supplier."""
    short: float = 0.005        # mean fraction of ordered qty not delivered
    late: float = 1.5           # mean days late
    reject: float = 0.0         # mean fraction rejected at inspection
    defect: float = 1.0         # multiplier on the chance a batch triggers customer returns
    premium: float = 0.0        # systematic price premium, fraction
    # material -> overrides, for a supplier that is bad on one line only
    by_material: dict[str, dict] = field(default_factory=dict)
    # ISO date from which the behaviour above applies; before it, a normal
    # supplier. Models a supplier that deteriorated recently.
    bad_from: str | None = None


@dataclass
class Scenario:
    name: str
    title: str
    purpose: str
    n_suppliers: int
    n_orders: int
    bad: dict[str, Profile]            # supplier_id -> planted behaviour
    price_noise: float = 0.10          # sd of per-order price noise (fraction)
    label_share: float = 0.65          # share of returns with supplier recorded
    # If set, returns from planted offenders are recorded at this rate instead:
    # clerks write the supplier down more often when it's a known problem one.
    label_share_bad: float | None = None
    return_rate: float = 0.0045        # returns per MT received, for a normal supplier
    materials: int = 18
    index_materials: int = 6
    years: int = 3
    tiny_suppliers: dict[str, int] = field(default_factory=dict)  # id -> order count
    # Behaviour that is *not* a planted offence -- e.g. a tiny supplier whose
    # two orders happened to go badly. The pipeline should not condemn them.
    unlucky: dict[str, Profile] = field(default_factory=dict)
    messy: bool = False
    # "batch": a return comes from a specific delivery, weeks after it arrived.
    # "propensity": as observed in the assignment data -- the supplier is
    # drawn by volume x defect rate, but the returned material and date are
    # unrelated to any particular batch.
    returns: str = "batch"
    # "iso" or "indian": how a spreadsheet/Tally export would actually look.
    export: str = "iso"
    seed: int = 0


SCENARIOS = [
    Scenario(
        name="A_large_subtle", title="Larger panel, subtler offenders",
        purpose="Twice as many suppliers as the assignment, with five problem suppliers who are only "
                "a little worse than the rest -- harder to spot.",
        n_suppliers=70, n_orders=14_000, seed=11,
        bad={s: Profile(short=0.02, late=3.5, reject=0.012, defect=3.0, premium=0.02)
             for s in ["S004", "S017", "S029", "S041", "S063"]}),
    Scenario(
        name="B_failure_modes", title="Different failure modes",
        purpose="Each problem supplier fails in just one way -- one overcharges, one is always late, one "
                "sends poor material, one delivers short -- plus one that is bad on a single material.",
        n_suppliers=30, n_orders=6_000, price_noise=0.06, seed=22,
        bad={"S003": Profile(premium=0.08),
             "S007": Profile(late=6.5),
             "S011": Profile(reject=0.03, defect=4.0),
             "S015": Profile(short=0.04),
             "S020": Profile(by_material={"MS Pipes": {"short": 0.05, "reject": 0.04, "defect": 6.0}})}),
    Scenario(
        name="C_sparse_messy", title="Sparse and messy",
        purpose="A small, untidy dataset: most returns have no supplier recorded, some rows are "
                "duplicated or broken, and a tiny supplier had a couple of unlucky orders.",
        n_suppliers=25, n_orders=1_800, label_share=0.15, index_materials=2, messy=True, seed=33,
        tiny_suppliers={"S022": 3, "S023": 2, "S024": 4},
        unlucky={"S023": Profile(short=0.035, late=4.0)},
        bad={s: Profile(short=0.035, late=5.0, reject=0.025, defect=4.0, premium=0.03)
             for s in ["S002", "S009", "S016"]}),
    Scenario(
        name="D_control_no_offenders", title="Control: nobody is bad",
        purpose="Every supplier behaves the same. Nobody should be flagged -- any warning here is a "
                "false alarm.",
        n_suppliers=30, n_orders=5_000, seed=44, bad={}),
    Scenario(
        name="E_recent_deterioration", title="Suppliers that went bad recently",
        purpose="Two suppliers were fine for two years and went bad in the last one; two others were "
                "poor throughout. Does a recent collapse still get caught?",
        n_suppliers=35, n_orders=7_000, seed=55,
        bad={"S006": Profile(short=0.05, late=6.0, reject=0.04, defect=5.0, bad_from="2024-01-01"),
             "S019": Profile(short=0.05, late=6.0, reject=0.04, defect=5.0, bad_from="2024-01-01"),
             "S027": Profile(short=0.025, late=4.0, reject=0.015, defect=3.0),
             "S033": Profile(short=0.025, late=4.0, reject=0.015, defect=3.0)}),
    Scenario(
        name="F_assignment_mechanism_at_scale", title="Assignment-like returns, at scale",
        purpose="A large business -- 120 suppliers, 30,000 orders -- where returns behave the way they "
                "do in the assignment data.",
        n_suppliers=120, n_orders=30_000, returns="propensity", seed=66,
        bad={s: Profile(short=0.03, late=5.0, reject=0.02, defect=6.0)
             for s in ["S011", "S034", "S058", "S077", "S090", "S112"]}),
    Scenario(
        name="G_spreadsheet_export", title="Spreadsheet exports (Indian formats)",
        purpose="Files exactly as Excel or Tally export them in India: dates like 02/04/2023, amounts "
                "like 23,26,836.99, extra columns and stray spaces. Should give the same answer as "
                "clean files.",
        n_suppliers=30, n_orders=5_000, export="indian", seed=77,
        bad={s: Profile(short=0.035, late=5.0, reject=0.025, defect=4.0) for s in ["S005", "S014", "S026"]}),
    Scenario(
        name="H_small_but_bad", title="A small supplier that is genuinely bad",
        purpose="One supplier has only 12 orders, and every one of them goes badly; another small "
                "supplier with 10 orders is fine. Small suppliers are protected from bad luck -- does "
                "that protection hide one who really is bad?",
        n_suppliers=40, n_orders=6_000, seed=88,
        tiny_suppliers={"S038": 12, "S039": 10},
        bad={"S038": Profile(short=0.05, late=6.0, reject=0.04, defect=5.0),
             "S007": Profile(short=0.03, late=4.5, reject=0.02, defect=4.0),
             "S021": Profile(short=0.03, late=4.5, reject=0.02, defect=4.0)}),
    Scenario(
        name="I_biased_recording", title="Returns recorded selectively",
        purpose="Clerks write the supplier down on 90% of returns from known problem suppliers but only "
                "45% from the rest, so the untraced returns come mostly from good suppliers. Does the "
                "model over-blame the problem suppliers for them?",
        n_suppliers=30, n_orders=6_000, seed=99, label_share=0.45, label_share_bad=0.90,
        bad={s: Profile(short=0.03, late=4.5, reject=0.02, defect=5.0) for s in ["S004", "S012", "S023"]}),
]

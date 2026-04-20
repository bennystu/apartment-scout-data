"""
core/criteria.py — Single source of truth for all housing search criteria.

Edit THIS FILE to change search parameters. All pipeline stages read from CRITERIA.
No project imports — stdlib only.
"""
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType


@dataclass(frozen=True)
class HousingCriteria:
    # Location
    allowed_towns: tuple[str, ...]           # display names ("Auderghem", "Etterbeek", ...)
    postal_to_commune: MappingProxyType      # {"1160": "auderghem", ...}
    excluded_towns: tuple[str, ...]          # pre-filter at classify stage (lowercase)

    # Budget
    max_price_all_in: int                    # hard ceiling — rent + charges + bills
    bill_charges_included: int               # add for elec/internet when charges incluses
    bill_charges_separate: int               # add for elec/internet when listed separately
    bill_unspecified: int                    # assume total bills when charges unspecified

    # Size
    min_m2: int                              # hard floor — dismiss below this

    # Furnished
    require_furnished: bool                  # True → dismiss furnished==0

    # Move-in window
    window_start: date                       # earliest acceptable available date
    target_move_in: date                     # latest acceptable available date

    # Metro proximity
    max_walk_min: int                        # hard ceiling for UI filter default
    walk_close_min: int                      # threshold for full metro score boost

    # Bedrooms
    max_bedrooms: int                        # dismiss strictly greater than this

    # Domiciliation
    require_domiciliation: bool              # True → ask about it in inquiry

    # Price curve
    price_floor: int                         # score penalty below this
    price_sweet_spot: int                    # peak score at this price

    # Size scoring thresholds
    m2_neutral_max: int                      # below this → neutral (no bonus)
    m2_good_max: int                         # below this → small bonus; above → full bonus

    # Scoring weights + boosts (MappingProxyType — immutable at runtime)
    data_weights: MappingProxyType           # field → weight for data completeness score
    score_furnished_boost: float             # added when furnished==1
    score_furnished_penalty: float           # subtracted when furnished==0
    score_walk_close_boost: float            # added when walk_min <= walk_close_min
    score_walk_medium_boost: float           # added when walk_min <= max_walk_min
    score_vision_neutral: float              # added when vision_score is None
    score_vision_max: float                  # vision_score=5 maps to this

    def __post_init__(self):
        if self.window_start >= self.target_move_in:
            raise ValueError("window_start must be before target_move_in")
        if self.price_floor >= self.price_sweet_spot:
            raise ValueError("price_floor must be below price_sweet_spot")
        if self.price_sweet_spot > self.max_price_all_in:
            raise ValueError("price_sweet_spot must be ≤ max_price_all_in")
        if self.min_m2 < 0:
            raise ValueError("min_m2 must be non-negative")


# ── Single canonical instance — edit values here ──────────────────────────────

CRITERIA = HousingCriteria(
    # Location
    allowed_towns=(
        "Auderghem",
        "Etterbeek",
        "Watermael-Boitsfort",
        "Ixelles",
        "Woluwe-Saint-Pierre",
    ),
    postal_to_commune=MappingProxyType({
        "1160": "auderghem",
        "1040": "etterbeek",
        "1170": "watermaelboitsfort",
        "1050": "ixelles",
        "1150": "woluwesaintpierre",
    }),
    excluded_towns=(
        "schaerbeek", "anderlecht", "molenbeek", "laeken", "neder-over-heembeek",
        "forest", "saint-gilles", "uccle", "jette", "koekelberg",
        "evere", "ganshoren", "berchem-sainte-agathe", "woluwe-saint-lambert",
    ),

    # Budget
    max_price_all_in=1250,
    bill_charges_included=100,
    bill_charges_separate=100,
    bill_unspecified=250,

    # Size
    min_m2=35,

    # Furnished
    require_furnished=True,

    # Move-in window
    window_start=date(2026, 4, 15),
    target_move_in=date(2026, 6, 1),

    # Metro proximity
    max_walk_min=15,
    walk_close_min=10,

    # Bedrooms
    max_bedrooms=2,

    # Domiciliation
    require_domiciliation=True,

    # Price curve
    price_floor=600,
    price_sweet_spot=750,

    # Size scoring thresholds
    m2_neutral_max=55,
    m2_good_max=75,

    # Scoring weights + boosts
    data_weights=MappingProxyType({
        "price": 1.5,
        "contact": 0.5,
        "town": 1.0,
        "bedrooms": 1.0,
        "m2": 0.5,
        "furnished": 0.75,
        "available_date": 0.75,
    }),
    score_furnished_boost=1.5,
    score_furnished_penalty=0.3,
    score_walk_close_boost=0.5,
    score_walk_medium_boost=0.2,
    score_vision_neutral=0.6,
    score_vision_max=1.5,
)

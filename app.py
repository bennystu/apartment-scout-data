"""
Streamlit apartment scout UI.

Run: streamlit run app.py
"""

import json
import sys
import os
from pathlib import Path

# Ensure apartment-scout dir is on sys.path (needed when deployed on Streamlit Community Cloud)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests as _requests
import streamlit as st

# ---------------------------------------------------------------------------
# Data source — listings.json (Streamlit Cloud) or local SQLite
# ---------------------------------------------------------------------------
_HERE = Path(os.path.dirname(os.path.abspath(__file__)))
_LISTINGS_JSON = _HERE / "listings.json"
_USE_JSON = _LISTINGS_JSON.exists() and not (_HERE / "apartment_scout.db").exists()

_GH_REPO  = "bennystu/apartment-scout-data"
_GH_PATH  = "listings.json"
_GH_API   = f"https://api.github.com/repos/{_GH_REPO}/contents/{_GH_PATH}"

if _USE_JSON:
    def _gh_token():
        try:
            return st.secrets.get("GITHUB_TOKEN", "")
        except Exception:
            return os.environ.get("GITHUB_TOKEN", "")

    def _commit_listings(listings: list):
        """Write updated listings.json back to GitHub. Triggers Streamlit redeploy."""
        token = _gh_token()
        if not token:
            return
        import base64
        content = base64.b64encode(
            json.dumps(listings, indent=2, ensure_ascii=False).encode()
        ).decode()
        # Get current SHA (required for update)
        r = _requests.get(_GH_API, headers={"Authorization": f"token {token}"}, timeout=5)
        sha = r.json().get("sha", "")
        _requests.put(
            _GH_API,
            headers={"Authorization": f"token {token}"},
            json={"message": "update listing status", "content": content, "sha": sha},
            timeout=10,
        )

    _ALL_LISTINGS = json.loads(_LISTINGS_JSON.read_text())

    def get_listings(max_price=None, min_vision_score=None, furnished=None,
                     exclude_status=None, sources=None):
        results = _ALL_LISTINGS
        if max_price:
            results = [l for l in results if not l.get("price") or l["price"] <= max_price]
        if min_vision_score is not None:
            results = [l for l in results if not l.get("vision_score") or l["vision_score"] >= min_vision_score]
        if furnished is not None:
            results = [l for l in results if l.get("furnished") == (1 if furnished else 0)]
        if exclude_status:
            results = [l for l in results if l.get("status") not in exclude_status]
        return results

    def update_status(listing_id, status):
        for l in _ALL_LISTINGS:
            if l["id"] == listing_id:
                l["status"] = status
                break
        _commit_listings(_ALL_LISTINGS)  # persists to GitHub, triggers redeploy

    def init_db():
        pass

else:
    from db import init_db, get_listings, update_status
    init_db()

st.set_page_config(
    page_title="Apartment Scout",
    page_icon="🏠",
    layout="wide",
)

st.title("🏠 Apartment Scout")
st.caption("Listings near AGC Glass Europe — Brussels side")

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")

    st.subheader("Price")
    price_range = st.slider("€/mo", 400, 1300, (400, 1100), step=50)

    st.subheader("Location")
    KNOWN_TOWNS = ["Rixensart", "Genval", "La Hulpe", "Court-Saint-Étienne", "Profondsart", "Waterloo", "Braine-l'Alleud"]
    town_filters = {t: st.checkbox(t, value=True) for t in KNOWN_TOWNS}
    other_towns = st.checkbox("Other / unknown", value=True)

    min_score = st.slider(
        "Min photo score", 1.0, 5.0, 2.5, step=0.5,
        help="1 = poor, 5 = excellent. Listings without photos are always shown."
    )

    furnished_filter = st.radio(
        "Furnished",
        ["All", "Furnished only", "Unfurnished only"],
    )

    st.subheader("Available from")
    avail_april = st.checkbox("April 2026", value=True)
    avail_may = st.checkbox("May 2026", value=True)
    avail_june = st.checkbox("June 2026", value=True)
    avail_unknown = st.checkbox("No start date listed", value=True)

    hide_dismissed = st.checkbox("Hide dismissed", value=True)

    st.divider()
    if st.button("🔄 Refresh listings"):
        st.rerun()

# ---------------------------------------------------------------------------
# Load and filter
# ---------------------------------------------------------------------------
furnished_arg = None
if furnished_filter == "Furnished only":
    furnished_arg = True
elif furnished_filter == "Unfurnished only":
    furnished_arg = False

exclude_status = ["dismissed"] if hide_dismissed else []

listings = get_listings(
    max_price=price_range[1],
    min_vision_score=min_score,
    furnished=furnished_arg,
    exclude_status=exclude_status,
)

# Price minimum
listings = [l for l in listings if not l.get("price") or l["price"] >= price_range[0]]

# Location filter
def _town_matches(listing):
    town = (listing.get("town") or "").strip()
    for known in KNOWN_TOWNS:
        if known.lower() in town.lower():
            return town_filters[known]
    return other_towns  # no match → "Other"

listings = [l for l in listings if _town_matches(l)]

# Availability filter
def _avail_matches(listing):
    d = listing.get("available_date")
    if not d:
        return avail_unknown
    if d.startswith("2026-04"):
        return avail_april
    if d.startswith("2026-05"):
        return avail_may
    if d.startswith("2026-06"):
        return avail_june
    if d < "2026-04-01":
        return False   # in the past — never show
    if d > "2026-06-30":
        return False   # too far out — never show
    return avail_unknown

listings = [l for l in listings if _avail_matches(l)]

# Sort by listing_score descending (nulls last)
listings.sort(key=lambda l: l.get("listing_score") or 0, reverse=True)

# ---------------------------------------------------------------------------
# Header stats
# ---------------------------------------------------------------------------
total = len(listings)
new_count = sum(1 for l in listings if l["status"] == "new")
col1, col2, col3 = st.columns(3)
col1.metric("Total listings", total)
col2.metric("New", new_count)
col3.metric("Favorites", sum(1 for l in listings if l["status"] == "favorite"))

if not listings:
    st.info("No listings match your filters. Try adjusting the sliders, or run `python run.py` to scrape new ones.")
    st.stop()

st.divider()

# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------
PAGE_SIZE = 10
total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

# Reset to page 0 whenever filters change
filter_key = f"{price_range}_{min_score}_{furnished_filter}_{hide_dismissed}_{avail_april}_{avail_may}_{avail_june}_{avail_unknown}_{''.join(str(v) for v in town_filters.values())}_{other_towns}"
if st.session_state.get("filter_key") != filter_key:
    st.session_state.page = 0
    st.session_state.filter_key = filter_key

col_prev, col_info, col_next = st.columns([1, 2, 1])
with col_prev:
    if st.button("← Prev") and st.session_state.page > 0:
        st.session_state.page -= 1
with col_info:
    st.markdown(
        f"<div style='text-align:center;padding-top:6px'>Page {st.session_state.page + 1} of {total_pages}</div>",
        unsafe_allow_html=True,
    )
with col_next:
    if st.button("Next →") and st.session_state.page < total_pages - 1:
        st.session_state.page += 1

page_listings = listings[st.session_state.page * PAGE_SIZE:(st.session_state.page + 1) * PAGE_SIZE]

# ---------------------------------------------------------------------------
# Listing cards
# ---------------------------------------------------------------------------
for listing in page_listings:
    is_new = listing["status"] == "new"
    is_fav = listing["status"] == "favorite"

    # Card header
    badge = "🆕 " if is_new else ("⭐ " if is_fav else "")
    price_str = f"€{listing['price']}/mo" if listing["price"] else "Price unknown"
    town_str = listing.get("town") or "Location unknown"
    dist_str = f" · {listing['distance_km']}km from AGC" if listing.get("distance_km") else ""
    furnished_str = ""
    if listing.get("furnished") == 1:
        furnished_str = " · Furnished"
    elif listing.get("furnished") == 0:
        furnished_str = " · Unfurnished"

    score_str = f" · ⭐ {listing['vision_score']:.1f}/5" if listing.get("vision_score") else ""
    avail_str = f" · 📅 {listing['available_from']}" if listing.get("available_from") else ""

    with st.expander(
        f"{badge}{price_str} — {town_str}{dist_str}{furnished_str}{avail_str}{score_str}",
        expanded=False,
    ):
        # Photos row
        photos = listing.get("photos") or []
        if photos:
            photo_cols = st.columns(2)
            for i, url in enumerate(photos[:2]):
                with photo_cols[i]:
                    try:
                        st.image(url, use_container_width=True)
                    except Exception:
                        st.caption("(photo unavailable)")

        # Details grid
        detail_col, action_col = st.columns([3, 1])

        with detail_col:
            if listing.get("vision_notes"):
                st.markdown(f"**Vision:** {listing['vision_notes']}")

            details = []
            if listing.get("m2"):
                details.append(f"**Size:** {listing['m2']} m²")
            if listing.get("bedrooms"):
                details.append(f"**Bedrooms:** {listing['bedrooms']}")
            if listing.get("available_from"):
                details.append(f"**Available:** {listing['available_from']}")
            if listing.get("contact"):
                details.append(f"**Contact:** {listing['contact']}")
            if listing.get("source"):
                details.append(f"**Source:** {listing['source'].replace('_', ' ')}")
            if listing.get("first_seen"):
                details.append(f"**Seen:** {listing['first_seen'][:10]}")

            if details:
                st.markdown("  \n".join(details))

            if listing.get("post_text"):
                with st.expander("Original post"):
                    st.text(listing["post_text"][:800])

            if listing.get("source_url"):
                st.markdown(f"[View original listing →]({listing['source_url']})")

        with action_col:
            lid = listing["id"]

            if listing["status"] != "favorite":
                if st.button("⭐ Favourite", key=f"fav_{lid}"):
                    update_status(lid, "favorite")
                    st.rerun()
            else:
                if st.button("★ Unfavourite", key=f"unfav_{lid}"):
                    update_status(lid, "new")
                    st.rerun()

            if listing["status"] != "dismissed":
                if st.button("✗ Dismiss", key=f"dis_{lid}"):
                    update_status(lid, "dismissed")
                    st.rerun()

        # French inquiry message
        if listing.get("inquiry_message"):
            st.divider()
            st.markdown("**📋 Message to copy:**")
            st.code(listing["inquiry_message"], language=None)

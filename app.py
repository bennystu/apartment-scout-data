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

    def save_feedback(listing_id, reason):
        for l in _ALL_LISTINGS:
            if l["id"] == listing_id:
                l["dismiss_reason"] = reason
                break

    def init_db():
        pass

else:
    from db import init_db, get_listings, update_status, save_feedback
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

    st.subheader("Bedrooms")
    bed_any = st.checkbox("Any", value=True)
    bed_studio = st.checkbox("Studio", value=True)
    bed_1 = st.checkbox("1 bed", value=True)
    bed_2 = st.checkbox("2 bed", value=True)

    st.subheader("Location")
    max_distance_km = st.slider("Max distance from AGC (km)", 1, 35, 10, step=1)
    KNOWN_TOWNS = ["Rixensart", "Genval", "La Hulpe", "Court-Saint-Étienne", "Profondsart"]
    town_filters = {t: st.checkbox(t, value=True) for t in KNOWN_TOWNS}
    other_towns = st.checkbox("Other / unknown", value=True)

    st.subheader("Train line")
    train_l161 = st.checkbox("L161 → Bruxelles-Luxembourg", value=True)
    train_l124 = st.checkbox("L124 → Bruxelles-Midi", value=True)
    train_none = st.checkbox("No train nearby", value=True)

    min_score = st.slider(
        "Min photo score", 1.0, 5.0, 1.0, step=0.5,
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
    # July+ always hidden — too far out

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

# Bedrooms filter
def _beds_matches(listing):
    if bed_any:
        return True
    beds = listing.get("bedrooms")
    if beds is None:
        return True  # unknown — always show
    if beds == 0:
        return bed_studio
    if beds == 1:
        return bed_1
    if beds == 2:
        return bed_2
    return False

listings = [l for l in listings if _beds_matches(l)]

# Distance filter
listings = [l for l in listings if (l.get("distance_km") or 0) <= max_distance_km or not l.get("distance_km")]

# Location filter
def _town_matches(listing):
    town = (listing.get("town") or "").strip()
    for known in KNOWN_TOWNS:
        if known.lower() in town.lower():
            return town_filters[known]
    return other_towns  # no match → "Other"

listings = [l for l in listings if _town_matches(l)]

# Train line filter
def _train_matches(listing):
    info = listing.get("train_info") or ""
    if "L161" in info:
        return train_l161
    if "L124" in info:
        return train_l124
    return train_none

listings = [l for l in listings if _train_matches(l)]

# Availability filter
def _avail_matches(listing):
    d = listing.get("available_date")
    if not d:
        return avail_unknown
    if d < "2026-04-01":
        return avail_unknown  # past date = available now/immediately
    if d.startswith("2026-04"):
        return avail_april
    if d.startswith("2026-05"):
        return avail_may
    if d.startswith("2026-06"):
        return avail_june
    if d > "2026-06-30":
        return False   # July+ — too far out, always hide
    return avail_unknown

listings = [l for l in listings if _avail_matches(l)]

# Sort by match_score descending (nulls last)
listings.sort(key=lambda l: l.get("match_score") or 0, reverse=True)

# ---------------------------------------------------------------------------
# Header stats
# ---------------------------------------------------------------------------
total = len(listings)
new_count = sum(1 for l in listings if l["status"] == "new")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total", total)
col2.metric("New", new_count)
col3.metric("Favourites", sum(1 for l in listings if l["status"] == "favorite"))
col4.metric("Contacted", sum(1 for l in listings if l["status"] == "contacted"))

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
filter_key = f"{price_range}_{min_score}_{furnished_filter}_{hide_dismissed}_{avail_april}_{avail_may}_{avail_june}_{avail_unknown}_{''.join(str(v) for v in town_filters.values())}_{other_towns}_{bed_any}_{bed_studio}_{bed_1}_{bed_2}_{train_l161}_{train_l124}_{train_none}_{max_distance_km}"
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
    dist_str = f" · {listing['distance_km']}km AGC" if listing.get("distance_km") else ""
    dist_bxl_str = f" · {listing['distance_bxl_km']}km BXL" if listing.get("distance_bxl_km") else ""
    train_str = f" · 🚆 {listing['train_info']}" if listing.get("train_info") else ""
    furnished_str = ""
    if listing.get("furnished") == 1:
        furnished_str = " · Furnished"
    elif listing.get("furnished") == 0:
        furnished_str = " · Unfurnished"

    m2_str = f" · {listing['m2']}m²" if listing.get("m2") else ""
    beds_str = f" · {listing['bedrooms']}bed" if listing.get("bedrooms") else (" · studio" if listing.get("bedrooms") == 0 else "")
    match_str = f" · match {listing['match_score']:.1f}/10" if listing.get("match_score") is not None else ""
    data_str = f" · data {listing['data_score']}/7" if listing.get("data_score") is not None else ""
    score_str = f" · 📷 {listing['vision_score']:.1f}/5" if listing.get("vision_score") else ""
    score_str = match_str + data_str + score_str
    avail_str = f" · 📅 {listing['available_from']}" if listing.get("available_from") else ""

    with st.expander(
        f"{badge}{price_str} — {town_str}{dist_str}{dist_bxl_str}{train_str}{beds_str}{m2_str}{furnished_str}{avail_str}{score_str}",
        expanded=False,
    ):
        # Photos grid — all photos, 3 per row
        photos = listing.get("photos") or []
        if photos:
            cols_per_row = 3
            for row_start in range(0, len(photos), cols_per_row):
                row_photos = photos[row_start:row_start + cols_per_row]
                photo_cols = st.columns(len(row_photos))
                for i, url in enumerate(row_photos):
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
            if listing.get("contract_length"):
                labels = {"short": "Short-stay", "1year": "1-year lease", "3year": "3-year lease"}
                details.append(f"**Contract:** {labels.get(listing['contract_length'], listing['contract_length'])}")
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

            if listing["status"] != "contacted":
                if st.button("📨 Contacted", key=f"con_{lid}"):
                    update_status(lid, "contacted")
                    st.rerun()
            else:
                st.markdown("📨 *Contacted*")

            if listing["status"] != "dismissed":
                if st.button("✗ Dismiss", key=f"dis_{lid}"):
                    st.session_state[f"dismissing_{lid}"] = True
                if st.session_state.get(f"dismissing_{lid}"):
                    QUICK_REASONS = [
                        "Too far from train station",
                        "Ground floor",
                        "Too dark / poor lighting",
                        "Rooms look too small",
                        "Poor condition",
                        "Too noisy area",
                        "Other",
                    ]
                    reason = st.selectbox(
                        "Why?", QUICK_REASONS, key=f"reason_sel_{lid}"
                    )
                    if reason == "Other":
                        reason = st.text_input(
                            "Describe reason", key=f"reason_txt_{lid}"
                        )
                    col_ok, col_cancel = st.columns(2)
                    with col_ok:
                        if st.button("Confirm", key=f"dis_ok_{lid}"):
                            if reason:
                                save_feedback(lid, reason)
                            update_status(lid, "dismissed")
                            st.session_state.pop(f"dismissing_{lid}", None)
                            st.rerun()
                    with col_cancel:
                        if st.button("Cancel", key=f"dis_cancel_{lid}"):
                            st.session_state.pop(f"dismissing_{lid}", None)
                            st.rerun()

        # French inquiry message
        if listing.get("inquiry_message"):
            st.divider()
            st.markdown("**📋 Message to copy:**")
            st.code(listing["inquiry_message"], language=None)

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

from core.criteria import CRITERIA

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
st.caption("Brussels furnished apartments — Auderghem · Etterbeek · Ixelles · Watermael-Boitsfort · Woluwe-Saint-Pierre")

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
    max_walk_min = st.slider("Max walk to metro Line 5 (min)", 1, 30, CRITERIA.max_walk_min, step=1)
    KNOWN_TOWNS = list(CRITERIA.allowed_towns)
    town_filters = {t: st.checkbox(t, value=True) for t in KNOWN_TOWNS}
    other_towns = st.checkbox("Other / unknown", value=True)

    min_score = st.slider(
        "Min photo score", 1.0, 5.0, 1.0, step=0.5,
        help="1 = poor, 5 = excellent. Listings without photos are always shown."
    )

    min_match = st.slider(
        "Min overall score", 0.0, 10.0, 0.0, step=0.5,
        help="0–10 match score. Listings without a score are always shown."
    )

    furnished_filter = st.radio(
        "Furnished",
        ["All", "Furnished only", "Unfurnished only"],
        index=1,
    )

    st.subheader("Available from")
    avail_april = st.checkbox("April 2026", value=True)
    avail_may = st.checkbox("May 2026", value=True)
    avail_june = st.checkbox("June 2026", value=True)
    avail_unknown = st.checkbox("No start date listed", value=True)
    # July+ always hidden — too far out

    status_filter = st.selectbox(
        "Status",
        ["All", "To review", "Shortlisted", "Contacted"],
        help="All hides dismissed listings. Use individual status views to focus.",
    )

    st.subheader("Latest run")
    new_only = st.checkbox("🆕 Latest batch only", value=False,
                           help="Show only listings added in the most recent scrape")

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

listings = get_listings(
    max_price=price_range[1],
    min_vision_score=min_score,
    furnished=furnished_arg,
    exclude_status=["dismissed"],
)

if status_filter == "To review":
    listings = [l for l in listings if l["status"] == "new"]
elif status_filter == "Shortlisted":
    listings = [l for l in listings if l["status"] == "favorite"]
elif status_filter == "Contacted":
    listings = [l for l in listings if l["status"] == "contacted"]
# "All" — dismissed already excluded above

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

# Metro walk filter
listings = [l for l in listings if (l.get("walk_min") or 0) <= max_walk_min or not l.get("walk_min")]

# Location filter
def _town_matches(listing):
    town = (listing.get("town") or "").strip()
    for known in KNOWN_TOWNS:
        if known.lower() in town.lower():
            return town_filters[known]
    return other_towns  # no match → "Other"

listings = [l for l in listings if _town_matches(l)]

# Availability filter
_LATE_MONTHS = ("juil", "août", "aout", "jul", "aug", "sept", "octo", "nove", "déce", "dece")

def _avail_matches(listing):
    d = listing.get("available_date")
    # No extracted date — check free-text available_from for late-month signals
    if not d:
        avail_from = (listing.get("available_from") or "").lower()
        if any(m in avail_from for m in _LATE_MONTHS):
            return False  # clearly July+ — hide even without a parsed date
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

# Latest batch filter — show only listings added in the most recent scrape
if new_only:
    latest_date = max(
        (l.get("first_seen") or "")[:10] for l in listings if l.get("first_seen")
    ) if listings else ""
    if latest_date:
        listings = [l for l in listings if (l.get("first_seen") or "").startswith(latest_date)]

# Match score filter (nulls always shown)
if min_match > 0:
    listings = [l for l in listings if l.get("match_score") is None or l["match_score"] >= min_match]

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
filter_key = f"{price_range}_{min_score}_{min_match}_{furnished_filter}_{status_filter}_{avail_april}_{avail_may}_{avail_june}_{avail_unknown}_{''.join(str(v) for v in town_filters.values())}_{other_towns}_{bed_any}_{bed_studio}_{bed_1}_{bed_2}_{max_walk_min}_{new_only}"
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
    price_str = f"€{listing['price']}/mo" if listing["price"] else "⚠ no price"
    town_str = listing.get("town") or "location unknown"
    metro_str = f" · 🚇 {listing['walk_min']}min to {listing['nearest_metro']}" if listing.get("walk_min") and listing.get("nearest_metro") else (" · 🚇 walk?" if not listing.get("walk_min") else "")
    furnished_str = ""
    if listing.get("furnished") == 1:
        furnished_str = " · Furnished"
    elif listing.get("furnished") == 0:
        furnished_str = " · Unfurnished"

    m2_str = f" · {listing['m2']}m²" if listing.get("m2") else ""
    beds_str = f" · {listing['bedrooms']}bed" if listing.get("bedrooms") else (" · studio" if listing.get("bedrooms") == 0 else "")
    score_str = f" · {listing['match_score']:.1f}/10" if listing.get("match_score") is not None else ""
    avail_str = f" · 📅 {listing['available_from']}" if listing.get("available_from") else ""

    with st.expander(
        f"{badge}{price_str} — {town_str}{metro_str}{beds_str}{m2_str}{furnished_str}{avail_str}{score_str}",
        expanded=False,
    ):
        # Photos grid — all photos, 3 per row
        photos = listing.get("photos") or []
        if photos:
            for url in photos:
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
                        "Too far from metro",
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

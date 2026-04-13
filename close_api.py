"""
Close CRM API wrapper with Streamlit caching.
Data refreshes automatically every 30 minutes, or on-demand via clear_cache().
"""
import requests
from requests.auth import HTTPBasicAuth
from datetime import date
import streamlit as st

BASE = "https://api.close.com/api/v1"


def _auth(key):
    return HTTPBasicAuth(key, "")


def _paginate(key, path, params=None):
    """Fetch all pages from a Close CRM endpoint."""
    params = dict(params or {})
    params.setdefault("_limit", 100)
    params["_skip"] = 0
    results = []
    while True:
        try:
            r = requests.get(
                f"{BASE}/{path}/",
                auth=_auth(key),
                params=params,
                timeout=15,
            )
        except Exception as e:
            return [], f"Connection error: {e}"
        if r.status_code == 401:
            return [], "Invalid API key"
        if r.status_code != 200:
            return [], f"API error {r.status_code}"
        d = r.json()
        results.extend(d.get("data", []))
        if not d.get("has_more", False):
            break
        params["_skip"] += params["_limit"]
    return results, None


def test_connection(api_key):
    try:
        r = requests.get(f"{BASE}/me/", auth=_auth(api_key), timeout=5)
        if r.status_code == 200:
            u = r.json()
            name = f"{u.get('first_name','')} {u.get('last_name','')}".strip()
            return True, name, None
        return False, None, f"Status {r.status_code}"
    except Exception as e:
        return False, None, str(e)


# ── Existing (used by personal app) ───────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def get_users(api_key):
    data, err = _paginate(api_key, "user")
    return data, err


@st.cache_data(ttl=1800, show_spinner=False)
def get_won_this_month(api_key):
    month_start = date.today().replace(day=1).isoformat()
    data, err = _paginate(api_key, "opportunity", {"status_type": "won"})
    filtered = [o for o in data if (o.get("date_won") or "") >= month_start]
    return filtered, err


@st.cache_data(ttl=1800, show_spinner=False)
def get_active_pipeline(api_key):
    data, err = _paginate(api_key, "opportunity", {"status_type": "active"})
    return data, err


@st.cache_data(ttl=1800, show_spinner=False)
def get_calls_this_month(api_key):
    month_start = date.today().replace(day=1).isoformat() + "T00:00:00.000000"
    data, err = _paginate(api_key, "activity/call", {"date_created__gte": month_start})
    return data, err


@st.cache_data(ttl=1800, show_spinner=False)
def get_leads(api_key):
    data, err = _paginate(api_key, "lead")
    return data, err


# ── Date-range versions (for monthly toggle) ───────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def get_won_in_range(api_key, month_start, month_end):
    """Won opportunities within a date range (month_start/end as ISO date strings)."""
    data, err = _paginate(api_key, "opportunity", {"status_type": "won"})
    filtered = [o for o in data
                if month_start <= (o.get("date_won") or "") < month_end]
    return filtered, err


@st.cache_data(ttl=1800, show_spinner=False)
def get_calls_in_range(api_key, month_start, month_end):
    """Calls within a date range."""
    data, err = _paginate(api_key, "activity/call", {
        "date_created__gte": month_start + "T00:00:00.000000",
        "date_created__lt":  month_end   + "T00:00:00.000000",
    })
    return data, err


# ── Custom activities (RPS) ────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def get_custom_activity_types(api_key):
    """
    Get all custom activity type definitions for this account.
    Falls back to discovering type IDs from recent activity instances
    if the official type-definition endpoint isn't accessible.
    """
    data, err = _paginate(api_key, "custom_activity_type")
    if not err:
        return data, None

    # Fallback: sample recent custom activity instances to discover type IDs,
    # then look up each type definition individually to get its name.
    sample, err2 = _paginate(api_key, "activity/custom", {"_limit": 100})
    if err2:
        return [], err  # return the original error

    # Collect unique type IDs from instances
    type_ids = []
    seen = set()
    for a in sample:
        tid = a.get("custom_activity_type_id")
        if tid and tid not in seen:
            seen.add(tid)
            type_ids.append(tid)

    # Try individual type-definition lookups to get names
    types_result = []
    for tid in type_ids:
        r = requests.get(
            f"{BASE}/custom_activity_type/{tid}/",
            auth=_auth(api_key),
            timeout=15,
        )
        if r.status_code == 200:
            types_result.append(r.json())
        else:
            types_result.append({"id": tid, "name": ""})

    return types_result, None


@st.cache_data(ttl=1800, show_spinner=False)
def get_custom_activities_in_range(api_key, type_id, month_start, month_end):
    """Custom activities of a specific type within a date range."""
    # Try type_id in the URL path first (preferred Close CRM format)
    data, err = _paginate(api_key, f"activity/custom/{type_id}", {
        "date_created__gte": month_start + "T00:00:00.000000",
        "date_created__lt":  month_end   + "T00:00:00.000000",
    })
    if not err:
        return data, None
    # Fallback: type_id as query parameter
    data, err = _paginate(api_key, "activity/custom", {
        "custom_activity_type_id": type_id,
        "date_created__gte": month_start + "T00:00:00.000000",
        "date_created__lt":  month_end   + "T00:00:00.000000",
    })
    return data, err


# ── Lead status change activities (Vibe) ──────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def get_leads_with_status(api_key, status_label):
    """Fetch leads currently in a given status."""
    data, err = _paginate(api_key, "lead", {
        "status_label": status_label,
        "_limit": 5,
    })
    return data, err


@st.cache_data(ttl=1800, show_spinner=False)
def get_meetings_in_range(api_key, month_start, month_end):
    """
    Fetch implementation call meetings where the call date (starts_at) falls
    within the selected month. Only counts first-ever implementation calls —
    leads who had a prior implementation call in the previous 12 months are
    excluded as follow-ups. Deduplicates by lead so rebooks count once.
    """
    import datetime
    dt_start = datetime.date.fromisoformat(month_start)
    window_start = (dt_start - datetime.timedelta(days=90)).isoformat()
    history_start = (dt_start - datetime.timedelta(days=365)).isoformat()

    # Fetch meetings from 90-day window (captures advance bookings)
    data, err = _paginate(api_key, "activity/meeting", {
        "date_created__gte": window_start + "T00:00:00.000000",
        "date_created__lt":  month_end   + "T00:00:00.000000",
    })
    if err:
        return [], err

    filtered = []
    for m in data:
        title = (m.get("title") or "").strip().lower()
        if "implementation call" not in title:
            continue
        if title.startswith("canceled:"):
            continue
        if title.startswith("updated -"):
            continue
        starts_at = (m.get("starts_at") or "")[:10]
        if not (month_start <= starts_at < month_end):
            continue
        filtered.append(m)

    # Deduplicate by lead within the month — keep earliest booking
    seen_leads = set()
    deduped = []
    for m in sorted(filtered, key=lambda x: x.get("date_created", "")):
        lid = m.get("lead_id")
        if lid and lid in seen_leads:
            continue
        if lid:
            seen_leads.add(lid)
        deduped.append(m)

    if not deduped:
        return deduped, None

    # Fetch prior 12 months of implementation calls to identify follow-ups
    history_data, _ = _paginate(api_key, "activity/meeting", {
        "date_created__gte": history_start + "T00:00:00.000000",
        "date_created__lt":  window_start  + "T00:00:00.000000",
    })

    prior_lead_ids = set()

    # Check the dedicated history window (months 4–12 before selected month)
    for m in history_data:
        title = (m.get("title") or "").strip().lower()
        if "implementation call" not in title:
            continue
        if title.startswith("canceled:") or title.startswith("updated -"):
            continue
        lid = m.get("lead_id")
        if lid:
            prior_lead_ids.add(lid)

    # Also check the 90-day window data for calls whose call date was BEFORE this month
    # (covers the gap between window_start and month_start)
    for m in data:
        starts_at = (m.get("starts_at") or "")[:10]
        if starts_at >= month_start:
            continue  # April call — not prior history
        title = (m.get("title") or "").strip().lower()
        if "implementation call" not in title:
            continue
        if title.startswith("canceled:") or title.startswith("updated -"):
            continue
        lid = m.get("lead_id")
        if lid:
            prior_lead_ids.add(lid)

    # Keep only leads whose first implementation call is this month
    first_calls = [m for m in deduped if m.get("lead_id") not in prior_lead_ids]
    return first_calls, None


@st.cache_data(ttl=1800, show_spinner=False)
def get_lead_status_changes_in_range(api_key, month_start, month_end):
    """
    Lead status change activity events within a date range.
    Each record has new_status_label showing what status the lead moved TO.
    """
    data, err = _paginate(api_key, "activity/status_change/lead", {
        "date_created__gte": month_start + "T00:00:00.000000",
        "date_created__lt":  month_end   + "T00:00:00.000000",
    })
    return data, err


def clear_cache():
    get_users.clear()
    get_won_this_month.clear()
    get_active_pipeline.clear()
    get_calls_this_month.clear()
    get_leads.clear()
    get_won_in_range.clear()
    get_calls_in_range.clear()
    get_custom_activity_types.clear()
    get_custom_activities_in_range.clear()
    get_meetings_in_range.clear()
    get_lead_status_changes_in_range.clear()

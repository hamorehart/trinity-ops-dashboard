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
    """Returns (success: bool, display_name: str, error: str)"""
    try:
        r = requests.get(f"{BASE}/me/", auth=_auth(api_key), timeout=5)
        if r.status_code == 200:
            u = r.json()
            name = f"{u.get('first_name','')} {u.get('last_name','')}".strip()
            return True, name, None
        return False, None, f"Status {r.status_code}"
    except Exception as e:
        return False, None, str(e)


@st.cache_data(ttl=1800, show_spinner=False)
def get_users(api_key):
    data, err = _paginate(api_key, "user")
    return data, err


@st.cache_data(ttl=1800, show_spinner=False)
def get_won_this_month(api_key):
    month_start = date.today().replace(day=1).isoformat()
    data, err = _paginate(api_key, "opportunity", {"status_type": "won"})
    # Filter client-side in case the API ignores the date param
    filtered = []
    for o in data:
        dw = o.get("date_won") or ""
        if dw >= month_start:
            filtered.append(o)
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


def clear_cache():
    get_users.clear()
    get_won_this_month.clear()
    get_active_pipeline.clear()
    get_calls_this_month.clear()
    get_leads.clear()

import streamlit as st
import bcrypt
import json
import pandas as pd
from datetime import date, datetime
import close_api

# ── Auth ───────────────────────────────────────────────────────────────────────

USERS = {
    "simon@trinityops.io":  "Simon",
    "hannah@trinityops.io": "Hannah",
    "josh@trinityops.io":   "Josh",
}

# Pre-hashed passwords stored in st.secrets (never in code)
def _get_hash(email):
    key = email.split("@")[0]
    return st.secrets.get("passwords", {}).get(key, "")

def check_login(email, password):
    if email not in USERS:
        return False
    stored = _get_hash(email)
    if not stored:
        return False
    return bcrypt.checkpw(password.encode(), stored.encode())

def login_page():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
    html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
        background: #0a1628 !important;
        font-family: 'Inter', sans-serif;
    }
    [data-testid="stSidebar"] { display: none; }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.4, 1])
    with col2:
        st.markdown("<div style='height:80px'></div>", unsafe_allow_html=True)
        st.markdown("""
        <div style='text-align:center;margin-bottom:32px;'>
            <div style='font-size:2.6rem;font-weight:800;color:#a78bfa;letter-spacing:-0.02em;'>
                Trinity Ops
            </div>
            <div style='color:#4a6580;font-size:0.9rem;margin-top:4px;letter-spacing:0.08em;text-transform:uppercase;'>
                Team Dashboard
            </div>
        </div>
        """, unsafe_allow_html=True)

        with st.form("login_form"):
            email    = st.text_input("Email", placeholder="you@trinityops.io")
            password = st.text_input("Password", type="password", placeholder="Password")
            submit   = st.form_submit_button("Sign In", type="primary", use_container_width=True)

        if submit:
            if check_login(email.strip().lower(), password):
                st.session_state.authenticated  = True
                st.session_state.user_email     = email.strip().lower()
                st.session_state.user_name      = USERS[email.strip().lower()]
                st.rerun()
            else:
                st.error("Incorrect email or password.")

def require_auth():
    if not st.session_state.get("authenticated"):
        login_page()
        st.stop()

# ── Config from secrets ────────────────────────────────────────────────────────

def load_businesses():
    return {
        "vibe": {
            "name":           st.secrets["vibe"]["name"],
            "emoji":          st.secrets["vibe"]["emoji"],
            "api_key":        st.secrets["vibe"]["api_key"],
            "monthly_target": int(st.secrets["vibe"]["monthly_target"]),
            "reps":           json.loads(st.secrets["vibe"]["reps"]),
        },
        "rps": {
            "name":           st.secrets["rps"]["name"],
            "emoji":          st.secrets["rps"]["emoji"],
            "api_key":        st.secrets["rps"]["api_key"],
            "monthly_target": int(st.secrets["rps"]["monthly_target"]),
            "reps":           json.loads(st.secrets["rps"]["reps"]),
        },
    }

# ── Helpers ────────────────────────────────────────────────────────────────────

def fmt_money(n):
    return f"${n:,.0f}"

def find_user_ids(users, first_name):
    if not first_name:
        return []
    name = first_name.lower()
    return [u["id"] for u in users if (u.get("first_name") or "").lower() == name]

def _filter_this_month(opps):
    month_start = date.today().replace(day=1).isoformat()
    return [o for o in opps if (o.get("date_won") or "") >= month_start]

def _val(opp):
    return (opp.get("value") or 0) / 100

def revenue_this_month(won, user_ids=None):
    opps = _filter_this_month(won)
    if user_ids:
        opps = [o for o in opps if o.get("user_id") in user_ids]
    return sum(_val(o) for o in opps)

def deals_this_month(won, user_ids=None):
    opps = _filter_this_month(won)
    if user_ids:
        opps = [o for o in opps if o.get("user_id") in user_ids]
    return len(opps)

def pipeline_value(active, user_ids=None):
    opps = active
    if user_ids:
        opps = [o for o in opps if o.get("user_id") in user_ids]
    return sum(_val(o) for o in opps)

def call_count(calls, user_ids=None):
    if user_ids:
        return sum(1 for c in calls if c.get("user_id") in user_ids)
    return len(calls)

def progress_bar(label, current, target):
    pct = min(current / target, 1.0) if target > 0 else 0
    pct_int = int(pct * 100)
    if pct >= 1:
        bar_color, text_color = "linear-gradient(90deg,#8b5cf6,#a78bfa)", "#a78bfa"
    elif pct >= 0.5:
        bar_color, text_color = "linear-gradient(90deg,#f59e0b,#d97706)", "#f59e0b"
    else:
        bar_color, text_color = "linear-gradient(90deg,#ef4444,#dc2626)", "#ef4444"
    st.markdown(f"""
    <div style="margin-bottom:14px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px;">
        <span style="font-weight:700;color:#c8d8eb;font-size:0.93rem;">{label}</span>
        <span style="font-weight:700;color:{text_color};font-size:0.93rem;">
          {fmt_money(current)} / {fmt_money(target)} &nbsp;·&nbsp; {pct_int}%
        </span>
      </div>
      <div style="background:#1a3050;border-radius:8px;height:10px;overflow:hidden;">
        <div style="width:{pct_int}%;background:{bar_color};height:100%;border-radius:8px;transition:width 0.4s;"></div>
      </div>
    </div>
    """, unsafe_allow_html=True)

# ── CSS ────────────────────────────────────────────────────────────────────────

def inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"], .main {
        background-color: #0a1628 !important;
        font-family: 'Inter', sans-serif;
        color: #e8edf5 !important;
    }
    [data-testid="stSidebar"] {
        background: #071020 !important;
        border-right: 1px solid #152035 !important;
    }
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] div { color: #7a93b8 !important; font-size:0.85rem; }
    [data-testid="stSidebar"] .stRadio label {
        padding:7px 12px; border-radius:7px; transition:all 0.15s;
        color:#a8bdd4 !important; font-weight:500;
    }
    [data-testid="stSidebar"] .stRadio label:hover {
        background:rgba(167,139,250,0.12) !important; color:#a78bfa !important;
    }
    [data-testid="stSidebar"] [data-testid="stMetricValue"] {
        color:#a78bfa !important; font-weight:800 !important; font-size:1.4rem !important;
    }
    [data-testid="stSidebar"] [data-testid="stMetricLabel"] {
        color:#4a6580 !important; font-size:0.7rem !important;
        text-transform:uppercase; letter-spacing:0.08em;
    }
    [data-testid="stSidebar"] hr { border-color:#152035 !important; margin:10px 0 !important; }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color:#e8edf5 !important; font-size:1rem !important; font-weight:700 !important;
    }
    h1 { color:#a78bfa !important; font-weight:800 !important; font-size:1.6rem !important;
         letter-spacing:-0.02em; margin-bottom:2px !important; }
    h2 { color:#c8d8eb !important; font-weight:700 !important; font-size:1.1rem !important; }
    h3 { color:#a8bdd4 !important; font-weight:600 !important; font-size:0.98rem !important; }
    p, li { color:#a8bdd4; font-size:0.88rem; }
    [data-testid="metric-container"] {
        background:#112240 !important; border:1px solid #1a3050 !important;
        border-radius:10px; padding:16px 20px !important;
        box-shadow:0 4px 16px rgba(0,0,0,0.35); transition:all 0.2s;
    }
    [data-testid="metric-container"]:hover {
        border-color:#a78bfa !important; box-shadow:0 4px 24px rgba(167,139,250,0.15);
        transform:translateY(-1px);
    }
    [data-testid="stMetricLabel"] {
        color:#4a6580 !important; font-size:0.7rem !important; font-weight:700 !important;
        text-transform:uppercase; letter-spacing:0.08em;
    }
    [data-testid="stMetricValue"] {
        color:#e8edf5 !important; font-size:1.7rem !important;
        font-weight:800 !important; letter-spacing:-0.02em; line-height:1.1;
    }
    .stButton > button { border-radius:7px; font-weight:600; font-size:0.83rem;
        transition:all 0.18s; letter-spacing:0.02em; }
    .stButton > button[kind="primary"] {
        background:linear-gradient(135deg,#8b5cf6 0%,#a78bfa 100%) !important;
        border:none !important; color:white !important;
        box-shadow:0 2px 12px rgba(139,92,246,0.35); font-weight:700 !important;
    }
    .stButton > button[kind="primary"]:hover {
        transform:translateY(-1px); box-shadow:0 6px 22px rgba(139,92,246,0.5);
    }
    .stButton > button[kind="secondary"] {
        border:1px solid #1a3050 !important; color:#7a93b8 !important;
        background:#112240 !important;
    }
    .stButton > button[kind="secondary"]:hover {
        background:#152a4a !important; border-color:#a78bfa !important;
        color:#a78bfa !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"] {
        border:1px solid #1a3050 !important; border-radius:10px !important;
        background:#112240 !important; box-shadow:0 4px 16px rgba(0,0,0,0.3) !important;
        transition:all 0.2s;
    }
    [data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color:#2d1f5e !important;
        box-shadow:0 6px 24px rgba(167,139,250,0.08) !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        background:#0d1e35; border-radius:8px; padding:3px;
        gap:2px; border:1px solid #1a3050;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius:6px; color:#4a6580; font-weight:600; font-size:0.82rem;
        padding:5px 14px; transition:all 0.15s; background:transparent;
    }
    .stTabs [aria-selected="true"] {
        background:#112240 !important; color:#a78bfa !important;
        font-weight:700 !important; box-shadow:0 2px 8px rgba(0,0,0,0.4);
    }
    [data-testid="stDataFrame"] {
        border:1px solid #1a3050; border-radius:10px; overflow:hidden;
    }
    [data-testid="stExpander"] {
        border:1px solid #1a3050 !important; border-radius:10px !important;
        background:#112240 !important; margin-bottom:6px;
    }
    [data-testid="stExpander"] summary {
        font-weight:600; color:#a8bdd4; font-size:0.87rem; padding:10px 14px;
    }
    [data-testid="stExpander"] summary:hover { color:#a78bfa; }
    .stTextInput input, .stTextArea textarea {
        border-radius:7px !important; border:1px solid #1a3050 !important;
        background:#0a1628 !important; color:#e8edf5 !important; font-size:0.87rem !important;
    }
    .stTextInput input:focus, .stTextArea textarea:focus {
        border-color:#a78bfa !important;
        box-shadow:0 0 0 3px rgba(167,139,250,0.18) !important;
    }
    .stSelectbox > div > div {
        border-radius:7px !important; border:1px solid #1a3050 !important;
        background:#0a1628 !important; color:#e8edf5 !important;
    }
    [data-baseweb="menu"] {
        background:#112240 !important; border:1px solid #1a3050 !important;
        border-radius:8px !important;
    }
    [data-testid="stAlert"] {
        border-radius:8px !important; background:#0d1e35 !important;
    }
    hr { border-color:#152035 !important; }
    [data-testid="stCaptionContainer"] p { color:#4a6580 !important; font-size:0.78rem !important; }
    </style>
    """, unsafe_allow_html=True)

# ── UI Components ──────────────────────────────────────────────────────────────

def rep_card(rep_name, role, deals, revenue, pipeline, calls):
    with st.container(border=True):
        st.markdown(f"### {rep_name} &nbsp;<span style='font-size:0.75rem;color:#4a6580;font-weight:500;'>{role}</span>", unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Deals Closed",  deals)
        c2.metric("Revenue",       fmt_money(revenue))
        c3.metric("Pipeline",      fmt_money(pipeline))
        c4.metric("Calls (mo.)",   calls)

# ── Pages ──────────────────────────────────────────────────────────────────────

def page_command_center(BUSINESSES):
    st.title("🎯 Command Center")
    st.caption(f"Today is {date.today().strftime('%A, %B %d, %Y')}")

    col_sync, _ = st.columns([1, 6])
    with col_sync:
        if st.button("🔄 Sync All", type="secondary"):
            close_api.clear_cache()
            st.rerun()

    all_data = {}
    for biz_key, biz in BUSINESSES.items():
        with st.spinner(f"Loading {biz['name']}..."):
            won,    _ = close_api.get_won_this_month(biz["api_key"])
            active, _ = close_api.get_active_pipeline(biz["api_key"])
            calls,  _ = close_api.get_calls_this_month(biz["api_key"])
        all_data[biz_key] = {"won": won, "active": active, "calls": calls, "config": biz}

    total_revenue  = sum(revenue_this_month(d["won"]) for d in all_data.values())
    total_target   = sum(d["config"]["monthly_target"] for d in all_data.values())
    total_pipeline = sum(pipeline_value(d["active"]) for d in all_data.values())
    total_deals    = sum(deals_this_month(d["won"]) for d in all_data.values())

    st.subheader("📊 Combined Performance This Month")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Combined Revenue",  fmt_money(total_revenue))
    c2.metric("Combined Target",   fmt_money(total_target))
    c3.metric("Open Pipeline",     fmt_money(total_pipeline))
    c4.metric("Deals Closed",      total_deals)

    st.subheader("🎯 Revenue Goals")
    for biz_key, d in all_data.items():
        biz = d["config"]
        progress_bar(f"{biz['emoji']} {biz['name']}", revenue_this_month(d["won"]), biz["monthly_target"])

    st.divider()
    st.subheader("👥 Rep Performance")
    rows = []
    for biz_key, d in all_data.items():
        biz = d["config"]
        users, _ = close_api.get_users(biz["api_key"])
        for rep in biz["reps"]:
            uids = find_user_ids(users, rep["name"])
            rows.append({
                "Business": f"{biz['emoji']} {biz['name']}",
                "Rep":      rep["name"],
                "Role":     rep["role"],
                "Revenue":  fmt_money(revenue_this_month(d["won"], uids)),
                "Deals":    deals_this_month(d["won"], uids),
                "Pipeline": fmt_money(pipeline_value(d["active"], uids)),
                "Calls":    call_count(d["calls"], uids),
            })
    if rows:
        st.dataframe(
            pd.DataFrame(rows).sort_values("Deals", ascending=False),
            use_container_width=True, hide_index=True
        )


def page_business(biz_key, BUSINESSES):
    biz    = BUSINESSES[biz_key]
    api    = biz["api_key"]
    reps   = biz["reps"]
    target = biz["monthly_target"]

    st.title(f"{biz['emoji']} {biz['name']}")

    col_sync, _ = st.columns([1, 5])
    with col_sync:
        if st.button("🔄 Sync", type="secondary"):
            close_api.clear_cache()
            st.rerun()

    with st.spinner("Loading from Close CRM..."):
        won,    err1 = close_api.get_won_this_month(api)
        active, err2 = close_api.get_active_pipeline(api)
        calls,  err3 = close_api.get_calls_this_month(api)
        users,  err4 = close_api.get_users(api)

    for err in [err1, err2, err3, err4]:
        if err:
            st.error(f"Close CRM error: {err}")
            return

    rep_ids = {rep["name"]: find_user_ids(users, rep["name"]) for rep in reps}

    tab_overview, tab_pipeline, *rep_tabs = st.tabs(
        ["📊 Overview", "🔭 Pipeline"] + [f"👤 {r['name']}" for r in reps]
    )

    # ── Overview ──────────────────────────────────────────────────────────────
    with tab_overview:
        rev   = revenue_this_month(won)
        deals = deals_this_month(won)
        pipe  = pipeline_value(active)
        total_calls = call_count(calls)

        st.subheader("This Month")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Revenue",       fmt_money(rev))
        c2.metric("Deals Closed",  deals)
        c3.metric("Open Pipeline", fmt_money(pipe))
        c4.metric("Calls Made",    total_calls)

        st.subheader("Revenue Goal")
        progress_bar(biz["name"], rev, target)

        st.subheader("Team Performance")
        for rep in reps:
            uids = rep_ids.get(rep["name"])
            rep_card(
                rep["name"], rep["role"],
                deals_this_month(won, uids),
                revenue_this_month(won, uids),
                pipeline_value(active, uids),
                call_count(calls, uids),
            )

        if won:
            st.subheader("Recent Wins")
            rows = [
                {"Lead": o.get("lead_name", ""), "Value": fmt_money(_val(o)),
                 "Rep": o.get("user_name", ""), "Date Won": o.get("date_won", "")}
                for o in sorted(won, key=lambda x: x.get("date_won", ""), reverse=True)[:10]
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── Pipeline ──────────────────────────────────────────────────────────────
    with tab_pipeline:
        st.subheader("Active Opportunities")
        if active:
            rows = [
                {"Lead": o.get("lead_name", ""), "Value": fmt_money(_val(o)),
                 "Rep": o.get("user_name", ""), "Status": o.get("status_label", ""),
                 "Close Date": o.get("close_date", "")}
                for o in sorted(active, key=lambda x: x.get("value", 0), reverse=True)
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            st.caption(f"Total pipeline: {fmt_money(pipeline_value(active))}")
        else:
            st.info("No active opportunities.")

    # ── Rep Tabs ──────────────────────────────────────────────────────────────
    for i, rep in enumerate(reps):
        with rep_tabs[i]:
            uids = rep_ids.get(rep["name"])
            if not uids:
                st.warning(f"Could not find **{rep['name']}** in Close CRM.")
                continue

            rep_won    = [o for o in won    if o.get("user_id") in uids]
            rep_active = [o for o in active if o.get("user_id") in uids]
            rep_calls  = [c for c in calls  if c.get("user_id") in uids]

            st.subheader(f"{rep['name']} — {rep['role']}")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Deals Closed",  len(rep_won))
            c2.metric("Revenue",       fmt_money(sum(_val(o) for o in rep_won)))
            c3.metric("Pipeline",      fmt_money(sum(_val(o) for o in rep_active)))
            c4.metric("Calls (mo.)",   len(rep_calls))

            if rep_won:
                st.subheader("Won This Month")
                rows = [{"Lead": o.get("lead_name", ""), "Value": fmt_money(_val(o)),
                         "Date Won": o.get("date_won", "")} for o in rep_won]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            if rep_active:
                st.subheader("Active Pipeline")
                rows = [{"Lead": o.get("lead_name", ""), "Value": fmt_money(_val(o)),
                         "Status": o.get("status_label", ""), "Close Date": o.get("close_date", "")}
                        for o in sorted(rep_active, key=lambda x: x.get("value", 0), reverse=True)]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="Trinity Ops Dashboard",
        page_icon="🔺",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    require_auth()
    inject_css()

    BUSINESSES = load_businesses()

    with st.sidebar:
        st.markdown("""
        <div style='padding:4px 0 12px 0;'>
            <div style='font-size:1.3rem;font-weight:800;color:#a78bfa;'>🔺 Trinity Ops</div>
            <div style='font-size:0.7rem;color:#4a6580;text-transform:uppercase;
                        letter-spacing:0.1em;margin-top:2px;'>Team Dashboard</div>
        </div>
        """, unsafe_allow_html=True)
        st.caption(f"Today: {date.today().strftime('%b %d, %Y')}")
        st.divider()

        st.caption("OVERVIEW")
        overview_page = st.radio("nav_overview", [
            "🎯 Command Center",
        ], label_visibility="collapsed", key="nav_overview")

        st.divider()
        st.caption("BUSINESSES")
        team_page = st.radio("nav_teams", [
            "💎 Vibe Consultant",
            "🎮 RockPaperScissors.io",
        ], label_visibility="collapsed", key="nav_teams")

        st.divider()
        user_name = st.session_state.get("user_name", "")
        st.caption(f"Signed in as **{user_name}**")
        if st.button("Sign Out", type="secondary", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.user_email    = ""
            st.session_state.user_name     = ""
            st.rerun()

    if "active_section" not in st.session_state:
        st.session_state.active_section = "overview"

    if st.session_state.get("_last_overview") != overview_page:
        st.session_state.active_section      = "overview"
        st.session_state["_last_overview"]   = overview_page
    elif st.session_state.get("_last_teams") != team_page:
        st.session_state.active_section    = "teams"
        st.session_state["_last_teams"]    = team_page

    section = st.session_state.active_section

    if section == "overview":
        page_command_center(BUSINESSES)
    elif section == "teams":
        if team_page == "💎 Vibe Consultant":
            page_business("vibe", BUSINESSES)
        elif team_page == "🎮 RockPaperScissors.io":
            page_business("rps", BUSINESSES)


if __name__ == "__main__":
    main()

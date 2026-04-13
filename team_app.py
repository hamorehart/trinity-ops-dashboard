import streamlit as st
import bcrypt
import json
import pandas as pd
import plotly.graph_objects as go
from datetime import date, datetime
import close_api

# ── Auth ───────────────────────────────────────────────────────────────────────

USERS = {
    "simon@trinityops.io":  "Simon",
    "hannah@trinityops.io": "Hannah",
    "josh@trinityops.io":   "Josh",
}

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
            <div style='font-size:2.6rem;font-weight:800;color:#14b8a6;letter-spacing:-0.02em;'>
                Trinity Ops
            </div>
            <div style='color:#4a6580;font-size:0.9rem;margin-top:4px;
                        letter-spacing:0.08em;text-transform:uppercase;'>
                Team Dashboard
            </div>
        </div>
        """, unsafe_allow_html=True)
        with st.form("login_form"):
            email    = st.text_input("Email", placeholder="you@trinityops.io")
            password = st.text_input("Password", type="password", placeholder="Password")
            submit   = st.form_submit_button("Sign In", type="primary",
                                             use_container_width=True)
        if submit:
            if check_login(email.strip().lower(), password):
                st.session_state.authenticated = True
                st.session_state.user_email    = email.strip().lower()
                st.session_state.user_name     = USERS[email.strip().lower()]
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

# ── Month helpers ──────────────────────────────────────────────────────────────

def get_month_options():
    """Last 13 months, most recent first."""
    y, m = date.today().year, date.today().month
    months = []
    for _ in range(13):
        months.append(date(y, m, 1).strftime("%B %Y"))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return months

def month_to_range(month_str):
    """'April 2026' → ('2026-04-01', '2026-05-01')"""
    d = datetime.strptime(month_str, "%B %Y").date().replace(day=1)
    if d.month == 12:
        end = d.replace(year=d.year + 1, month=1)
    else:
        end = d.replace(month=d.month + 1)
    return d.isoformat(), end.isoformat()

def month_selector(key="month_sel"):
    options = get_month_options()
    col, _ = st.columns([2, 5])
    with col:
        selected = st.selectbox("📅 Month", options, index=0, key=key)
    return month_to_range(selected)

# ── Formatters ─────────────────────────────────────────────────────────────────

def fmt_money(n):
    return f"${n:,.0f}"

def fmt_pct(n):
    return f"{n:.0f}%"

# ── Data helpers ───────────────────────────────────────────────────────────────

def find_user_ids(users, first_name):
    if not first_name:
        return []
    name = first_name.lower()
    return [u["id"] for u in users if (u.get("first_name") or "").lower() == name]

def _val(opp):
    return (opp.get("value") or 0) / 100

def revenue_in_range(won, month_start, month_end, user_ids=None):
    opps = [o for o in won if month_start <= (o.get("date_won") or "") < month_end]
    if user_ids:
        opps = [o for o in opps if o.get("user_id") in user_ids]
    return sum(_val(o) for o in opps)

def deals_in_range(won, month_start, month_end, user_ids=None):
    opps = [o for o in won if month_start <= (o.get("date_won") or "") < month_end]
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

# ── Call metrics ───────────────────────────────────────────────────────────────

def get_vibe_call_metrics(api_key, month_start, month_end):
    meetings, err1 = close_api.get_meetings_in_range(api_key, month_start, month_end)
    changes,  err2 = close_api.get_lead_status_changes_in_range(api_key, month_start, month_end)
    err = err1 or err2
    if err:
        return 0, 0, 0, 0, err, []

    booked = len(meetings)
    NO_SHOW_STATUSES = {"didn't show up", "cancelled"}
    no_shows = sum(1 for c in changes
                   if (c.get("old_status_label") or "").strip().lower() == "call booked"
                   and (c.get("new_status_label") or "").strip().lower() in NO_SHOW_STATUSES)
    shows     = max(booked - no_shows, 0)
    show_rate = (shows / booked * 100) if booked > 0 else 0
    return booked, shows, no_shows, show_rate, None, meetings


def get_rps_call_metrics(api_key, month_start, month_end):
    BOOKED_ID    = "actitype_6iPyMCXtUDMCc1WrQbxk38"
    COMPLETED_ID = "actitype_1wbEHsXgDc5pI0uDad4vJA"
    NO_SHOW_ID   = "actitype_2A7bh2nzYu3lzTj5oVI7Ly"

    all_acts, err = close_api.get_all_custom_activities_in_range(api_key, month_start, month_end)
    if err:
        return 0, 0, 0, 0, err

    booked  = sum(1 for a in all_acts if a.get("custom_activity_type_id") == BOOKED_ID)
    show    = sum(1 for a in all_acts if a.get("custom_activity_type_id") == COMPLETED_ID)
    no_show = sum(1 for a in all_acts if a.get("custom_activity_type_id") == NO_SHOW_ID)

    total_outcome = show + no_show
    show_rate = (show / total_outcome * 100) if total_outcome > 0 else 0
    return booked, show, no_show, show_rate, None

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
    [data-testid="stSidebar"] [data-testid="stMetricValue"] {
        color:#14b8a6 !important; font-weight:800 !important; font-size:1.4rem !important;
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
    h1 { color:#14b8a6 !important; font-weight:800 !important; font-size:1.6rem !important;
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
        border-color:#14b8a6 !important;
        box-shadow:0 4px 24px rgba(20,184,166,0.15); transform:translateY(-1px);
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
        background:linear-gradient(135deg,#0d9488 0%,#14b8a6 100%) !important;
        border:none !important; color:white !important;
        box-shadow:0 2px 12px rgba(20,184,166,0.35); font-weight:700 !important;
    }
    .stButton > button[kind="primary"]:hover {
        transform:translateY(-1px); box-shadow:0 6px 22px rgba(20,184,166,0.5);
    }
    .stButton > button[kind="secondary"] {
        border:1px solid #1a3050 !important; color:#7a93b8 !important;
        background:#112240 !important;
    }
    .stButton > button[kind="secondary"]:hover {
        background:#152a4a !important; border-color:#14b8a6 !important;
        color:#14b8a6 !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"] {
        border:1px solid #1a3050 !important; border-radius:10px !important;
        background:#112240 !important; box-shadow:0 4px 16px rgba(0,0,0,0.3) !important;
        transition:all 0.2s;
    }
    [data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color:#134e4a !important;
        box-shadow:0 6px 24px rgba(20,184,166,0.08) !important;
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
    [data-testid="stExpander"] summary:hover { color:#14b8a6; }
    .stTextInput input, .stTextArea textarea {
        border-radius:7px !important; border:1px solid #1a3050 !important;
        background:#0a1628 !important; color:#e8edf5 !important; font-size:0.87rem !important;
    }
    .stTextInput input:focus, .stTextArea textarea:focus {
        border-color:#14b8a6 !important;
        box-shadow:0 0 0 3px rgba(20,184,166,0.18) !important;
    }
    .stSelectbox > div > div {
        border-radius:7px !important; border:1px solid #1a3050 !important;
        background:#0a1628 !important; color:#e8edf5 !important;
    }
    [data-baseweb="menu"] {
        background:#112240 !important; border:1px solid #1a3050 !important;
        border-radius:8px !important;
    }
    [data-testid="stAlert"] { border-radius:8px !important; background:#0d1e35 !important; }
    hr { border-color:#152035 !important; }
    [data-testid="stCaptionContainer"] p { color:#4a6580 !important; font-size:0.78rem !important; }
    </style>
    """, unsafe_allow_html=True)

# ── UI Components ──────────────────────────────────────────────────────────────

def kpi_card(label, value, sub=None, color="#e8edf5", accent=False):
    sub_html = f"<div style='color:#4a6580;font-size:0.75rem;margin-top:2px;'>{sub}</div>" if sub else ""
    border_left = "border-left:3px solid #14b8a6;" if accent else ""
    st.markdown(f"""
    <div style="background:#112240;border:1px solid #1a3050;border-radius:10px;
                padding:16px 20px;box-shadow:0 4px 16px rgba(0,0,0,0.35);{border_left}">
      <div style="color:#4a6580;font-size:0.7rem;font-weight:700;
                  text-transform:uppercase;letter-spacing:0.08em;">{label}</div>
      <div style="color:{color};font-size:1.7rem;font-weight:800;
                  letter-spacing:-0.02em;line-height:1.2;margin-top:4px;">{value}</div>
      {sub_html}
    </div>
    """, unsafe_allow_html=True)

def progress_bar(label, current, target):
    pct = min(current / target, 1.0) if target > 0 else 0
    pct_int = int(pct * 100)
    if pct >= 1:
        bar_color, text_color = "linear-gradient(90deg,#0d9488,#14b8a6)", "#14b8a6"
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
        <div style="width:{pct_int}%;background:{bar_color};height:100%;
                    border-radius:8px;transition:width 0.4s;"></div>
      </div>
    </div>
    """, unsafe_allow_html=True)

# ── Plotly chart helpers ────────────────────────────────────────────────────────

def _plotly_base_layout(height=280):
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#a8bdd4", size=11),
        margin=dict(l=0, r=24, t=32, b=0),
        height=height,
        showlegend=False,
    )

def chart_revenue_by_rep(rep_names, revenues, title="Revenue by Rep"):
    pairs = sorted(zip(rep_names, revenues), key=lambda x: x[1])
    names = [p[0] for p in pairs]
    vals  = [p[1] for p in pairs]

    fig = go.Figure(go.Bar(
        x=vals, y=names, orientation="h",
        marker=dict(color="#14b8a6", line=dict(width=0)),
        text=[fmt_money(v) for v in vals],
        textposition="outside",
        textfont=dict(color="#e8edf5", size=11, family="Inter"),
        hovertemplate="%{y}: %{x:$,.0f}<extra></extra>",
    ))
    layout = _plotly_base_layout(height=max(160, len(names) * 55))
    layout.update(
        title=dict(text=title, font=dict(size=12, color="#7a93b8"), x=0, pad=dict(l=0)),
        xaxis=dict(showgrid=True, gridcolor="#1a3050", gridwidth=1,
                   tickformat="$,.0f", tickfont=dict(color="#4a6580", size=10),
                   zeroline=False, showline=False),
        yaxis=dict(showgrid=False, tickfont=dict(color="#c8d8eb", size=11),
                   zeroline=False, showline=False),
    )
    fig.update_layout(**layout)
    return fig

def chart_calls_by_rep(rep_names, call_counts, title="Calls by Rep"):
    pairs = sorted(zip(rep_names, call_counts), key=lambda x: x[1])
    names = [p[0] for p in pairs]
    vals  = [p[1] for p in pairs]

    fig = go.Figure(go.Bar(
        x=vals, y=names, orientation="h",
        marker=dict(color="#0d9488", line=dict(width=0)),
        text=[str(v) for v in vals],
        textposition="outside",
        textfont=dict(color="#e8edf5", size=11, family="Inter"),
        hovertemplate="%{y}: %{x} calls<extra></extra>",
    ))
    layout = _plotly_base_layout(height=max(160, len(names) * 55))
    layout.update(
        title=dict(text=title, font=dict(size=12, color="#7a93b8"), x=0),
        xaxis=dict(showgrid=True, gridcolor="#1a3050",
                   tickfont=dict(color="#4a6580", size=10),
                   zeroline=False, showline=False),
        yaxis=dict(showgrid=False, tickfont=dict(color="#c8d8eb", size=11)),
    )
    fig.update_layout(**layout)
    return fig

def chart_show_rate_gauge(show_rate_pct, title="Show Rate"):
    if show_rate_pct >= 70:
        bar_color = "#22c55e"
    elif show_rate_pct >= 50:
        bar_color = "#f59e0b"
    else:
        bar_color = "#ef4444"

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=show_rate_pct,
        number=dict(suffix="%", font=dict(size=36, color="#e8edf5", family="Inter")),
        title=dict(text=title, font=dict(size=12, color="#7a93b8", family="Inter")),
        gauge=dict(
            axis=dict(range=[0, 100], tickwidth=1, tickcolor="#1a3050",
                      tickfont=dict(color="#4a6580", size=9), dtick=25),
            bar=dict(color=bar_color, thickness=0.25),
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
            steps=[
                dict(range=[0,  50], color="rgba(239,68,68,0.12)"),
                dict(range=[50, 70], color="rgba(245,158,11,0.12)"),
                dict(range=[70,100], color="rgba(34,197,94,0.12)"),
            ],
            threshold=dict(line=dict(color="#e8edf5", width=2),
                           thickness=0.75, value=show_rate_pct),
        ),
    ))
    layout = _plotly_base_layout(height=220)
    layout.update(margin=dict(l=24, r=24, t=40, b=0))
    fig.update_layout(**layout)
    return fig

def chart_team_comparison(vibe_rev, rps_rev, vibe_name="Vibe", rps_name="RPS"):
    fig = go.Figure(data=[
        go.Bar(name=vibe_name, x=[vibe_name], y=[vibe_rev],
               marker=dict(color="#14b8a6"),
               text=[fmt_money(vibe_rev)], textposition="outside",
               textfont=dict(color="#e8edf5", size=12)),
        go.Bar(name=rps_name,  x=[rps_name],  y=[rps_rev],
               marker=dict(color="#0d9488"),
               text=[fmt_money(rps_rev)],  textposition="outside",
               textfont=dict(color="#e8edf5", size=12)),
    ])
    layout = _plotly_base_layout(height=240)
    layout.update(
        title=dict(text="Revenue by Team", font=dict(size=12, color="#7a93b8"), x=0),
        barmode="group", bargap=0.35,
        xaxis=dict(showgrid=False, tickfont=dict(color="#c8d8eb")),
        yaxis=dict(showgrid=True, gridcolor="#1a3050",
                   tickformat="$,.0f", tickfont=dict(color="#4a6580", size=10),
                   zeroline=False),
        showlegend=False,
    )
    fig.update_layout(**layout)
    return fig

# ── Pages ──────────────────────────────────────────────────────────────────────

def page_master(BUSINESSES):
    # Header row
    h1, h2, h3 = st.columns([3, 2, 1])
    with h1:
        st.markdown("""
        <h1 style='margin-bottom:0;'>🔺 Trinity Ops</h1>
        <div style='color:#4a6580;font-size:0.78rem;text-transform:uppercase;
                    letter-spacing:0.1em;margin-top:2px;'>Master Dashboard</div>
        """, unsafe_allow_html=True)
    with h2:
        month_start, month_end = month_selector("master_month")
    with h3:
        st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
        if st.button("🔄 Sync All", type="secondary", use_container_width=True):
            close_api.clear_cache()
            st.rerun()

    # Data load
    all_data = {}
    for biz_key, biz in BUSINESSES.items():
        with st.spinner(f"Loading {biz['name']}..."):
            won,    _ = close_api.get_won_in_range(biz["api_key"], month_start, month_end)
            active, _ = close_api.get_active_pipeline(biz["api_key"])
            calls,  _ = close_api.get_calls_in_range(biz["api_key"], month_start, month_end)
        all_data[biz_key] = {"won": won, "active": active, "calls": calls, "config": biz}

    total_revenue  = sum(revenue_in_range(d["won"], month_start, month_end) for d in all_data.values())
    total_target   = sum(d["config"]["monthly_target"] for d in all_data.values())
    total_pipeline = sum(pipeline_value(d["active"]) for d in all_data.values())
    total_deals    = sum(deals_in_range(d["won"], month_start, month_end) for d in all_data.values())

    # Row 1: 4 KPI cards
    k1, k2, k3, k4 = st.columns(4)
    pct_to_target = (total_revenue / total_target * 100) if total_target > 0 else 0
    rev_color = "#22c55e" if pct_to_target >= 100 else ("#f59e0b" if pct_to_target >= 50 else "#ef4444")
    with k1:
        kpi_card("Combined Revenue", fmt_money(total_revenue),
                 sub=f"{fmt_pct(pct_to_target)} of target", color=rev_color, accent=True)
    with k2:
        kpi_card("Combined Target", fmt_money(total_target))
    with k3:
        kpi_card("Deals Closed", str(total_deals))
    with k4:
        kpi_card("Open Pipeline", fmt_money(total_pipeline))

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # Row 2: Revenue chart + team nav cards
    chart_col, nav_col = st.columns([3, 2])

    with chart_col:
        with st.container(border=True):
            vibe_rev = revenue_in_range(all_data["vibe"]["won"], month_start, month_end)
            rps_rev  = revenue_in_range(all_data["rps"]["won"],  month_start, month_end)
            fig = chart_team_comparison(
                vibe_rev, rps_rev,
                BUSINESSES["vibe"]["name"],
                BUSINESSES["rps"]["name"],
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with nav_col:
        for biz_key in ["vibe", "rps"]:
            biz = BUSINESSES[biz_key]
            rev = revenue_in_range(all_data[biz_key]["won"], month_start, month_end)
            tgt = biz["monthly_target"]
            pct = (rev / tgt * 100) if tgt > 0 else 0
            pct_color = "#22c55e" if pct >= 100 else ("#f59e0b" if pct >= 50 else "#ef4444")
            with st.container(border=True):
                st.markdown(f"""
                <div style='font-size:1.0rem;font-weight:700;color:#e8edf5;margin-bottom:6px;'>
                    {biz['emoji']} {biz['name']}
                </div>
                <div style='font-size:1.5rem;font-weight:800;color:#14b8a6;'>{fmt_money(rev)}</div>
                <div style='color:{pct_color};font-size:0.75rem;font-weight:600;margin-top:2px;'>
                    {fmt_pct(pct)} of target
                </div>
                """, unsafe_allow_html=True)
                if st.button(f"Open {biz['name']} →", key=f"nav_to_{biz_key}",
                             use_container_width=True, type="primary"):
                    st.session_state.current_page = biz_key
                    st.rerun()
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # Row 3: Revenue goal progress bars
    with st.container(border=True):
        st.markdown("<div style='font-size:0.7rem;font-weight:700;color:#4a6580;"
                    "text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px;'>"
                    "Revenue Goals</div>", unsafe_allow_html=True)
        for biz_key, d in all_data.items():
            biz = d["config"]
            progress_bar(
                f"{biz['emoji']} {biz['name']}",
                revenue_in_range(d["won"], month_start, month_end),
                biz["monthly_target"],
            )

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # Row 4: Rep performance table
    with st.container(border=True):
        st.markdown("<div style='font-size:0.7rem;font-weight:700;color:#4a6580;"
                    "text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px;'>"
                    "Rep Performance</div>", unsafe_allow_html=True)
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
                    "Revenue":  fmt_money(revenue_in_range(d["won"], month_start, month_end, uids)),
                    "Deals":    deals_in_range(d["won"], month_start, month_end, uids),
                    "Pipeline": fmt_money(pipeline_value(d["active"], uids)),
                    "Calls":    call_count(d["calls"], uids),
                })
        if rows:
            st.dataframe(
                pd.DataFrame(rows).sort_values("Deals", ascending=False),
                use_container_width=True, hide_index=True,
            )


def page_team(biz_key, BUSINESSES):
    biz    = BUSINESSES[biz_key]
    api    = biz["api_key"]
    reps   = biz["reps"]
    target = biz["monthly_target"]

    # Header row
    back_col, title_col, month_col, sync_col = st.columns([0.8, 3, 2, 1])
    with back_col:
        st.markdown("<div style='height:22px'></div>", unsafe_allow_html=True)
        if st.button("← Back", type="secondary"):
            st.session_state.current_page = "master"
            st.rerun()
    with title_col:
        st.markdown(f"<h1 style='margin-bottom:0;'>{biz['emoji']} {biz['name']}</h1>",
                    unsafe_allow_html=True)
    with month_col:
        month_start, month_end = month_selector(f"team_month_{biz_key}")
    with sync_col:
        st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
        if st.button("🔄 Sync", type="secondary", use_container_width=True, key=f"sync_{biz_key}"):
            close_api.clear_cache()
            st.rerun()

    # Data load
    with st.spinner("Loading from Close CRM..."):
        won,    err1 = close_api.get_won_in_range(api, month_start, month_end)
        active, err2 = close_api.get_active_pipeline(api)
        calls,  err3 = close_api.get_calls_in_range(api, month_start, month_end)
        users,  err4 = close_api.get_users(api)

    for err in [err1, err2, err3, err4]:
        if err:
            st.error(f"Close CRM error: {err}")
            return

    rep_ids = {rep["name"]: find_user_ids(users, rep["name"]) for rep in reps}

    # Call KPIs
    with st.spinner("Loading call data..."):
        if biz_key == "vibe":
            booked, shows, no_shows, show_rate, call_err, booked_meetings = \
                get_vibe_call_metrics(api, month_start, month_end)
        else:
            booked, shows, no_shows, show_rate, call_err = \
                get_rps_call_metrics(api, month_start, month_end)
            booked_meetings = []

    rev   = revenue_in_range(won, month_start, month_end)
    deals = deals_in_range(won, month_start, month_end)
    pipe  = pipeline_value(active)
    total_calls_count = call_count(calls)

    # Row 1: 6 KPI cards
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    pct = (rev / target * 100) if target > 0 else 0
    rev_color = "#22c55e" if pct >= 100 else ("#f59e0b" if pct >= 50 else "#ef4444")
    with k1:
        kpi_card("Revenue", fmt_money(rev), sub=f"{fmt_pct(pct)} of target",
                 color=rev_color, accent=True)
    with k2:
        kpi_card("Target", fmt_money(target))
    with k3:
        kpi_card("Deals Closed", str(deals))
    with k4:
        if call_err:
            kpi_card("Booked Calls", "—")
        else:
            kpi_card("Booked Calls", str(booked))
    with k5:
        if call_err:
            kpi_card("Show Rate", "—")
        else:
            sr_color = "#22c55e" if show_rate >= 70 else ("#f59e0b" if show_rate >= 50 else "#ef4444")
            kpi_card("Show Rate", fmt_pct(show_rate),
                     sub=f"{shows} shows · {no_shows} no-shows", color=sr_color)
    with k6:
        kpi_card("Calls Made", str(total_calls_count))

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # Row 2: Revenue by Rep chart + Show Rate gauge
    chart_col, gauge_col = st.columns([3, 2])

    with chart_col:
        with st.container(border=True):
            rep_names = [r["name"] for r in reps]
            revenues  = [revenue_in_range(won, month_start, month_end, rep_ids.get(r["name"]))
                         for r in reps]
            fig = chart_revenue_by_rep(rep_names, revenues)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with gauge_col:
        with st.container(border=True):
            if call_err:
                st.warning("Call data unavailable")
            else:
                fig = chart_show_rate_gauge(show_rate)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                st.markdown(f"""
                <div style='text-align:center;margin-top:-8px;'>
                    <span style='color:#4a6580;font-size:0.7rem;text-transform:uppercase;
                                 letter-spacing:0.08em;'>
                        {booked} booked · {shows} shows · {no_shows} no-shows
                    </span>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # Row 3: Calls by Rep chart + Revenue Goal progress bars
    calls_col, goal_col = st.columns([3, 2])

    with calls_col:
        with st.container(border=True):
            call_counts_per_rep = [call_count(calls, rep_ids.get(r["name"])) for r in reps]
            fig = chart_calls_by_rep([r["name"] for r in reps], call_counts_per_rep)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with goal_col:
        with st.container(border=True):
            st.markdown("<div style='font-size:0.7rem;font-weight:700;color:#4a6580;"
                        "text-transform:uppercase;letter-spacing:0.08em;margin-bottom:12px;'>"
                        "Revenue Goal</div>", unsafe_allow_html=True)
            progress_bar(biz["name"], rev, target)
            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            rep_target = target / max(len(reps), 1)
            for rep in reps:
                uids = rep_ids.get(rep["name"])
                rep_rev = revenue_in_range(won, month_start, month_end, uids)
                progress_bar(rep["name"], rep_rev, rep_target)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # Row 4: Recent Wins + Active Pipeline tables side by side
    wins_col, pipe_col = st.columns(2)

    with wins_col:
        with st.container(border=True):
            st.markdown("<div style='font-size:0.7rem;font-weight:700;color:#4a6580;"
                        "text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;'>"
                        "Recent Wins</div>", unsafe_allow_html=True)
            if won:
                rows = [
                    {"Lead": o.get("lead_name", ""), "Value": fmt_money(_val(o)),
                     "Rep": o.get("user_name", ""), "Date": o.get("date_won", "")}
                    for o in sorted(won, key=lambda x: x.get("date_won", ""), reverse=True)[:8]
                ]
                st.dataframe(pd.DataFrame(rows), use_container_width=True,
                             hide_index=True, height=260)
            else:
                st.info("No wins this month yet.")

    with pipe_col:
        with st.container(border=True):
            st.markdown(f"<div style='font-size:0.7rem;font-weight:700;color:#4a6580;"
                        f"text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;'>"
                        f"Active Pipeline · {fmt_money(pipe)}</div>", unsafe_allow_html=True)
            if active:
                rows = [
                    {"Lead": o.get("lead_name", ""), "Value": fmt_money(_val(o)),
                     "Rep": o.get("user_name", ""), "Status": o.get("status_label", ""),
                     "Close Date": o.get("close_date", "")}
                    for o in sorted(active, key=lambda x: x.get("value", 0), reverse=True)[:8]
                ]
                st.dataframe(pd.DataFrame(rows), use_container_width=True,
                             hide_index=True, height=260)
            else:
                st.info("No active opportunities.")

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # Row 5: Individual rep detail via selectbox
    with st.container(border=True):
        st.markdown("<div style='font-size:0.7rem;font-weight:700;color:#4a6580;"
                    "text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px;'>"
                    "Individual Rep Detail</div>", unsafe_allow_html=True)

        rep_options = [r["name"] for r in reps]
        selected_rep = st.selectbox("Select rep", rep_options,
                                    key=f"rep_sel_{biz_key}", label_visibility="collapsed")

        uids     = rep_ids.get(selected_rep)
        rep_won  = [o for o in won    if o.get("user_id") in (uids or [])]
        rep_actv = [o for o in active if o.get("user_id") in (uids or [])]
        rep_call = [c for c in calls  if c.get("user_id") in (uids or [])]

        if not uids:
            st.warning(f"Could not find {selected_rep} in Close CRM.")
        else:
            d1, d2, d3, d4 = st.columns(4)
            with d1:
                kpi_card("Deals", str(len(rep_won)))
            with d2:
                kpi_card("Revenue", fmt_money(sum(_val(o) for o in rep_won)), accent=True)
            with d3:
                kpi_card("Pipeline", fmt_money(sum(_val(o) for o in rep_actv)))
            with d4:
                kpi_card("Calls", str(len(rep_call)))

            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
            r1, r2 = st.columns(2)
            with r1:
                if rep_won:
                    st.markdown("<div style='font-size:0.7rem;color:#4a6580;text-transform:uppercase;"
                                "letter-spacing:0.08em;margin-bottom:6px;'>Wins</div>",
                                unsafe_allow_html=True)
                    rows = [{"Lead": o.get("lead_name", ""), "Value": fmt_money(_val(o)),
                             "Date": o.get("date_won", "")} for o in rep_won]
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                else:
                    st.caption("No wins this month.")
            with r2:
                if rep_actv:
                    st.markdown("<div style='font-size:0.7rem;color:#4a6580;text-transform:uppercase;"
                                "letter-spacing:0.08em;margin-bottom:6px;'>Active Pipeline</div>",
                                unsafe_allow_html=True)
                    rows = [{"Lead": o.get("lead_name", ""), "Value": fmt_money(_val(o)),
                             "Status": o.get("status_label", ""),
                             "Close Date": o.get("close_date", "")}
                            for o in sorted(rep_actv, key=lambda x: x.get("value", 0), reverse=True)]
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                else:
                    st.caption("No active pipeline.")

    # Vibe only: booked calls expander
    if biz_key == "vibe" and not call_err and booked_meetings:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        with st.expander(f"All Booked Calls This Month ({booked})"):
            rows = [
                {
                    "Lead":      m.get("lead_name") or m.get("contact_name") or "—",
                    "Title":     (m.get("title") or "")
                                  .replace("Implementation Call - Danie + ", "")
                                  .replace("Implementation Call - ", ""),
                    "Call Date": (m.get("starts_at") or "")[:10],
                    "Booked On": (m.get("date_created") or "")[:10],
                }
                for m in sorted(booked_meetings, key=lambda x: x.get("starts_at", ""))
            ]
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

    if "current_page" not in st.session_state:
        st.session_state.current_page = "master"

    with st.sidebar:
        st.markdown("""
        <div style='padding:4px 0 12px 0;'>
            <div style='font-size:1.3rem;font-weight:800;color:#14b8a6;'>🔺 Trinity Ops</div>
            <div style='font-size:0.7rem;color:#4a6580;text-transform:uppercase;
                        letter-spacing:0.1em;margin-top:2px;'>Team Dashboard</div>
        </div>
        """, unsafe_allow_html=True)
        st.caption(f"Today: {date.today().strftime('%b %d, %Y')}")
        st.divider()

        st.caption("OVERVIEW")
        master_type = "primary" if st.session_state.current_page == "master" else "secondary"
        if st.button("🎯 Master Dashboard", use_container_width=True, type=master_type,
                     key="nav_master"):
            st.session_state.current_page = "master"
            st.rerun()

        st.divider()
        st.caption("TEAMS")

        vibe_type = "primary" if st.session_state.current_page == "vibe" else "secondary"
        if st.button("💎 Vibe Consultant", use_container_width=True, type=vibe_type,
                     key="nav_vibe"):
            st.session_state.current_page = "vibe"
            st.rerun()

        rps_type = "primary" if st.session_state.current_page == "rps" else "secondary"
        if st.button("🎮 RockPaperScissors.io", use_container_width=True, type=rps_type,
                     key="nav_rps"):
            st.session_state.current_page = "rps"
            st.rerun()

        st.divider()
        user_name = st.session_state.get("user_name", "")
        st.caption(f"Signed in as **{user_name}**")
        if st.button("Sign Out", type="secondary", use_container_width=True, key="sign_out"):
            for key in ["authenticated", "user_email", "user_name"]:
                st.session_state[key] = "" if key != "authenticated" else False
            st.session_state.current_page = "master"
            st.rerun()

    page = st.session_state.current_page
    if page == "master":
        page_master(BUSINESSES)
    elif page == "vibe":
        page_team("vibe", BUSINESSES)
    elif page == "rps":
        page_team("rps", BUSINESSES)


if __name__ == "__main__":
    main()

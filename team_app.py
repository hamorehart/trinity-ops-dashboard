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
        background: #080a10 !important;
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
            <div style='color:#ffffff;font-size:0.9rem;margin-top:4px;
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
        background-color: #080a10 !important;
        font-family: 'Inter', sans-serif;
        color: #e8edf5 !important;
    }
    [data-testid="stSidebar"] {
        background: #060709 !important;
        border-right: 1px solid #131620 !important;
    }
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] div { color: #ffffff !important; font-size:0.85rem; }
    [data-testid="stSidebar"] [data-testid="stMetricValue"] {
        color:#a78bfa !important; font-weight:800 !important; font-size:1.4rem !important;
    }
    [data-testid="stSidebar"] [data-testid="stMetricLabel"] {
        color:#ffffff !important; font-size:0.7rem !important;
        text-transform:uppercase; letter-spacing:0.08em;
    }
    [data-testid="stSidebar"] hr { border-color:#131620 !important; margin:10px 0 !important; }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color:#e8edf5 !important; font-size:1rem !important; font-weight:700 !important;
    }
    h1 { color:#a78bfa !important; font-weight:800 !important; font-size:1.6rem !important;
         letter-spacing:-0.02em; margin-bottom:2px !important; }
    h2 { color:#ffffff !important; font-weight:700 !important; font-size:1.1rem !important; }
    h3 { color:#ffffff !important; font-weight:600 !important; font-size:0.98rem !important; }
    p, li { color:#ffffff; font-size:0.88rem; }
    [data-testid="metric-container"] {
        background:#0e1117 !important; border:1px solid #1a1f2e !important;
        border-radius:10px; padding:16px 20px !important;
        box-shadow:0 4px 16px rgba(0,0,0,0.5); transition:all 0.2s;
    }
    [data-testid="metric-container"]:hover {
        border-color:#a78bfa !important;
        box-shadow:0 4px 24px rgba(167,139,250,0.15); transform:translateY(-1px);
    }
    [data-testid="stMetricLabel"] {
        color:#ffffff !important; font-size:0.7rem !important; font-weight:700 !important;
        text-transform:uppercase; letter-spacing:0.08em;
    }
    [data-testid="stMetricValue"] {
        color:#e8edf5 !important; font-size:1.7rem !important;
        font-weight:800 !important; letter-spacing:-0.02em; line-height:1.1;
    }
    .stButton > button { border-radius:7px; font-weight:600; font-size:0.83rem;
        transition:all 0.18s; letter-spacing:0.02em; }
    .stButton > button[kind="primary"] {
        background:linear-gradient(135deg,#7c3aed 0%,#a78bfa 100%) !important;
        border:none !important; color:white !important;
        box-shadow:0 2px 12px rgba(167,139,250,0.35); font-weight:700 !important;
    }
    .stButton > button[kind="primary"]:hover {
        transform:translateY(-1px); box-shadow:0 6px 22px rgba(167,139,250,0.5);
    }
    .stButton > button[kind="secondary"] {
        border:1px solid #1a1f2e !important; color:#ffffff !important;
        background:#0e1117 !important;
    }
    .stButton > button[kind="secondary"]:hover {
        background:#141824 !important; border-color:#a78bfa !important;
        color:#a78bfa !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"] {
        border:1px solid #1a1f2e !important; border-radius:10px !important;
        background:#0e1117 !important; box-shadow:0 4px 16px rgba(0,0,0,0.5) !important;
        transition:all 0.2s;
    }
    [data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color:#7c3aed !important;
        box-shadow:0 6px 24px rgba(167,139,250,0.08) !important;
    }
    [data-testid="stDataFrame"] {
        border:1px solid #1a1f2e; border-radius:10px; overflow:hidden;
    }
    [data-testid="stExpander"] {
        border:1px solid #1a1f2e !important; border-radius:10px !important;
        background:#0e1117 !important; margin-bottom:6px;
    }
    [data-testid="stExpander"] summary {
        font-weight:600; color:#ffffff; font-size:0.87rem; padding:10px 14px;
    }
    [data-testid="stExpander"] summary:hover { color:#a78bfa; }
    .stTextInput input, .stTextArea textarea {
        border-radius:7px !important; border:1px solid #1a1f2e !important;
        background:#080a10 !important; color:#e8edf5 !important; font-size:0.87rem !important;
    }
    .stTextInput input:focus, .stTextArea textarea:focus {
        border-color:#a78bfa !important;
        box-shadow:0 0 0 3px rgba(167,139,250,0.18) !important;
    }
    .stSelectbox > div > div {
        border-radius:7px !important; border:1px solid #1a1f2e !important;
        background:#080a10 !important; color:#e8edf5 !important;
    }
    [data-baseweb="menu"] {
        background:#0e1117 !important; border:1px solid #1a1f2e !important;
        border-radius:8px !important;
    }
    [data-testid="stAlert"] { border-radius:8px !important; background:#0a0c12 !important; }
    hr { border-color:#131620 !important; }
    [data-testid="stCaptionContainer"] p { color:#ffffff !important; font-size:0.78rem !important; }
    </style>
    """, unsafe_allow_html=True)

# ── UI Components ──────────────────────────────────────────────────────────────

def kpi_card(label, value, sub=None, color="#e8edf5", accent=False):
    sub_html = f"<div style='color:#ffffff;font-size:0.75rem;margin-top:2px;'>{sub}</div>" if sub else ""
    border_left = "border-left:3px solid #a78bfa;" if accent else ""
    st.markdown(f"""
    <div style="background:#0e1117;border:1px solid #1a1f2e;border-radius:10px;
                padding:16px 20px;box-shadow:0 4px 16px rgba(0,0,0,0.5);{border_left}">
      <div style="color:#ffffff;font-size:0.7rem;font-weight:700;
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
        bar_color, text_color = "linear-gradient(90deg,#7c3aed,#a78bfa)", "#a78bfa"
    elif pct >= 0.5:
        bar_color, text_color = "linear-gradient(90deg,#f59e0b,#d97706)", "#f59e0b"
    else:
        bar_color, text_color = "linear-gradient(90deg,#ef4444,#dc2626)", "#ef4444"
    st.markdown(f"""
    <div style="margin-bottom:14px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px;">
        <span style="font-weight:700;color:#ffffff;font-size:0.93rem;">{label}</span>
        <span style="font-weight:700;color:{text_color};font-size:0.93rem;">
          {fmt_money(current)} / {fmt_money(target)} &nbsp;·&nbsp; {pct_int}%
        </span>
      </div>
      <div style="background:#1a1f2e;border-radius:8px;height:10px;overflow:hidden;">
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
        font=dict(family="Inter, sans-serif", color="#ffffff", size=11),
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
        title=dict(text=title, font=dict(size=12, color="#ffffff"), x=0, pad=dict(l=0)),
        xaxis=dict(showgrid=True, gridcolor="#1a1f2e", gridwidth=1,
                   tickformat="$,.0f", tickfont=dict(color="#ffffff", size=10),
                   zeroline=False, showline=False),
        yaxis=dict(showgrid=False, tickfont=dict(color="#ffffff", size=11),
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
        title=dict(text=title, font=dict(size=12, color="#ffffff"), x=0),
        xaxis=dict(showgrid=True, gridcolor="#1a1f2e",
                   tickfont=dict(color="#ffffff", size=10),
                   zeroline=False, showline=False),
        yaxis=dict(showgrid=False, tickfont=dict(color="#ffffff", size=11)),
    )
    fig.update_layout(**layout)
    return fig

def chart_show_rate_gauge(show_rate_pct, title="Show Rate"):
    if show_rate_pct >= 70:
        bar_color = "#5b9bd5"
    elif show_rate_pct >= 50:
        bar_color = "#f59e0b"
    else:
        bar_color = "#ef4444"

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=show_rate_pct,
        number=dict(suffix="%", font=dict(size=36, color="#e8edf5", family="Inter")),
        title=dict(text=title, font=dict(size=12, color="#ffffff", family="Inter")),
        gauge=dict(
            axis=dict(range=[0, 100], tickwidth=1, tickcolor="#1a1f2e",
                      tickfont=dict(color="#ffffff", size=9), dtick=25),
            bar=dict(color=bar_color, thickness=0.25),
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
            steps=[
                dict(range=[0,  50], color="rgba(239,68,68,0.12)"),
                dict(range=[50, 70], color="rgba(245,158,11,0.12)"),
                dict(range=[70,100], color="rgba(91,155,213,0.12)"),
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
        title=dict(text="Revenue by Team", font=dict(size=12, color="#ffffff"), x=0),
        barmode="group", bargap=0.35,
        xaxis=dict(showgrid=False, tickfont=dict(color="#ffffff")),
        yaxis=dict(showgrid=True, gridcolor="#1a1f2e",
                   tickformat="$,.0f", tickfont=dict(color="#ffffff", size=10),
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
        <div style='color:#ffffff;font-size:0.78rem;text-transform:uppercase;
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
    rev_color = "#5b9bd5" if pct_to_target >= 100 else ("#f59e0b" if pct_to_target >= 50 else "#ef4444")
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
            pct_color = "#5b9bd5" if pct >= 100 else ("#f59e0b" if pct >= 50 else "#ef4444")
            with st.container(border=True):
                st.markdown(f"""
                <div style='font-size:1.0rem;font-weight:700;color:#e8edf5;margin-bottom:6px;'>
                    {biz['emoji']} {biz['name']}
                </div>
                <div style='font-size:1.5rem;font-weight:800;color:#a78bfa;'>{fmt_money(rev)}</div>
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
        st.markdown("<div style='font-size:0.7rem;font-weight:700;color:#ffffff;"
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
        st.markdown("<div style='font-size:0.7rem;font-weight:700;color:#ffffff;"
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
    rev_color = "#5b9bd5" if pct >= 100 else ("#f59e0b" if pct >= 50 else "#ef4444")
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
            sr_color = "#5b9bd5" if show_rate >= 70 else ("#f59e0b" if show_rate >= 50 else "#ef4444")
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
                    <span style='color:#ffffff;font-size:0.7rem;text-transform:uppercase;
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
            st.markdown("<div style='font-size:0.7rem;font-weight:700;color:#ffffff;"
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
            st.markdown("<div style='font-size:0.7rem;font-weight:700;color:#ffffff;"
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
            st.markdown(f"<div style='font-size:0.7rem;font-weight:700;color:#ffffff;"
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
        st.markdown("<div style='font-size:0.7rem;font-weight:700;color:#ffffff;"
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
                    st.markdown("<div style='font-size:0.7rem;color:#ffffff;text-transform:uppercase;"
                                "letter-spacing:0.08em;margin-bottom:6px;'>Wins</div>",
                                unsafe_allow_html=True)
                    rows = [{"Lead": o.get("lead_name", ""), "Value": fmt_money(_val(o)),
                             "Date": o.get("date_won", "")} for o in rep_won]
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                else:
                    st.caption("No wins this month.")
            with r2:
                if rep_actv:
                    st.markdown("<div style='font-size:0.7rem;color:#ffffff;text-transform:uppercase;"
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
        st.markdown(f"""
        <div style='padding:4px 0 16px 0;'>
            <div style='display:flex;align-items:center;gap:10px;'>
                <img src='data:image/png;base64,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'
                     style='width:48px;height:48px;border-radius:10px;flex-shrink:0;'/>
                <div>
                    <div style='font-size:1.5rem;font-weight:800;color:#a78bfa;
                                line-height:1.1;'>Trinity Ops</div>
                    <div style='font-size:0.7rem;color:#ffffff;text-transform:uppercase;
                                letter-spacing:0.1em;margin-top:2px;'>Team Dashboard</div>
                </div>
            </div>
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

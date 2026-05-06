import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import io
import re

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Spend Lens",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:ital,wght@0,300;0,400;0,500;1,300&family=Syne:wght@400;500;600;700;800&display=swap');

/* ── Base ── */
html, body, [class*="css"] {
    font-family: 'DM Mono', monospace;
    background-color: #0d0f14;
    color: #e8e4da;
}

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1400px; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #131720;
    border-right: 1px solid #1f2535;
}
[data-testid="stSidebar"] .stMarkdown h1,
[data-testid="stSidebar"] .stMarkdown h2,
[data-testid="stSidebar"] .stMarkdown h3 {
    font-family: 'Syne', sans-serif;
    color: #c8f542;
}

/* ── Headings ── */
h1, h2, h3 { font-family: 'Syne', sans-serif !important; letter-spacing: -0.03em; }

/* ── Metric cards ── */
[data-testid="metric-container"] {
    background: #131720;
    border: 1px solid #1f2535;
    border-radius: 8px;
    padding: 1rem 1.2rem;
}
[data-testid="metric-container"] label { color: #6b7a99 !important; font-size: 0.72rem !important; letter-spacing: 0.08em; text-transform: uppercase; }
[data-testid="metric-container"] [data-testid="stMetricValue"] { color: #c8f542 !important; font-family: 'Syne', sans-serif !important; font-size: 1.6rem !important; }
[data-testid="metric-container"] [data-testid="stMetricDelta"] { font-size: 0.75rem !important; }

/* ── Buttons ── */
.stButton > button {
    background: #c8f542;
    color: #0d0f14;
    border: none;
    border-radius: 4px;
    font-family: 'DM Mono', monospace;
    font-weight: 500;
    font-size: 0.8rem;
    letter-spacing: 0.05em;
    padding: 0.4rem 1rem;
    transition: all 0.15s ease;
}
.stButton > button:hover { background: #d9ff55; transform: translateY(-1px); }

/* ── Secondary button override ── */
button[kind="secondary"] {
    background: transparent !important;
    border: 1px solid #2a3245 !important;
    color: #8899bb !important;
}
button[kind="secondary"]:hover { border-color: #c8f542 !important; color: #c8f542 !important; }

/* ── Data editor / table ── */
[data-testid="stDataFrame"], [data-testid="data-grid-canvas"] {
    border: 1px solid #1f2535 !important;
    border-radius: 6px;
}

/* ── Tabs ── */
[data-testid="stTabs"] button {
    font-family: 'DM Mono', monospace;
    font-size: 0.78rem;
    color: #6b7a99;
    letter-spacing: 0.04em;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #c8f542 !important;
    border-bottom-color: #c8f542 !important;
}

/* ── Selectbox / inputs ── */
.stSelectbox > div > div, .stTextInput > div > div > input, .stDateInput > div {
    background: #131720 !important;
    border-color: #1f2535 !important;
    border-radius: 4px;
    color: #e8e4da !important;
}
.stSelectbox label, .stTextInput label, .stMultiSelect label { color: #6b7a99 !important; font-size: 0.75rem !important; }

/* ── File uploader ── */
[data-testid="stFileUploader"] {
    border: 1px dashed #2a3245;
    border-radius: 8px;
    background: #0d1119;
    padding: 0.5rem;
}
[data-testid="stFileUploader"] label { color: #8899bb !important; }

/* ── Logo / hero ── */
.hero-title {
    font-family: 'Syne', sans-serif;
    font-size: 2.4rem;
    font-weight: 800;
    color: #e8e4da;
    letter-spacing: -0.04em;
    line-height: 1;
}
.hero-title span { color: #c8f542; }
.hero-sub {
    color: #6b7a99;
    font-size: 0.78rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-top: 0.3rem;
}
.section-label {
    color: #c8f542;
    font-size: 0.68rem;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    margin-bottom: 0.2rem;
}
.pill {
    display: inline-block;
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    font-size: 0.68rem;
    font-weight: 500;
    letter-spacing: 0.04em;
}
.pill-rogers { background: #1e2e4a; color: #5b9cf6; }
.pill-ws     { background: #1e3a2a; color: #4ecb71; }

/* ── Category badge colors ── */
.cat-badge {
    padding: 0.1rem 0.5rem;
    border-radius: 3px;
    font-size: 0.68rem;
    letter-spacing: 0.04em;
}

/* ── Divider ── */
hr { border-color: #1f2535 !important; margin: 1.2rem 0 !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────
CATEGORY_COLORS = {
    "🍔 Food & Dining": "#f97316",
    "🛒 Groceries": "#eab308",
    "🚗 Transport": "#3b82f6",
    "🏠 Housing & Utilities": "#8b5cf6",
    "🎬 Entertainment": "#ec4899",
    "🛍️ Shopping": "#14b8a6",
    "💊 Health & Wellness": "#22c55e",
    "✈️ Travel": "#06b6d4",
    "💰 Transfers & Fees": "#94a3b8",
    "📱 Subscriptions": "#f43f5e",
    "🏦 Banking": "#64748b",
    "❓ Other": "#6b7280",
}

MERCHANT_CATEGORY_MAP = {
    "Restaurants": "🍔 Food & Dining",
    "Eating Places": "🍔 Food & Dining",
    "Fast Food": "🍔 Food & Dining",
    "Grocery": "🛒 Groceries",
    "Supermarkets": "🛒 Groceries",
    "Parking": "🚗 Transport",
    "Gas": "🚗 Transport",
    "Fuel": "🚗 Transport",
    "Taxi": "🚗 Transport",
    "Transit": "🚗 Transport",
    "Airlines": "✈️ Travel",
    "Hotels": "✈️ Travel",
    "Lodging": "✈️ Travel",
    "Entertainment": "🎬 Entertainment",
    "Movie": "🎬 Entertainment",
    "Drug": "💊 Health & Wellness",
    "Medical": "💊 Health & Wellness",
    "Pharmacy": "💊 Health & Wellness",
    "Clothing": "🛍️ Shopping",
    "Merchandise": "🛍️ Shopping",
    "Department Stores": "🛍️ Shopping",
    "Utilities": "🏠 Housing & Utilities",
    "Insurance": "🏠 Housing & Utilities",
    "Subscription": "📱 Subscriptions",
    "Streaming": "📱 Subscriptions",
}

def guess_category(merchant_cat: str, merchant_name: str) -> str:
    text = f"{merchant_cat} {merchant_name}".lower()
    for keyword, cat in MERCHANT_CATEGORY_MAP.items():
        if keyword.lower() in text:
            return cat
    for keyword in ["spotify", "netflix", "apple", "google", "amazon prime", "disney"]:
        if keyword in text:
            return "📱 Subscriptions"
    for keyword in ["tim horton", "starbucks", "mcdonald", "pizza", "sushi", "restaurant", "cafe", "coffee"]:
        if keyword in text:
            return "🍔 Food & Dining"
    for keyword in ["uber", "lyft", "ttc", "transit", "esso", "petro", "shell", "parkade", "parking"]:
        if keyword in text:
            return "🚗 Transport"
    for keyword in ["shoppers", "rexall", "costco", "walmart", "sobeys", "loblaws", "metro", "safeway", "save-on"]:
        if keyword in text:
            return "🛒 Groceries"
    return "❓ Other"

# ─────────────────────────────────────────────
# PARSERS
# ─────────────────────────────────────────────
def parse_amount(val) -> float:
    if pd.isna(val):
        return 0.0
    s = str(val).replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0

def parse_rogers(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip() for c in df.columns]
    rows = []
    for _, r in df.iterrows():
        raw_amount = parse_amount(r.get("Amount", 0))
        # Rogers: positive = expense, negative = payment/credit
        amount = abs(raw_amount) if raw_amount > 0 else raw_amount
        is_expense = raw_amount > 0
        rows.append({
            "date": pd.to_datetime(r.get("Date", r.get("Posted Date", "")), errors="coerce"),
            "description": str(r.get("Merchant Name", "")).strip(),
            "merchant_category": str(r.get("Merchant Category Description", "")).strip(),
            "amount": amount,
            "is_expense": is_expense,
            "currency": "CAD",
            "source": "Rogers Bank",
            "account": str(r.get("Card Number", "")).strip(),
            "city": str(r.get("Merchant City", "")).strip(),
            "province": str(r.get("Merchant State or Province", "")).strip(),
            "raw_type": str(r.get("Activity Type", "")).strip(),
            "status": str(r.get("Activity Status", "")).strip(),
        })
    out = pd.DataFrame(rows)
    out["category"] = out.apply(lambda x: guess_category(x["merchant_category"], x["description"]), axis=1)
    return out

def parse_wealthsimple(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip() for c in df.columns]
    rows = []
    for _, r in df.iterrows():
        raw_amount = parse_amount(r.get("net_cash_amount", 0))
        # WS: negative = spending, positive = deposit
        amount = abs(raw_amount)
        is_expense = raw_amount < 0
        name = str(r.get("name", "")).strip()
        if not name or name == "nan":
            name = str(r.get("activity_sub_type", r.get("activity_type", ""))).strip()
        rows.append({
            "date": pd.to_datetime(r.get("transaction_date", r.get("settlement_date", "")), errors="coerce"),
            "description": name,
            "merchant_category": str(r.get("activity_sub_type", r.get("activity_type", ""))).strip(),
            "amount": amount,
            "is_expense": is_expense,
            "currency": str(r.get("currency", "CAD")).strip(),
            "source": "Wealthsimple",
            "account": str(r.get("account_id", "")).strip(),
            "city": "",
            "province": "",
            "raw_type": str(r.get("activity_type", "")).strip(),
            "status": "",
        })
    out = pd.DataFrame(rows)
    out["category"] = out.apply(lambda x: guess_category(x["merchant_category"], x["description"]), axis=1)
    # Override common WS types
    out.loc[out["raw_type"].str.upper() == "DIVIDEND", "category"] = "🏦 Banking"
    out.loc[out["raw_type"].str.upper() == "DEPOSIT", "category"] = "💰 Transfers & Fees"
    out.loc[out["raw_type"].str.upper() == "WITHDRAWAL", "category"] = "💰 Transfers & Fees"
    return out

def standardize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(subset=["date"])
    df = df.sort_values("date", ascending=False).reset_index(drop=True)
    df["id"] = df.index
    return df

# ─────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────
if "transactions" not in st.session_state:
    st.session_state.transactions = pd.DataFrame()
if "deleted_ids" not in st.session_state:
    st.session_state.deleted_ids = set()

# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='padding: 0.5rem 0 1rem 0;'>
        <div class='hero-title'>Spend<span>Lens</span></div>
        <div class='hero-sub'>Personal Finance Tracker</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("---")

    st.markdown("<div class='section-label'>📥 Upload Data</div>", unsafe_allow_html=True)

    rogers_file = st.file_uploader(
        "Rogers Bank CSV",
        type=["csv"],
        key="rogers_upload",
        help="Export from Rogers Bank portal as CSV"
    )
    ws_file = st.file_uploader(
        "Wealthsimple CSV",
        type=["csv"],
        key="ws_upload",
        help="Export from Wealthsimple as CSV"
    )

    if st.button("🔄 Process Files", use_container_width=True):
        frames = []
        errors = []

        if rogers_file:
            try:
                rdf = pd.read_csv(rogers_file)
                parsed = parse_rogers(rdf)
                frames.append(parsed)
                st.success(f"Rogers: {len(parsed)} rows loaded")
            except Exception as e:
                errors.append(f"Rogers error: {e}")

        if ws_file:
            try:
                wdf = pd.read_csv(ws_file)
                parsed = parse_wealthsimple(wdf)
                frames.append(parsed)
                st.success(f"Wealthsimple: {len(parsed)} rows loaded")
            except Exception as e:
                errors.append(f"WS error: {e}")

        for err in errors:
            st.error(err)

        if frames:
            combined = pd.concat(frames, ignore_index=True)
            st.session_state.transactions = standardize(combined)
            st.session_state.deleted_ids = set()
            st.rerun()

    st.markdown("---")

    # Filters (only show when data loaded)
    if not st.session_state.transactions.empty:
        df_all = st.session_state.transactions
        df_active = df_all[~df_all["id"].isin(st.session_state.deleted_ids)]

        st.markdown("<div class='section-label'>🔍 Filters</div>", unsafe_allow_html=True)

        sources = ["All"] + sorted(df_active["source"].unique().tolist())
        sel_source = st.selectbox("Source", sources)

        cats = sorted(df_active["category"].unique().tolist())
        sel_cats = st.multiselect("Categories", cats, default=cats)

        min_d = df_active["date"].min().date()
        max_d = df_active["date"].max().date()
        date_range = st.date_input("Date range", value=(min_d, max_d), min_value=min_d, max_value=max_d)

        show_expenses_only = st.checkbox("Expenses only", value=True)

        st.markdown("---")
        if st.button("🗑️ Clear All Data", use_container_width=True):
            st.session_state.transactions = pd.DataFrame()
            st.session_state.deleted_ids = set()
            st.rerun()

# ─────────────────────────────────────────────
# MAIN AREA
# ─────────────────────────────────────────────
if st.session_state.transactions.empty:
    # ── Empty state ──
    st.markdown("""
    <div style='display:flex; flex-direction:column; align-items:center; justify-content:center;
                min-height:70vh; text-align:center; gap:1rem;'>
        <div style='font-size:4rem;'>💳</div>
        <div class='hero-title'>Spend<span style="color:#c8f542">Lens</span></div>
        <div style='color:#6b7a99; font-size:0.85rem; max-width:420px; line-height:1.7;'>
            Upload your <strong style="color:#5b9cf6">Rogers Bank</strong> and 
            <strong style="color:#4ecb71">Wealthsimple</strong> CSV exports in the sidebar
            to get a clear picture of your spending habits.
        </div>
        <div style='margin-top:1rem; padding:1rem 2rem; border:1px dashed #2a3245;
                    border-radius:8px; color:#4a5568; font-size:0.75rem; line-height:1.8;'>
            ✓ &nbsp;Automatic category detection<br>
            ✓ &nbsp;Interactive charts & breakdowns<br>
            ✓ &nbsp;Reclassify & delete transactions<br>
            ✓ &nbsp;Multi-source data standardization
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ── Apply filters ──
df_all = st.session_state.transactions
df_active = df_all[~df_all["id"].isin(st.session_state.deleted_ids)].copy()

if sel_source != "All":
    df_active = df_active[df_active["source"] == sel_source]
if sel_cats:
    df_active = df_active[df_active["category"].isin(sel_cats)]
if len(date_range) == 2:
    start_d, end_d = date_range
    df_active = df_active[(df_active["date"].dt.date >= start_d) & (df_active["date"].dt.date <= end_d)]
if show_expenses_only:
    df_active = df_active[df_active["is_expense"]]

expenses = df_active[df_active["is_expense"]]

# ─────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────
tab_overview, tab_charts, tab_transactions = st.tabs([
    "📊  Overview", "📈  Charts", "📋  Transactions"
])

# ══════════════════════════════════════════════
# TAB 1: OVERVIEW
# ══════════════════════════════════════════════
with tab_overview:
    total_spend = expenses["amount"].sum()
    num_txn = len(expenses)
    avg_txn = expenses["amount"].mean() if num_txn > 0 else 0
    top_cat = expenses.groupby("category")["amount"].sum().idxmax() if num_txn > 0 else "—"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Spend", f"${total_spend:,.2f}")
    c2.metric("Transactions", f"{num_txn}")
    c3.metric("Avg Transaction", f"${avg_txn:,.2f}")
    c4.metric("Top Category", top_cat.split(" ", 1)[-1] if top_cat != "—" else "—")

    st.markdown("---")

    col_l, col_r = st.columns([1, 1])

    with col_l:
        st.markdown("<div class='section-label'>Spending by Category</div>", unsafe_allow_html=True)
        if not expenses.empty:
            cat_summary = (
                expenses.groupby("category")["amount"]
                .sum()
                .sort_values(ascending=False)
                .reset_index()
            )
            cat_summary["color"] = cat_summary["category"].map(
                lambda c: CATEGORY_COLORS.get(c, "#6b7280")
            )
            fig = px.bar(
                cat_summary,
                x="amount",
                y="category",
                orientation="h",
                color="category",
                color_discrete_map=CATEGORY_COLORS,
                text=cat_summary["amount"].apply(lambda x: f"${x:,.0f}"),
            )
            fig.update_traces(textposition="outside", marker_line_width=0)
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#e8e4da",
                font_family="DM Mono",
                showlegend=False,
                yaxis=dict(autorange="reversed", gridcolor="#1f2535", title=""),
                xaxis=dict(gridcolor="#1f2535", title="Amount (CAD)", tickprefix="$"),
                margin=dict(l=10, r=80, t=10, b=10),
                height=380,
            )
            st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.markdown("<div class='section-label'>Category Share</div>", unsafe_allow_html=True)
        if not expenses.empty:
            fig2 = px.pie(
                cat_summary,
                values="amount",
                names="category",
                color="category",
                color_discrete_map=CATEGORY_COLORS,
                hole=0.55,
            )
            fig2.update_traces(
                textinfo="percent",
                textfont_size=11,
                marker=dict(line=dict(color="#0d0f14", width=2)),
            )
            fig2.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#e8e4da",
                font_family="DM Mono",
                showlegend=True,
                legend=dict(font=dict(size=10), orientation="v"),
                margin=dict(l=10, r=10, t=10, b=10),
                height=380,
            )
            st.plotly_chart(fig2, use_container_width=True)

    # Source breakdown
    st.markdown("<div class='section-label'>Source Breakdown</div>", unsafe_allow_html=True)
    src_cols = st.columns(len(expenses["source"].unique()) if not expenses.empty else 1)
    for i, (src, grp) in enumerate(expenses.groupby("source")):
        badge = "pill-rogers" if "Rogers" in src else "pill-ws"
        with src_cols[i]:
            st.markdown(f"""
            <div style='background:#131720; border:1px solid #1f2535; border-radius:8px;
                        padding:1rem; text-align:center;'>
                <div class='pill {badge}'>{src}</div>
                <div style='font-family:Syne,sans-serif; font-size:1.8rem; color:#c8f542;
                            margin-top:0.5rem;'>${grp["amount"].sum():,.2f}</div>
                <div style='color:#6b7a99; font-size:0.72rem;'>{len(grp)} transactions</div>
            </div>
            """, unsafe_allow_html=True)

# ══════════════════════════════════════════════
# TAB 2: CHARTS
# ══════════════════════════════════════════════
with tab_charts:
    if expenses.empty:
        st.info("No expense data to chart with current filters.")
    else:
        # Monthly trend
        st.markdown("<div class='section-label'>Monthly Spending Trend</div>", unsafe_allow_html=True)
        monthly = (
            expenses.copy()
            .assign(month=lambda d: d["date"].dt.to_period("M").astype(str))
            .groupby(["month", "category"])["amount"]
            .sum()
            .reset_index()
        )
        fig_trend = px.bar(
            monthly,
            x="month",
            y="amount",
            color="category",
            color_discrete_map=CATEGORY_COLORS,
            barmode="stack",
        )
        fig_trend.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#e8e4da",
            font_family="DM Mono",
            xaxis=dict(gridcolor="#1f2535", title="Month"),
            yaxis=dict(gridcolor="#1f2535", title="Amount (CAD)", tickprefix="$"),
            legend=dict(font=dict(size=10)),
            margin=dict(l=10, r=10, t=10, b=10),
            height=340,
        )
        st.plotly_chart(fig_trend, use_container_width=True)

        col_a, col_b = st.columns(2)

        with col_a:
            # Weekday heatmap
            st.markdown("<div class='section-label'>Spending by Day of Week</div>", unsafe_allow_html=True)
            dow = expenses.copy()
            dow["weekday"] = dow["date"].dt.day_name()
            dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            dow_sum = dow.groupby("weekday")["amount"].sum().reindex(dow_order).fillna(0).reset_index()
            fig_dow = px.bar(
                dow_sum,
                x="weekday",
                y="amount",
                color="amount",
                color_continuous_scale=["#1f2535", "#c8f542"],
                text=dow_sum["amount"].apply(lambda x: f"${x:,.0f}"),
            )
            fig_dow.update_traces(textposition="outside")
            fig_dow.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#e8e4da",
                font_family="DM Mono",
                xaxis=dict(gridcolor="#1f2535", title=""),
                yaxis=dict(gridcolor="#1f2535", title="", tickprefix="$"),
                coloraxis_showscale=False,
                margin=dict(l=10, r=10, t=10, b=10),
                height=300,
            )
            st.plotly_chart(fig_dow, use_container_width=True)

        with col_b:
            # Top merchants
            st.markdown("<div class='section-label'>Top 10 Merchants</div>", unsafe_allow_html=True)
            top_merch = (
                expenses.groupby("description")["amount"]
                .sum()
                .sort_values(ascending=False)
                .head(10)
                .reset_index()
            )
            fig_merch = px.bar(
                top_merch,
                x="amount",
                y="description",
                orientation="h",
                color="amount",
                color_continuous_scale=["#1f2535", "#5b9cf6"],
                text=top_merch["amount"].apply(lambda x: f"${x:,.0f}"),
            )
            fig_merch.update_traces(textposition="outside")
            fig_merch.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#e8e4da",
                font_family="DM Mono",
                yaxis=dict(autorange="reversed", gridcolor="#1f2535", title=""),
                xaxis=dict(gridcolor="#1f2535", title="", tickprefix="$"),
                coloraxis_showscale=False,
                margin=dict(l=10, r=80, t=10, b=10),
                height=300,
            )
            st.plotly_chart(fig_merch, use_container_width=True)

        # Rolling 7-day
        st.markdown("<div class='section-label'>Daily Spend (7-day Rolling Avg)</div>", unsafe_allow_html=True)
        daily = expenses.groupby("date")["amount"].sum().reset_index().sort_values("date")
        daily["rolling"] = daily["amount"].rolling(7, min_periods=1).mean()
        fig_roll = go.Figure()
        fig_roll.add_trace(go.Bar(
            x=daily["date"], y=daily["amount"],
            name="Daily", marker_color="#1f2535", opacity=0.7
        ))
        fig_roll.add_trace(go.Scatter(
            x=daily["date"], y=daily["rolling"],
            name="7-day avg", line=dict(color="#c8f542", width=2)
        ))
        fig_roll.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#e8e4da",
            font_family="DM Mono",
            xaxis=dict(gridcolor="#1f2535"),
            yaxis=dict(gridcolor="#1f2535", tickprefix="$"),
            legend=dict(font=dict(size=10)),
            margin=dict(l=10, r=10, t=10, b=10),
            height=280,
        )
        st.plotly_chart(fig_roll, use_container_width=True)

# ══════════════════════════════════════════════
# TAB 3: TRANSACTIONS
# ══════════════════════════════════════════════
with tab_transactions:
    st.markdown(
        f"<div class='section-label'>{len(df_active)} transactions — select rows to reclassify or delete</div>",
        unsafe_allow_html=True
    )

    # Search
    search = st.text_input("🔍 Search description", placeholder="e.g. Tim Hortons, Uber…", label_visibility="collapsed")
    if search:
        df_active = df_active[df_active["description"].str.contains(search, case=False, na=False)]

    # Build display df
    display_df = df_active[[
        "id", "date", "description", "merchant_category", "category",
        "amount", "is_expense", "currency", "source", "account", "city"
    ]].copy()
    display_df["date"] = display_df["date"].dt.strftime("%Y-%m-%d")
    display_df["amount_fmt"] = display_df.apply(
        lambda r: f"{'−' if r['is_expense'] else '+'} ${r['amount']:,.2f} {r['currency']}", axis=1
    )
    display_df = display_df.drop(columns=["is_expense", "currency"])

    # Editable table for reclassification
    edited = st.data_editor(
        display_df.drop(columns=["id", "amount"]),
        column_config={
            "date":              st.column_config.TextColumn("Date", width="small"),
            "description":       st.column_config.TextColumn("Description", width="medium"),
            "merchant_category": st.column_config.TextColumn("Raw Category", width="medium"),
            "category":          st.column_config.SelectboxColumn(
                "Category",
                options=list(CATEGORY_COLORS.keys()),
                width="medium",
                required=True,
            ),
            "amount_fmt":        st.column_config.TextColumn("Amount", width="small"),
            "source":            st.column_config.TextColumn("Source", width="small"),
            "account":           st.column_config.TextColumn("Account", width="small"),
            "city":              st.column_config.TextColumn("City", width="small"),
        },
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        height=500,
        key="txn_editor",
    )

    col_save, col_del, col_export, _ = st.columns([1.2, 1.2, 1.2, 4])

    with col_save:
        if st.button("💾 Save Changes"):
            # Merge edited categories back
            edited_ids = display_df["id"].values
            new_cats = edited["category"].values
            for tid, cat in zip(edited_ids, new_cats):
                st.session_state.transactions.loc[
                    st.session_state.transactions["id"] == tid, "category"
                ] = cat
            st.success("Categories updated!")
            st.rerun()

    with col_del:
        if st.button("🗑️ Delete Shown"):
            ids_to_del = set(display_df["id"].values)
            st.session_state.deleted_ids.update(ids_to_del)
            st.warning(f"Deleted {len(ids_to_del)} transactions.")
            st.rerun()

    with col_export:
        if st.button("📤 Export CSV"):
            df_export = st.session_state.transactions[
                ~st.session_state.transactions["id"].isin(st.session_state.deleted_ids)
            ]
            csv_bytes = df_export.to_csv(index=False).encode()
            st.download_button(
                "⬇️ Download",
                data=csv_bytes,
                file_name=f"transactions_{datetime.today().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )

    # Restore deleted
    if st.session_state.deleted_ids:
        st.markdown("---")
        if st.button(f"↩️ Restore {len(st.session_state.deleted_ids)} deleted transaction(s)"):
            st.session_state.deleted_ids = set()
            st.rerun()

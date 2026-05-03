import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, timedelta
import calendar

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Mortgage Payoff Calculator",
    page_icon="🏡",
    layout="wide",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');

:root {
    --ink:    #1a1a2e;
    --paper:  #f5f0e8;
    --cream:  #ede8dc;
    --gold:   #c9922a;
    --rust:   #b85c2a;
    --sage:   #4a7c59;
    --muted:  #7a7060;
    --card:   #faf7f2;
    --border: #d8d0c0;
}

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    background-color: var(--paper);
    color: var(--ink);
}

/* Header */
.hero {
    background: var(--ink);
    border-radius: 16px;
    padding: 2.5rem 3rem;
    margin-bottom: 2rem;
    position: relative;
    overflow: hidden;
}
.hero::before {
    content: '🏡';
    font-size: 8rem;
    position: absolute;
    right: 2rem;
    top: 50%;
    transform: translateY(-50%);
    opacity: 0.08;
}
.hero h1 {
    font-family: 'DM Serif Display', serif;
    font-size: 2.6rem;
    color: #f5f0e8;
    margin: 0 0 0.5rem 0;
    letter-spacing: -0.02em;
}
.hero p {
    color: #a09880;
    font-size: 1.05rem;
    margin: 0;
    font-weight: 300;
}

/* Section headers */
.section-label {
    font-family: 'DM Sans', sans-serif;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--gold);
    margin-bottom: 1rem;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid var(--border);
}

/* Metric cards */
.metric-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.4rem 1.6rem;
    height: 100%;
}
.metric-card .label {
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 0.4rem;
}
.metric-card .value {
    font-family: 'DM Serif Display', serif;
    font-size: 2rem;
    color: var(--ink);
    line-height: 1.1;
}
.metric-card .sub {
    font-size: 0.82rem;
    color: var(--muted);
    margin-top: 0.3rem;
}
.metric-card.highlight {
    background: var(--ink);
    border-color: var(--ink);
}
.metric-card.highlight .label { color: #807060; }
.metric-card.highlight .value { color: #f5f0e8; }
.metric-card.highlight .sub   { color: #a09880; }
.metric-card.savings {
    background: linear-gradient(135deg, #2a4a35 0%, #1a3328 100%);
    border-color: #3a6045;
}
.metric-card.savings .label { color: #6a9a78; }
.metric-card.savings .value { color: #a8dab5; }
.metric-card.savings .sub   { color: #6a9a78; }

/* Streamlit overrides */
div[data-testid="stMetricValue"] {
    font-family: 'DM Serif Display', serif !important;
}
div[data-testid="stNumberInput"] label,
div[data-testid="stSelectbox"] label,
div[data-testid="stDateInput"] label,
div[data-testid="stSlider"] label {
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    color: var(--muted) !important;
}

.stDataFrame { border-radius: 10px; overflow: hidden; }

/* Sidebar */
section[data-testid="stSidebar"] {
    background: var(--cream) !important;
    border-right: 1px solid var(--border);
}
section[data-testid="stSidebar"] .block-container {
    padding-top: 2rem;
}

div[data-testid="stExpander"] {
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
    background: var(--card) !important;
}
</style>
""", unsafe_allow_html=True)


# ── Helper functions ──────────────────────────────────────────────────────────

def periods_per_year(schedule: str) -> float:
    return {"Monthly": 12, "Bi-weekly": 26, "Accelerated Bi-weekly": 26, "Weekly": 52, "Accelerated Weekly": 52}[schedule]

def base_payment(principal: float, annual_rate: float, amort_years: int, schedule: str) -> float:
    """Calculate the regular payment for a given schedule."""
    n = periods_per_year(schedule)
    r = annual_rate / n

    if schedule == "Accelerated Bi-weekly":
        # Take monthly payment and divide by 2 (results in one extra monthly payment/year)
        r_m = annual_rate / 12
        n_m = amort_years * 12
        monthly = principal * r_m * (1 + r_m)**n_m / ((1 + r_m)**n_m - 1)
        return monthly / 2

    if schedule == "Accelerated Weekly":
        r_m = annual_rate / 12
        n_m = amort_years * 12
        monthly = principal * r_m * (1 + r_m)**n_m / ((1 + r_m)**n_m - 1)
        return monthly / 4

    if r == 0:
        return principal / (amort_years * n)

    total_periods = amort_years * n
    pmt = principal * r * (1 + r)**total_periods / ((1 + r)**total_periods - 1)
    return pmt


def amortize(principal: float, annual_rate: float, payment: float,
             schedule: str, extra_per_period: float,
             extra_lump_sums: list,          # [(period_number, amount), ...]
             start_date: date) -> pd.DataFrame:
    """Run full amortization, return DataFrame."""
    n = periods_per_year(schedule)
    r = annual_rate / n

    balance = principal
    records = []
    period = 0
    current_date = start_date
    total_interest = 0.0
    total_principal = 0.0

    lump_map = {}
    for (pd_no, amt) in extra_lump_sums:
        lump_map[pd_no] = lump_map.get(pd_no, 0) + amt

    while balance > 0.01:
        period += 1
        interest = balance * r
        lump = lump_map.get(period, 0)
        total_payment = payment + extra_per_period + lump
        principal_paid = min(total_payment - interest, balance)
        total_payment = principal_paid + interest
        balance = max(balance - principal_paid, 0)
        total_interest += interest
        total_principal += principal_paid

        records.append({
            "Period": period,
            "Date": current_date,
            "Payment": round(total_payment, 2),
            "Principal": round(principal_paid, 2),
            "Interest": round(interest, 2),
            "Extra": round(extra_per_period + lump, 2),
            "Balance": round(balance, 2),
            "Cum. Interest": round(total_interest, 2),
        })

        # Advance date
        if schedule in ("Monthly",):
            month = current_date.month + 1
            year = current_date.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            day = min(current_date.day, calendar.monthrange(year, month)[1])
            current_date = date(year, month, day)
        elif schedule in ("Bi-weekly", "Accelerated Bi-weekly"):
            current_date += timedelta(weeks=2)
        else:  # Weekly / Accelerated Weekly
            current_date += timedelta(weeks=1)

        if period > 100_000:  # safety
            break

    return pd.DataFrame(records)


def years_months_str(total_periods: int, schedule: str) -> str:
    n = periods_per_year(schedule)
    total_months = total_periods / n * 12
    y = int(total_months // 12)
    m = int(round(total_months % 12))
    if m == 12:
        y += 1; m = 0
    parts = []
    if y: parts.append(f"{y} yr{'s' if y != 1 else ''}")
    if m: parts.append(f"{m} mo{'s' if m != 1 else ''}")
    return " ".join(parts) if parts else "< 1 month"


# ── UI ────────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="hero">
  <h1>Mortgage Payoff Calculator</h1>
  <p>See how extra payments can save you years and thousands in interest.</p>
</div>
""", unsafe_allow_html=True)

# Sidebar — mortgage details
with st.sidebar:
    st.markdown('<div class="section-label">Mortgage Details</div>', unsafe_allow_html=True)

    purchase_price = st.number_input("Home Purchase Price ($)", min_value=50_000, max_value=10_000_000,
                                      value=600_000, step=5_000, format="%d")
    down_payment = st.number_input("Down Payment ($)", min_value=0, max_value=int(purchase_price),
                                    value=int(purchase_price * 0.20), step=5_000, format="%d")
    annual_rate = st.number_input("Annual Interest Rate (%)", min_value=0.1, max_value=20.0,
                                   value=5.25, step=0.05, format="%.2f") / 100
    amort_years = st.selectbox("Amortization Period", [10, 15, 20, 25, 30], index=3)
    schedule = st.selectbox("Payment Schedule",
                            ["Monthly", "Bi-weekly", "Accelerated Bi-weekly", "Weekly", "Accelerated Weekly"],
                            index=2)
    start_date = st.date_input("Mortgage Start Date", value=date.today())

    st.markdown('<div class="section-label" style="margin-top:1.5rem;">Extra Payments</div>', unsafe_allow_html=True)

    extra_per_period = st.number_input("Extra Payment Each Period ($)", min_value=0, max_value=50_000,
                                        value=200, step=50, format="%d")

    with st.expander("➕ Add Lump-Sum Payments"):
        n_lump = st.number_input("Number of lump-sum payments", min_value=0, max_value=10, value=0, step=1)
        lump_sums = []
        for i in range(int(n_lump)):
            c1, c2 = st.columns(2)
            with c1:
                lp = st.number_input(f"Period #{i+1}", min_value=1, value=12*(i+1), key=f"lp_{i}")
            with c2:
                la = st.number_input(f"Amount ($)", min_value=0, value=5000, step=500, key=f"la_{i}", format="%d")
            lump_sums.append((lp, la))


# ── Calculations ──────────────────────────────────────────────────────────────

principal = purchase_price - down_payment
dp_pct = down_payment / purchase_price * 100

pmt_base = base_payment(principal, annual_rate, amort_years, schedule)
pmt_extra = pmt_base  # same payment, just adding extra

# Baseline (no extras)
df_base = amortize(principal, annual_rate, pmt_base, schedule, 0, [], start_date)
# With extras
df_extra = amortize(principal, annual_rate, pmt_base, schedule, extra_per_period, lump_sums, start_date)

base_periods   = len(df_base)
extra_periods  = len(df_extra)
periods_saved  = base_periods - extra_periods
base_interest  = df_base["Cum. Interest"].iloc[-1]
extra_interest = df_extra["Cum. Interest"].iloc[-1]
interest_saved = base_interest - extra_interest
time_saved_str = years_months_str(periods_saved, schedule)
payoff_date    = df_extra["Date"].iloc[-1]
base_payoff    = df_base["Date"].iloc[-1]

n = periods_per_year(schedule)

# ── Results area ─────────────────────────────────────────────────────────────

c1, c2, c3 = st.columns(3)
with c1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="label">Loan Amount</div>
        <div class="value">${principal:,.0f}</div>
        <div class="sub">{dp_pct:.1f}% down · ${purchase_price:,.0f} purchase</div>
    </div>""", unsafe_allow_html=True)

with c2:
    st.markdown(f"""
    <div class="metric-card highlight">
        <div class="label">Regular Payment</div>
        <div class="value">${pmt_base:,.2f}</div>
        <div class="sub">{schedule} · {amort_years}-yr amortization</div>
    </div>""", unsafe_allow_html=True)

with c3:
    total_extra_annual = extra_per_period * n + sum(a for _, a in lump_sums)
    st.markdown(f"""
    <div class="metric-card">
        <div class="label">Extra / Year</div>
        <div class="value">${total_extra_annual:,.0f}</div>
        <div class="sub">${extra_per_period:,.0f} per period + {len(lump_sums)} lump sum(s)</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# Savings row
c4, c5, c6, c7 = st.columns(4)
with c4:
    st.markdown(f"""
    <div class="metric-card savings">
        <div class="label">Time Saved</div>
        <div class="value">{time_saved_str if periods_saved > 0 else "—"}</div>
        <div class="sub">{periods_saved} fewer {schedule.lower()} payments</div>
    </div>""", unsafe_allow_html=True)

with c5:
    st.markdown(f"""
    <div class="metric-card savings">
        <div class="label">Interest Saved</div>
        <div class="value">${interest_saved:,.0f}</div>
        <div class="sub">vs. ${base_interest:,.0f} baseline total</div>
    </div>""", unsafe_allow_html=True)

with c6:
    st.markdown(f"""
    <div class="metric-card">
        <div class="label">Payoff Date</div>
        <div class="value">{payoff_date.strftime("%b %Y")}</div>
        <div class="sub">Baseline: {base_payoff.strftime("%b %Y")}</div>
    </div>""", unsafe_allow_html=True)

with c7:
    pct_saved = interest_saved / base_interest * 100 if base_interest > 0 else 0
    st.markdown(f"""
    <div class="metric-card">
        <div class="label">Interest Reduction</div>
        <div class="value">{pct_saved:.1f}%</div>
        <div class="sub">of total interest eliminated</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Charts ───────────────────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs(["📉 Balance Over Time", "💸 Interest Accumulation", "📋 Amortization Table"])

with tab1:
    chart_data = pd.DataFrame({
        "Period": df_base["Period"],
        "No Extra Payments": df_base["Balance"],
    }).set_index("Period")

    # Align extra df to same index (may be shorter)
    extra_series = df_extra[["Period", "Balance"]].set_index("Period")["Balance"]
    chart_data["With Extra Payments"] = extra_series
    chart_data = chart_data.fillna(0)

    st.line_chart(chart_data, height=360, use_container_width=True,
                  color=["#c9922a", "#4a7c59"])
    st.caption(f"Balance reaches $0 in period {extra_periods} (with extras) vs {base_periods} (baseline)")

with tab2:
    cum_data = pd.DataFrame({
        "Period": df_base["Period"],
        "No Extra Payments": df_base["Cum. Interest"],
    }).set_index("Period")
    extra_cum = df_extra[["Period", "Cum. Interest"]].set_index("Period")["Cum. Interest"]
    cum_data["With Extra Payments"] = extra_cum
    cum_data = cum_data.ffill()

    st.line_chart(cum_data, height=360, use_container_width=True,
                  color=["#b85c2a", "#4a7c59"])
    st.caption(f"Total interest: ${extra_interest:,.0f} (with extras) vs ${base_interest:,.0f} (baseline) — saving ${interest_saved:,.0f}")

with tab3:
    display_cols = ["Period", "Date", "Payment", "Principal", "Interest", "Extra", "Balance", "Cum. Interest"]
    df_show = df_extra[display_cols].copy()
    df_show["Date"] = df_show["Date"].astype(str)
    for col in ["Payment", "Principal", "Interest", "Extra", "Balance", "Cum. Interest"]:
        df_show[col] = df_show[col].map("${:,.2f}".format)

    st.dataframe(df_show, use_container_width=True, height=420,
                 hide_index=True,
                 column_config={
                     "Period": st.column_config.NumberColumn("Period", width="small"),
                     "Balance": st.column_config.TextColumn("Remaining Balance"),
                 })

# ── Footer tip ────────────────────────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
st.info(
    f"💡 **Tip:** Your {schedule.lower()} payment is **${pmt_base:,.2f}**. "
    f"Adding just **${extra_per_period:,.0f}** extra each period saves you **${interest_saved:,.0f}** "
    f"in interest and pays off your mortgage **{time_saved_str}** sooner.",
    icon=None
)

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import date, datetime
import calendar
import json

# ─── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Debt & Investment Simulator",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Syne', sans-serif;
}

.main {
    background: #0a0e1a;
    color: #e8eaf0;
}

.stApp {
    background: linear-gradient(135deg, #0a0e1a 0%, #0d1422 50%, #0a0e1a 100%);
}

h1, h2, h3 {
    font-family: 'Syne', sans-serif;
    font-weight: 800;
}

.metric-card {
    background: linear-gradient(135deg, #131929 0%, #1a2236 100%);
    border: 1px solid #2a3550;
    border-radius: 12px;
    padding: 20px;
    margin: 8px 0;
}

.month-header {
    background: linear-gradient(90deg, #1e3a5f 0%, #162c4a 100%);
    border-left: 4px solid #4dabf7;
    border-radius: 8px;
    padding: 12px 20px;
    margin: 16px 0 8px 0;
    font-family: 'Space Mono', monospace;
    font-weight: 700;
    font-size: 1.1em;
    color: #4dabf7;
}

.car-paid {
    background: linear-gradient(90deg, #1a3a2a 0%, #122a1e 100%);
    border-left: 4px solid #51cf66;
    border-radius: 8px;
    padding: 12px 20px;
    margin: 8px 0;
    color: #51cf66;
    font-weight: 700;
}

.stMetric {
    background: #131929;
    border-radius: 10px;
    padding: 12px;
    border: 1px solid #2a3550;
}

.stMetric label {
    color: #7c90b0 !important;
    font-size: 0.8em !important;
    font-family: 'Space Mono', monospace !important;
}

.stMetric [data-testid="metric-container"] {
    color: #e8eaf0;
}

div[data-testid="metric-container"] {
    background: #131929;
    border-radius: 10px;
    padding: 12px 16px;
    border: 1px solid #2a3550;
}

.stNumberInput input, .stSelectbox select, .stSlider {
    background: #131929 !important;
    color: #e8eaf0 !important;
    border-color: #2a3550 !important;
}

.stButton > button {
    background: linear-gradient(135deg, #1c6ef3 0%, #1557d4 100%);
    color: white;
    border: none;
    border-radius: 8px;
    font-family: 'Space Mono', monospace;
    font-weight: 700;
    letter-spacing: 0.05em;
    padding: 10px 24px;
    transition: all 0.2s;
}

.stButton > button:hover {
    background: linear-gradient(135deg, #2980ff 0%, #1c6ef3 100%);
    transform: translateY(-1px);
    box-shadow: 0 4px 20px rgba(28, 110, 243, 0.4);
}

.stExpander {
    background: #131929;
    border: 1px solid #2a3550;
    border-radius: 10px;
}

.sidebar .stNumberInput label, .sidebar .stSlider label, .sidebar .stSelectbox label {
    color: #7c90b0;
    font-size: 0.85em;
}

.info-box {
    background: #0f1e33;
    border: 1px solid #1c3a5e;
    border-radius: 8px;
    padding: 14px;
    font-family: 'Space Mono', monospace;
    font-size: 0.82em;
    color: #7c90b0;
    margin: 8px 0;
}

.highlight-green { color: #51cf66; font-weight: 700; }
.highlight-blue { color: #4dabf7; font-weight: 700; }
.highlight-orange { color: #ffa94d; font-weight: 700; }
.highlight-red { color: #ff6b6b; font-weight: 700; }

.section-title {
    font-family: 'Space Mono', monospace;
    font-size: 0.75em;
    letter-spacing: 0.15em;
    color: #4dabf7;
    text-transform: uppercase;
    margin: 20px 0 10px 0;
    border-bottom: 1px solid #2a3550;
    padding-bottom: 6px;
}
</style>
""", unsafe_allow_html=True)

# ─── Constants ────────────────────────────────────────────────────────────────
MORTGAGE_RATE_ANNUAL = 0.054
CAR_RATE_ANNUAL = 0.068
MORTGAGE_WEEKLY_PAYMENT = 441.0
CAR_BIWEEKLY_PAYMENT = 242.0

START_MONTH = date(2026, 5, 1)

MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

# ─── Session State Init ───────────────────────────────────────────────────────
def init_state():
    if "sim_data" not in st.session_state:
        st.session_state.sim_data = []
    if "overrides" not in st.session_state:
        st.session_state.overrides = {}       # month_key -> {bonus} only
    if "invest_pct_overrides" not in st.session_state:
        st.session_state.invest_pct_overrides = {}  # month_key -> float (cascades forward)
    if "savings_overrides" not in st.session_state:
        st.session_state.savings_overrides = {}     # month_key -> float (cascades forward)
    if "sim_months" not in st.session_state:
        st.session_state.sim_months = 120
    if "inv_rate" not in st.session_state:
        st.session_state.inv_rate = 7.0

init_state()

def resolve_invest_pct(mk, total_months):
    """Return the effective invest_pct for a month key, cascading from the most recent override."""
    ip_overrides = st.session_state.invest_pct_overrides
    # Walk back through all months up to and including mk to find last explicit override
    effective = 50.0
    for i in range(total_months):
        d = month_key(i)
        k = d.isoformat()
        if k in ip_overrides:
            effective = ip_overrides[k]
        if k == mk:
            break
    return effective

def is_invest_pct_overridden(mk):
    """True only if this specific month has an explicit override (not inherited)."""
    return mk in st.session_state.invest_pct_overrides

# ─── Finance Logic ────────────────────────────────────────────────────────────
def weeks_in_month(year, month):
    """Approximate weekly payments per month (52/12)"""
    return 52 / 12

def biweeks_in_month(year, month):
    return 26 / 12

def month_key(idx):
    """Return date for month index 0=May2026"""
    y = START_MONTH.year + (START_MONTH.month - 1 + idx) // 12
    m = (START_MONTH.month - 1 + idx) % 12 + 1
    return date(y, m, 1)

def month_label(idx):
    d = month_key(idx)
    return f"{MONTHS[d.month-1]} {d.year}"

def run_simulation(total_months, overrides, inv_rate_annual):
    mortgage_bal = 275000.0
    car_bal = 30000.0
    investment_bal = 72000
    car_paid_month = None

    # Monthly rates
    mort_rate_m = MORTGAGE_RATE_ANNUAL / 12
    car_rate_m = CAR_RATE_ANNUAL / 12
    inv_rate_m = inv_rate_annual / 100 / 12

    # Pre-compute cascaded invest_pct for every month index
    cascaded_invest_pct = {}
    effective_pct = 71
    for i in range(total_months):
        d = month_key(i)
        mk = d.isoformat()
        if mk in st.session_state.invest_pct_overrides:
            effective_pct = st.session_state.invest_pct_overrides[mk]
        cascaded_invest_pct[i] = effective_pct

    # Pre-compute cascaded savings for every month index
    cascaded_savings = {}
    effective_savings = 3000.0
    for i in range(total_months):
        d = month_key(i)
        mk = d.isoformat()
        if mk in st.session_state.savings_overrides:
            effective_savings = st.session_state.savings_overrides[mk]
        cascaded_savings[i] = effective_savings

    results = []

    for i in range(total_months):
        d = month_key(i)
        mk = d.isoformat()

        ov = overrides.get(mk, {})
        savings = cascaded_savings[i]
        bonus = ov.get("bonus", 10000.0 if d.month == 4 else 0.0)
        invest_pct = cascaded_invest_pct[i]

        # After the car is paid off, add the freed-up car payment to available cash
        car_payment_monthly = CAR_BIWEEKLY_PAYMENT * (26 / 12)
        car_freed = car_payment_monthly if car_bal == 0 else 0.0

        total_available = savings + bonus + car_freed

        # ── Mortgage scheduled payments ──
        mort_payments_month = MORTGAGE_WEEKLY_PAYMENT * (52 / 12)
        mort_interest = mortgage_bal * mort_rate_m
        mort_principal = min(mort_payments_month - mort_interest, mortgage_bal)
        if mort_principal < 0:
            mort_principal = 0

        # ── Car scheduled payments ──
        car_payments_month = CAR_BIWEEKLY_PAYMENT * (26 / 12)
        car_interest = car_bal * car_rate_m if car_bal > 0 else 0
        car_principal = min(car_payments_month - car_interest, car_bal) if car_bal > 0 else 0
        if car_principal < 0:
            car_principal = 0

        car_extra = 0.0
        mort_extra = 0.0
        invested = 0.0

        if car_bal > 0:
            # All savings go to car first
            car_extra = min(total_available, max(0, car_bal - car_principal))
            leftover = total_available - car_extra
            # Any leftover after car payoff uses the invest_pct split
            if leftover > 0:
                mort_extra = min(leftover * (1 - invest_pct / 100), mortgage_bal)
                invested = leftover * (invest_pct / 100)
        else:
            # Car is paid off — split between mortgage and investments
            mort_extra = min(total_available * (1 - invest_pct / 100), mortgage_bal)
            invested = total_available * (invest_pct / 100)

        # ── Apply payments ──
        mortgage_bal = max(0, mortgage_bal - (mort_principal + mort_extra))

        if car_bal > 0:
            car_bal = max(0, car_bal - (car_principal + car_extra))
            if car_bal == 0 and car_paid_month is None:
                car_paid_month = i

        # ── Investment growth ──
        investment_bal = investment_bal * (1 + inv_rate_m) + invested

        results.append({
            "idx": i,
            "date": d,
            "label": month_label(i),
            "mortgage_bal": mortgage_bal,
            "car_bal": car_bal,
            "investment_bal": investment_bal,
            "mort_interest": mort_interest,
            "car_interest": car_interest,
            "mort_principal": mort_principal,
            "mort_extra": mort_extra,
            "car_principal": car_principal,
            "car_extra": car_extra,
            "invested": invested,
            "savings_used": savings,
            "bonus": bonus,
            "invest_pct": invest_pct,
            "invest_pct_is_override": mk in st.session_state.invest_pct_overrides,
            "savings_is_override": mk in st.session_state.savings_overrides,
            "car_paid_month": car_paid_month,
            "total_available": total_available,
        })

        if mortgage_bal == 0 and car_bal == 0:
            break

    return results

# ─── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Settings")
    st.markdown('<div class="section-title">Simulation Range</div>', unsafe_allow_html=True)
    sim_months = st.slider("Months to simulate", 12, 120, st.session_state.sim_months, 12)
    st.session_state.sim_months = sim_months

    st.markdown('<div class="section-title">Investment Return</div>', unsafe_allow_html=True)
    inv_rate = st.number_input("Annual return (%)", value=st.session_state.inv_rate, min_value=0.0, max_value=20.0, step=0.5)
    st.session_state.inv_rate = inv_rate

    st.markdown('<div class="section-title">Loan Details</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="info-box">
    🏠 <span class="highlight-blue">Mortgage</span><br>
    Balance: $275,000<br>
    Rate: 5.4% | $441/wk<br><br>
    🚗 <span class="highlight-orange">Car Loan</span><br>
    Balance: $30,000<br>
    Rate: 6.8% | $242/biweek
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">Quick Reset</div>', unsafe_allow_html=True)
    if st.button("🔄 Reset All Overrides"):
        st.session_state.overrides = {}
        st.session_state.invest_pct_overrides = {}
        st.session_state.savings_overrides = {}
        st.rerun()

# ─── Run simulation ───────────────────────────────────────────────────────────
results = run_simulation(sim_months, st.session_state.overrides, inv_rate)

# ─── Header ──────────────────────────────────────────────────────────────────
st.markdown("# 💰 Debt & Investment Simulator")
st.markdown(f"*Starting May 2026 · {sim_months} month projection*")

# ─── Summary Metrics ─────────────────────────────────────────────────────────
last = results[-1]
first = results[0]

# Find car payoff
car_payoff_label = "Not paid off"
car_payoff_idx = None
for r in results:
    if r["car_bal"] == 0 and car_payoff_idx is None:
        car_payoff_idx = r["idx"]
        car_payoff_label = r["label"]

# Mortgage payoff
mort_payoff_label = "Not paid off"
for r in results:
    if r["mortgage_bal"] == 0:
        mort_payoff_label = r["label"]
        break

total_interest = sum(r["mort_interest"] + r["car_interest"] for r in results)
total_invested = sum(r["invested"] for r in results)

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("🏠 Mortgage Balance", f"${last['mortgage_bal']:,.0f}", 
              delta=f"-${275000 - last['mortgage_bal']:,.0f}")
with col2:
    st.metric("🚗 Car Balance", f"${last['car_bal']:,.0f}",
              delta=f"Paid off {car_payoff_label}" if last["car_bal"] == 0 else f"-${30000 - last['car_bal']:,.0f}")
with col3:
    st.metric("📈 Investment Portfolio", f"${last['investment_bal']:,.0f}",
              delta=f"+${last['investment_bal'] - total_invested:,.0f} growth")
with col4:
    st.metric("💸 Total Interest Paid", f"${total_interest:,.0f}")
with col5:
    st.metric("🎯 Car Payoff", car_payoff_label)

st.divider()

# ─── Charts ──────────────────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["📊 Charts", "📅 Month-by-Month Editor"])

with tab1:
    labels = [r["label"] for r in results]
    
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=("Debt Balances Over Time", "Investment Portfolio Growth",
                        "Monthly Interest Paid", "Monthly Cash Allocation"),
        vertical_spacing=0.12,
        horizontal_spacing=0.08,
    )

    # Debt balances
    fig.add_trace(go.Scatter(
        x=labels, y=[r["mortgage_bal"] for r in results],
        name="Mortgage", line=dict(color="#4dabf7", width=2.5),
        fill="tozeroy", fillcolor="rgba(77,171,247,0.08)"
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=labels, y=[r["car_bal"] for r in results],
        name="Car Loan", line=dict(color="#ffa94d", width=2.5),
        fill="tozeroy", fillcolor="rgba(255,169,77,0.1)"
    ), row=1, col=1)

    # Investments
    fig.add_trace(go.Scatter(
        x=labels, y=[r["investment_bal"] for r in results],
        name="Portfolio", line=dict(color="#51cf66", width=2.5),
        fill="tozeroy", fillcolor="rgba(81,207,102,0.08)"
    ), row=1, col=2)
    fig.add_trace(go.Bar(
        x=labels, y=[r["invested"] for r in results],
        name="Monthly Invest", marker_color="rgba(81,207,102,0.35)"
    ), row=1, col=2)

    # Interest
    fig.add_trace(go.Bar(
        x=labels, y=[r["mort_interest"] for r in results],
        name="Mortgage Interest", marker_color="rgba(77,171,247,0.6)"
    ), row=2, col=1)
    fig.add_trace(go.Bar(
        x=labels, y=[r["car_interest"] for r in results],
        name="Car Interest", marker_color="rgba(255,169,77,0.6)"
    ), row=2, col=1)

    # Cash allocation stacked
    fig.add_trace(go.Bar(
        x=labels, y=[r["mort_extra"] for r in results],
        name="Extra Mortgage", marker_color="rgba(77,171,247,0.7)"
    ), row=2, col=2)
    fig.add_trace(go.Bar(
        x=labels, y=[r["car_extra"] for r in results],
        name="Extra Car", marker_color="rgba(255,169,77,0.7)"
    ), row=2, col=2)
    fig.add_trace(go.Bar(
        x=labels, y=[r["invested"] for r in results],
        name="Invested", marker_color="rgba(81,207,102,0.7)"
    ), row=2, col=2)

    fig.update_layout(
        height=700,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(13,20,34,0.8)",
        font=dict(color="#7c90b0", family="Syne"),
        barmode="stack",
        legend=dict(
            bgcolor="rgba(19,25,41,0.9)",
            bordercolor="#2a3550",
            borderwidth=1,
            font=dict(size=11),
        ),
        margin=dict(t=40, b=20, l=10, r=10),
    )
    fig.update_xaxes(gridcolor="#1e2d45", linecolor="#2a3550", tickfont=dict(size=10))
    fig.update_yaxes(gridcolor="#1e2d45", linecolor="#2a3550", tickprefix="$", tickfont=dict(size=10))
    
    st.plotly_chart(fig, use_container_width=True)

# ─── Month-by-Month Editor ────────────────────────────────────────────────────
with tab2:
    st.markdown("### Adjust inputs for each month")
    st.markdown("""
    <div class="info-box">
    💡 <b>How it works:</b> Car payments are priority until paid off. Once the car is paid off, 
    your savings split between extra mortgage payments and investments based on the % slider.<br><br>
    🔁 <b>Cascading inputs:</b> Changing <b>monthly savings</b> or the <b>invest %</b> in any month 
    automatically applies it to all following months — until you set a different value later. 
    Months showing <span style="color:#4dabf7">◈ SET HERE</span> have an explicit override; 
    <span style="color:#7c90b0">↳ inherited</span> months are cascading from a prior setting.
    April months show a one-time tax refund field (never cascades).
    </div>
    """, unsafe_allow_html=True)

    if car_payoff_idx is not None:
        st.markdown(f"""
        <div class="car-paid">
        ✅ CAR LOAN PAID OFF in {car_payoff_label}! 
        Freed-up cash now splits between mortgage & investments.
        </div>
        """, unsafe_allow_html=True)

    for r in results:
        d = r["date"]
        mk = d.isoformat()
        ov = st.session_state.overrides.get(mk, {})

        is_car_paid_this_month = (r["idx"] == car_payoff_idx)
        car_active = r["car_bal"] > 0 or is_car_paid_this_month

        eff_savings = r["savings_used"]
        this_month_sets_savings = r["savings_is_override"]
        def_bonus = ov.get("bonus", 2000.0 if d.month == 4 else 0.0)

        eff_invest_pct = r["invest_pct"]
        this_month_sets_pct = r["invest_pct_is_override"]

        car_status = "🚗 PAYING CAR" if car_active else "📈 INVESTING"
        sav_badge = f"◈ ${eff_savings:,.0f}/mo" if this_month_sets_savings else f"↳ ${eff_savings:,.0f}/mo"
        pct_badge = f"◈ {int(eff_invest_pct)}% inv" if this_month_sets_pct else f"↳ {int(eff_invest_pct)}% inv"

        with st.expander(f"**{r['label']}** — {car_status} | {sav_badge} | {pct_badge} | 🏠 ${r['mortgage_bal']:,.0f} | 📈 ${r['investment_bal']:,.0f}"):
            c1, c2, c3 = st.columns([2, 2, 3])

            with c1:
                new_savings = st.number_input(
                    "Monthly savings ($)",
                    value=float(eff_savings), min_value=0.0, step=100.0,
                    key=f"sav_{mk}"
                )
                if this_month_sets_savings:
                    st.markdown("<span style='color:#4dabf7;font-size:0.8em;'>◈ Override set here — cascades forward</span>", unsafe_allow_html=True)
                    if st.button("✕ Remove savings override", key=f"clrsav_{mk}"):
                        del st.session_state.savings_overrides[mk]
                        st.rerun()
                else:
                    st.markdown("<span style='color:#7c90b0;font-size:0.8em;'>↳ Inherited from earlier month</span>", unsafe_allow_html=True)

            with c2:
                new_bonus = st.number_input(
                    "One-time extra / tax refund ($)" if d.month == 4 else "One-time extra ($)",
                    value=float(def_bonus), min_value=0.0, step=100.0,
                    key=f"bon_{mk}"
                )

            with c3:
                if not car_active:
                    new_invest_pct = st.slider(
                        "% to investments (rest → extra mortgage)",
                        0, 100, int(eff_invest_pct), 5,
                        key=f"inv_{mk}"
                    )
                    if this_month_sets_pct:
                        st.markdown("<span style='color:#4dabf7;font-size:0.8em;'>◈ Override set here — cascades forward</span>", unsafe_allow_html=True)
                        if st.button("✕ Remove ratio override", key=f"clr_{mk}"):
                            del st.session_state.invest_pct_overrides[mk]
                            st.rerun()
                    else:
                        st.markdown("<span style='color:#7c90b0;font-size:0.8em;'>↳ Inherited from earlier month</span>", unsafe_allow_html=True)
                else:
                    new_invest_pct = eff_invest_pct
                    st.markdown("<div style='color:#ffa94d;font-size:0.85em;margin-top:22px;'>💳 All savings → car payoff first</div>", unsafe_allow_html=True)

            # Summary row
            st.markdown(f"""
            <div class="info-box" style="margin-top:8px;">
            Monthly interest: 🏠 <span class="highlight-blue">${r['mort_interest']:.0f}</span> | 
            🚗 <span class="highlight-orange">${r['car_interest']:.0f}</span> &nbsp;|&nbsp; 
            Extra car: <span class="highlight-orange">${r['car_extra']:.0f}</span> | 
            Extra mortgage: <span class="highlight-blue">${r['mort_extra']:.0f}</span> | 
            Invested: <span class="highlight-green">${r['invested']:.0f}</span>
            </div>
            """, unsafe_allow_html=True)

            # ── Persist bonus override (never cascades) ──
            new_ov = {}
            if new_bonus != (2000.0 if d.month == 4 else 0.0):
                new_ov["bonus"] = new_bonus
            if new_ov:
                st.session_state.overrides[mk] = new_ov
            elif mk in st.session_state.overrides:
                del st.session_state.overrides[mk]

            # ── Persist savings cascade override ──
            if new_savings != eff_savings:
                st.session_state.savings_overrides[mk] = float(new_savings)

            # ── Persist invest_pct cascade override ──
            if not car_active and new_invest_pct != eff_invest_pct:
                st.session_state.invest_pct_overrides[mk] = float(new_invest_pct)

# ─── Summary Table ────────────────────────────────────────────────────────────
st.divider()
st.markdown("### 📋 Full Simulation Summary")

df = pd.DataFrame([{
    "Month": r["label"],
    "Mortgage Bal": f"${r['mortgage_bal']:,.0f}",
    "Car Bal": f"${r['car_bal']:,.0f}",
    "Portfolio": f"${r['investment_bal']:,.0f}",
    "Mort Interest": f"${r['mort_interest']:.0f}",
    "Car Interest": f"${r['car_interest']:.0f}",
    "Extra Car": f"${r['car_extra']:.0f}",
    "Extra Mort": f"${r['mort_extra']:.0f}",
    "Invested": f"${r['invested']:.0f}",
    "Savings": f"${r['savings_used']:,.0f}",
    "Bonus": f"${r['bonus']:,.0f}",
    "Total Available": f"${r['total_available']:,.0f}",
} for r in results])

st.dataframe(df, use_container_width=True, height=400, hide_index=True)

# ─── Footer ──────────────────────────────────────────────────────────────────
st.markdown("""
<div class="info-box" style="margin-top:20px; text-align:center;">
⚠️ <b>Disclaimer:</b> This simulator is for planning purposes only. 
Actual results will vary based on payment timing, rate changes, and other factors. 
Mortgage uses weekly payments (52/yr), car uses biweekly (26/yr), prorated monthly.
</div>
""", unsafe_allow_html=True)
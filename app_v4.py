import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date
import colorsys

st.set_page_config(page_title="Coast FIRE Planner", page_icon="🎯", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Syne', sans-serif; }
.stApp { background: linear-gradient(135deg, #0a0e1a 0%, #0d1422 50%, #0a0e1a 100%); }
h1, h2, h3 { font-family: 'Syne', sans-serif; font-weight: 800; }
div[data-testid="metric-container"] { background: #131929; border-radius: 10px; padding: 12px 16px; border: 1px solid #2a3550; }
.stButton > button { background: linear-gradient(135deg, #1c6ef3 0%, #1557d4 100%); color: white; border: none; border-radius: 8px; font-family: 'Space Mono', monospace; font-weight: 700; letter-spacing: 0.05em; padding: 8px 16px; transition: all 0.2s; width: 100%; }
.stButton > button:hover { background: linear-gradient(135deg, #2980ff 0%, #1c6ef3 100%); transform: translateY(-1px); box-shadow: 0 4px 20px rgba(28,110,243,0.4); }
.info-box { background: #0f1e33; border: 1px solid #1c3a5e; border-radius: 8px; padding: 12px 14px; font-family: 'Space Mono', monospace; font-size: 0.8em; color: #7c90b0; margin: 6px 0; }
.section-title { font-family: 'Space Mono', monospace; font-size: 0.7em; letter-spacing: 0.15em; color: #4dabf7; text-transform: uppercase; margin: 18px 0 6px 0; border-bottom: 1px solid #2a3550; padding-bottom: 5px; }
.stDataFrame { border: 1px solid #2a3550; border-radius: 10px; }
.strategy-box { background: #0f1e33; border: 1px solid #1c6ef3; border-radius: 8px; padding: 10px 14px; font-family: 'Space Mono', monospace; font-size: 0.78em; color: #7c90b0; margin: 6px 0; }
</style>
""", unsafe_allow_html=True)

# ─── Constants ────────────────────────────────────────────────────────────────
MORTGAGE_RATE_ANNUAL = 0.054
CAR_RATE_ANNUAL      = 0.068
MORTGAGE_WEEKLY_PMT  = 441.0
CAR_BIWEEKLY_PMT     = 242.0
START_MONTH          = date(2026, 5, 1)
MAX_MONTHS           = 120
MONTHS_ABBR = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

PREPAY_OPTIONS = {
    "📈 Increase payments by 20%": "increase_20pct",
    "💰 Annual lump sum (20% of balance)": "lump_sum_20pct",
    "🚫 No extra mortgage payments": "none",
}

def generate_colors(n):
    colors = []
    for i in range(n):
        hue = (i / n + 0.56) % 1.0
        r, g, b = colorsys.hls_to_rgb(hue, 0.62, 0.85)
        colors.append(f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}")
    return colors

def month_date(idx):
    y = START_MONTH.year + (START_MONTH.month - 1 + idx) // 12
    m = (START_MONTH.month - 1 + idx) % 12 + 1
    return date(y, m, 1)

def month_label(idx):
    d = month_date(idx)
    return f"{MONTHS_ABBR[d.month-1]} {d.year}"

def run_scenario(savings, invest_pct, inv_rate_annual, april_bonus, goal_investment, prepay_strategy):
    mort_bal = 275_000.0
    car_bal  =  30_000.0
    inv_bal  =  72_000.0
    mort_rate_m = MORTGAGE_RATE_ANNUAL / 12
    car_rate_m  = CAR_RATE_ANNUAL / 12
    inv_rate_m  = inv_rate_annual / 100 / 12
    car_monthly_pmt  = CAR_BIWEEKLY_PMT  * (26 / 12)
    mort_monthly_pmt = MORTGAGE_WEEKLY_PMT * (52 / 12)

    # Apply prepayment strategy to base mortgage payment
    # For "increase_20pct": scheduled payment is bumped 20% each month
    # For "lump_sum_20pct": normal payment each month, but once per year apply lump sum
    # For "none": normal scheduled payment only
    if prepay_strategy == "increase_20pct":
        mort_scheduled = mort_monthly_pmt * 1.20
    else:
        mort_scheduled = mort_monthly_pmt

    car_paid_label = mort_paid_label = goal_label = None
    goal_idx = None
    rows = []

    for i in range(MAX_MONTHS):
        d   = month_date(i)
        lbl = month_label(i)
        bonus       = april_bonus if d.month == 4 else 0.0
        car_freed   = car_monthly_pmt if car_bal == 0 else 0.0
        total_avail = savings + bonus + car_freed

        mort_interest  = mort_bal * mort_rate_m
        mort_principal = max(0.0, min(mort_scheduled - mort_interest, mort_bal))

        if car_bal > 0:
            car_interest  = car_bal * car_rate_m
            car_principal = max(0.0, min(car_monthly_pmt - car_interest, car_bal))
        else:
            car_interest = car_principal = 0.0

        car_extra = mort_extra = invested = 0.0

        if car_bal > 0:
            # Still paying off car — prioritise clearing it, then split remainder
            car_extra = min(total_avail, max(0.0, car_bal - car_principal))
            leftover  = total_avail - car_extra
            if leftover > 0:
                mort_extra = min(leftover * (1 - invest_pct / 100), mort_bal)
                invested   = leftover * (invest_pct / 100)
        else:
            # Car is gone — split available savings between mortgage and investments
            # For lump_sum strategy the "mort_extra" from the split is $0 (no monthly extra);
            # the annual lump sum is handled separately below.
            if prepay_strategy == "lump_sum_20pct":
                # No monthly extra — all available savings go to investments
                mort_extra = 0.0
                invested   = total_avail
            else:
                # increase_20pct already baked into mort_scheduled; "none" means no extra
                mort_extra = 0.0
                invested   = total_avail

        # Annual lump sum: applied once a year (January, or first month if start ≠ Jan)
        # Uses 20% of the *current* mortgage balance at that point
        lump_sum_applied = 0.0
        if prepay_strategy == "lump_sum_20pct" and mort_bal > 0:
            if d.month == 1 or (i == 0):  # apply in January each year (and month 0)
                lump_sum_applied = mort_bal * 0.20
                mort_extra += lump_sum_applied

        mort_bal = max(0.0, mort_bal - mort_principal - mort_extra)
        if car_bal > 0:
            car_bal = max(0.0, car_bal - car_principal - car_extra)
            if car_bal == 0 and car_paid_label is None:
                car_paid_label = lbl
        if mort_bal == 0 and mort_paid_label is None:
            mort_paid_label = lbl

        inv_bal = inv_bal * (1 + inv_rate_m) + invested

        if inv_bal >= goal_investment and mort_bal == 0 and goal_label is None:
            goal_label = lbl
            goal_idx   = i

        rows.append({
            "idx": i, "label": lbl, "mort_bal": mort_bal, "car_bal": car_bal,
            "inv_bal": inv_bal, "mort_interest": mort_interest, "car_interest": car_interest,
            "mort_extra": mort_extra, "car_extra": car_extra, "invested": invested,
            "lump_sum": lump_sum_applied,
        })

        if inv_bal >= goal_investment and mort_bal == 0:
            break

    return {
        "rows": rows,
        "car_paid":       car_paid_label  or "Not paid off",
        "mort_paid":      mort_paid_label or "Not paid off",
        "goal_reached":   goal_label,
        "goal_idx":       goal_idx if goal_idx is not None else 9999,
        "final_inv":      rows[-1]["inv_bal"],
        "final_mort":     rows[-1]["mort_bal"],
        "total_interest": sum(r["mort_interest"] + r["car_interest"] for r in rows),
        "total_invested": sum(r["invested"] for r in rows),
    }

# ─── Session State ────────────────────────────────────────────────────────────
def _default_scenarios():
    pcts   = list(range(60, 80, 1))
    colors = generate_colors(len(pcts))
    return [
        {"name": f"{p}% Invest / {100-p}% Mortgage", "invest_pct": p, "color": c}
        for p, c in zip(pcts, colors)
    ]

if "scenarios" not in st.session_state:
    st.session_state.scenarios = _default_scenarios()
if "inv_rate" not in st.session_state:
    st.session_state.inv_rate = 7.0
if "april_bonus" not in st.session_state:
    st.session_state.april_bonus = 10_000.0
if "goal_investment" not in st.session_state:
    st.session_state.goal_investment = 600_000.0
if "savings_amount" not in st.session_state:
    st.session_state.savings_amount = 3000.0
if "prepay_strategy" not in st.session_state:
    st.session_state.prepay_strategy = "📈 Increase payments by 20%"

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Global Settings")

    st.markdown('<div class="section-title">Monthly Savings</div>', unsafe_allow_html=True)
    savings_amount = st.number_input("Monthly savings ($)", value=st.session_state.savings_amount,
                                      min_value=0.0, step=100.0, format="%.0f")
    st.session_state.savings_amount = savings_amount

    st.markdown('<div class="section-title">Investment Return</div>', unsafe_allow_html=True)
    inv_rate = st.number_input("Annual return (%)", value=st.session_state.inv_rate,
                                min_value=0.0, max_value=20.0, step=0.5)
    st.session_state.inv_rate = inv_rate

    st.markdown('<div class="section-title">Annual April Bonus</div>', unsafe_allow_html=True)
    april_bonus = st.number_input("Tax refund / bonus ($)", value=st.session_state.april_bonus,
                                   min_value=0.0, step=500.0)
    st.session_state.april_bonus = april_bonus

    st.markdown('<div class="section-title">Coast FIRE Goal</div>', unsafe_allow_html=True)
    goal_investment = st.number_input("Target portfolio ($)", value=st.session_state.goal_investment,
                                       min_value=10_000.0, step=10_000.0, format="%.0f")
    st.session_state.goal_investment = goal_investment

    # ── Mortgage Prepayment Strategy ──────────────────────────────────────────
    st.markdown('<div class="section-title">Mortgage Prepayment Strategy</div>', unsafe_allow_html=True)
    prepay_label = st.radio(
        "How do you want to make extra mortgage payments?",
        options=list(PREPAY_OPTIONS.keys()),
        index=list(PREPAY_OPTIONS.keys()).index(st.session_state.prepay_strategy),
        help=(
            "📈 Increase by 20%: your weekly payment rises from $441 → $529, applied every month.\n\n"
            "💰 Annual lump sum: once each January, pay 20% of the remaining balance in one shot.\n\n"
            "🚫 None: stick to the scheduled payment only."
        ),
    )
    st.session_state.prepay_strategy = prepay_label
    prepay_strategy = PREPAY_OPTIONS[prepay_label]

    # Contextual explanation
    if prepay_strategy == "increase_20pct":
        extra_weekly = MORTGAGE_WEEKLY_PMT * 0.20
        st.markdown(f"""
        <div class="strategy-box">
        📅 Weekly payment:<br>
        $441 → <b style="color:#4dabf7">${MORTGAGE_WEEKLY_PMT * 1.20:,.0f}</b>/wk<br>
        (+${extra_weekly:,.0f}/wk extra)
        </div>
        """, unsafe_allow_html=True)
    elif prepay_strategy == "lump_sum_20pct":
        st.markdown(f"""
        <div class="strategy-box">
        📅 Normal $441/wk payments<br>
        🗓 Each January: pay <b style="color:#4dabf7">20% of remaining balance</b> as a lump sum<br>
        (e.g. on $275k → <b style="color:#4dabf7">$55,000</b> first year)
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="strategy-box">
        📅 Normal $441/wk payments only.<br>
        No extra principal applied.
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">Starting Position</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="info-box">
    🏠 Mortgage: $275,000 @ 5.4%<br>$441/wk scheduled<br><br>
    🚗 Car Loan: $30,000 @ 6.8%<br>$242/biweek scheduled<br><br>
    📈 Current portfolio: $72,000<br><br>
    🎯 Goal: ${goal_investment:,.0f} invested + house paid off
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">Manage Scenarios</div>', unsafe_allow_html=True)
    if st.button("➕ Add Scenario"):
        n = len(st.session_state.scenarios)
        st.session_state.scenarios.append({"name": f"Scenario {n + 1}", "invest_pct": 50, "color": "#ffffff"})
        new_colors = generate_colors(n + 1)
        for j, sc in enumerate(st.session_state.scenarios):
            sc["color"] = new_colors[j]
        st.rerun()
    if st.button("🔄 Reset to Defaults"):
        st.session_state.scenarios = _default_scenarios()
        st.rerun()

# ─── Header ───────────────────────────────────────────────────────────────────
strategy_display = {
    "increase_20pct":  "payments +20%",
    "lump_sum_20pct":  "annual lump sum (20% of balance)",
    "none":            "no extra payments",
}
st.markdown("# 🎯 Coast FIRE Scenario Planner")
st.markdown(
    f"*10-year projection — find the optimal invest/mortgage split to reach ${goal_investment:,.0f} portfolio + paid-off home · "
    f"savings: ${savings_amount:,.0f}/mo · prepayment: {strategy_display[prepay_strategy]}*"
)

# ─── Scenario Config Grid ─────────────────────────────────────────────────────
st.markdown("### Configure Scenarios")
st.markdown(
    f'<div class="info-box">All scenarios use <b>${savings_amount:,.0f}/mo</b> savings and '
    f'<b>{prepay_label}</b> (set in sidebar). Each scenario only varies the invest %. Changes apply instantly.</div>',
    unsafe_allow_html=True
)

scenarios_cfg = []
N    = len(st.session_state.scenarios)
COLS = 4

for row_start in range(0, N, COLS):
    row_scs = st.session_state.scenarios[row_start : row_start + COLS]
    cols = st.columns(len(row_scs))
    for col_idx, (sc, col) in enumerate(zip(row_scs, cols)):
        i = row_start + col_idx
        with col:
            st.markdown(f'<div style="height:3px;background:{sc["color"]};border-radius:3px;margin-bottom:6px"></div>', unsafe_allow_html=True)
            name       = st.text_input("Name", value=sc["name"], key=f"name_{i}", label_visibility="collapsed")
            invest_pct = st.number_input("Invest %", value=int(sc["invest_pct"]),
                                          min_value=0, max_value=100, step=1, key=f"pct_{i}")
            st.caption(f"🏠 {100-invest_pct}% mort · 📈 {invest_pct}% inv")
            if N > 1 and st.button("🗑", key=f"del_{i}", help="Remove"):
                st.session_state.scenarios.pop(i)
                new_colors = generate_colors(len(st.session_state.scenarios))
                for j, s in enumerate(st.session_state.scenarios):
                    s["color"] = new_colors[j]
                st.rerun()
            scenarios_cfg.append({"name": name, "invest_pct": invest_pct, "color": sc["color"]})

current_colors = generate_colors(len(scenarios_cfg))
for i, (cfg, col) in enumerate(zip(scenarios_cfg, current_colors)):
    cfg["color"] = col
    st.session_state.scenarios[i].update(cfg)

# ─── Run Simulations ──────────────────────────────────────────────────────────
sim_results = []
for sc in scenarios_cfg:
    res = run_scenario(savings_amount, sc["invest_pct"], inv_rate, april_bonus, goal_investment, prepay_strategy)
    res.update({"name": sc["name"], "color": sc["color"], "invest_pct": sc["invest_pct"], "savings": savings_amount})
    sim_results.append(res)

goal_reached = [r for r in sim_results if r["goal_reached"]]
winner = min(goal_reached, key=lambda r: r["goal_idx"]) if goal_reached else None

# ─── Winner Banner ────────────────────────────────────────────────────────────
st.divider()
st.markdown("### Results")

if winner:
    st.markdown(f"""
    <div style="background:linear-gradient(90deg,#1a3a2a,#122a1e);border-left:4px solid #51cf66;
    border-radius:8px;padding:12px 20px;margin-bottom:16px;font-family:'Space Mono',monospace;">
    🏆 <b style="color:#51cf66">FASTEST PATH:</b> &nbsp;
    <span style="color:#e8eaf0">{winner['name']}</span> &nbsp;—&nbsp;
    <span style="color:#51cf66">Goal reached {winner['goal_reached']}</span> &nbsp;|&nbsp;
    📈 {winner['invest_pct']}% invest &nbsp;|&nbsp; 💰 ${winner['savings']:,.0f}/mo &nbsp;|&nbsp;
    🏠 {prepay_label}
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown(f"""
    <div style="background:linear-gradient(90deg,#3a1a1a,#2a1212);border-left:4px solid #ff6b6b;
    border-radius:8px;padding:12px 20px;margin-bottom:16px;font-family:'Space Mono',monospace;color:#ff6b6b;">
    ⚠️ No scenario reaches ${goal_investment:,.0f} + paid-off home within 10 years. Try increasing savings or investment return.
    </div>
    """, unsafe_allow_html=True)

# ─── Results Table ────────────────────────────────────────────────────────────
comp_rows = []
for r in sim_results:
    is_w = winner and r["name"] == winner["name"]
    comp_rows.append({
        "🏷 Scenario":        r["name"],
        "📈 Invest %":        f"{r['invest_pct']}%",
        "🏠 Mortgage %":      f"{100 - r['invest_pct']}%",
        "🎯 Goal Reached":    r["goal_reached"] or "—",
        "🏠 Mort Paid":       r["mort_paid"],
        "🚗 Car Paid":        r["car_paid"],
        "📊 Final Portfolio": f"${r['final_inv']:,.0f}",
        "💸 Total Interest":  f"${r['total_interest']:,.0f}",
        "🏆":                 "✅" if is_w else "",
    })

st.dataframe(pd.DataFrame(comp_rows), use_container_width=True,
             hide_index=True, height=min(42 * N + 60, 620))

# ─── Charts ───────────────────────────────────────────────────────────────────
st.divider()
st.markdown("### Charts")

CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(13,20,34,0.8)",
    font=dict(color="#7c90b0", family="Syne"),
    legend=dict(bgcolor="rgba(19,25,41,0.9)", bordercolor="#2a3550", borderwidth=1, font=dict(size=10)),
    margin=dict(t=20, b=20, l=10, r=10),
    xaxis=dict(gridcolor="#1e2d45", linecolor="#2a3550"),
    yaxis=dict(gridcolor="#1e2d45", linecolor="#2a3550", tickprefix="$"),
)

tab1, tab2, tab3 = st.tabs(["📈 Portfolio Growth", "🏠 Mortgage Balance", "📊 Monthly Invested"])

with tab1:
    fig = go.Figure()
    fig.add_hline(y=goal_investment, line_dash="dash", line_color="#ffd43b", line_width=1.5,
                  annotation_text=f"${goal_investment:,.0f} Goal", annotation_font_color="#ffd43b",
                  annotation_position="top left")
    for r in sim_results:
        fig.add_trace(go.Scatter(
            x=[row["label"] for row in r["rows"]], y=[row["inv_bal"] for row in r["rows"]],
            name=r["name"], line=dict(color=r["color"], width=2),
            hovertemplate="%{x}<br>$%{y:,.0f}<extra>" + r["name"] + "</extra>"
        ))
    fig.update_layout(height=500, **CHART_LAYOUT)
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    fig2 = go.Figure()
    for r in sim_results:
        fig2.add_trace(go.Scatter(
            x=[row["label"] for row in r["rows"]], y=[row["mort_bal"] for row in r["rows"]],
            name=r["name"], line=dict(color=r["color"], width=2),
            hovertemplate="%{x}<br>$%{y:,.0f}<extra>" + r["name"] + "</extra>"
        ))
    fig2.update_layout(height=500, **CHART_LAYOUT)
    st.plotly_chart(fig2, use_container_width=True)

with tab3:
    fig3 = go.Figure()
    for r in sim_results:
        fig3.add_trace(go.Scatter(
            x=[row["label"] for row in r["rows"]], y=[row["invested"] for row in r["rows"]],
            name=r["name"], line=dict(color=r["color"], width=2),
            hovertemplate="%{x}<br>$%{y:,.0f}<extra>" + r["name"] + "</extra>"
        ))
    fig3.update_layout(height=500, **CHART_LAYOUT)
    st.plotly_chart(fig3, use_container_width=True)

st.markdown(f"""
<div class="info-box" style="margin-top:16px;text-align:center">
⚠️ All scenarios run exactly 10 years (120 months) from May 2026 · $72k starting portfolio ·
$441/wk mortgage · $242/biweek car · freed-up car payment reinvested after payoff · annual April bonus included.
Savings: ${savings_amount:,.0f}/mo · Prepayment: {prepay_label} · Goal: ${goal_investment:,.0f} invested + mortgage paid off.
For planning purposes only.
</div>
""", unsafe_allow_html=True)

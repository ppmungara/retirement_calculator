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
</style>
""", unsafe_allow_html=True)

# ─── Constants ────────────────────────────────────────────────────────────────
MORTGAGE_RATE_ANNUAL = 0.054
MORTGAGE_WEEKLY_PMT  = 441.0
# Opening balances. Single source of truth — the sidebar reads these too, so the
# displayed starting position cannot drift away from what is actually simulated.
MORTGAGE_START_BAL   = 270_000.0
PORTFOLIO_START_BAL  =  72_000.0
def _next_month_start(today=None):
    """First of the month after `today` — the projection always starts next month."""
    d = today or date.today()
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)

START_MONTH          = _next_month_start()
MAX_MONTHS           = 120
MONTHS_ABBR = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

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

def run_scenario(savings, invest_pct, inv_rate_annual, april_bonus, goal_investment):
    mort_bal = MORTGAGE_START_BAL
    inv_bal  = PORTFOLIO_START_BAL
    mort_rate_m = MORTGAGE_RATE_ANNUAL / 12
    inv_rate_m  = inv_rate_annual / 100 / 12
    mort_monthly_pmt = MORTGAGE_WEEKLY_PMT * (52 / 12)
    mort_paid_label = goal_label = None
    goal_idx = None
    rows = []
    for i in range(MAX_MONTHS):
        d   = month_date(i)
        lbl = month_label(i)
        bonus       = april_bonus if d.month == 4 else 0.0
        mort_freed  = mort_monthly_pmt if mort_bal == 0 else 0.0
        total_avail = savings + bonus + mort_freed
        mort_interest  = mort_bal * mort_rate_m
        mort_principal = max(0.0, min(mort_monthly_pmt - mort_interest, mort_bal))
        # Prepayment can only touch what the scheduled principal leaves behind.
        mort_room      = max(0.0, mort_bal - mort_principal)
        mort_extra = min(total_avail * (1 - invest_pct / 100), mort_room)
        invested   = total_avail - mort_extra
        mort_bal = max(0.0, mort_bal - mort_principal - mort_extra)
        if mort_bal == 0 and mort_paid_label is None:
            mort_paid_label = lbl
        inv_bal = inv_bal * (1 + inv_rate_m) + invested
        if inv_bal >= goal_investment and mort_bal == 0 and goal_label is None:
            goal_label = lbl
            goal_idx   = i
        rows.append({"idx": i, "label": lbl, "mort_bal": mort_bal,
                     "inv_bal": inv_bal, "mort_interest": mort_interest,
                     "mort_extra": mort_extra, "invested": invested})
        # Stop once the goal is met; scenarios that never meet it run the full
        # MAX_MONTHS. Runs therefore end at different times, so every summary
        # below is "at stop" and months_run states the horizon it was measured over.
        if goal_idx is not None:
            break

    return {
        "rows": rows,
        "months_run":     len(rows),
        "mort_paid":      mort_paid_label or "Not paid off",
        "goal_reached":   goal_label,
        "goal_idx":       goal_idx if goal_idx is not None else 9999,
        "final_inv":      rows[-1]["inv_bal"],
        "final_mort":     rows[-1]["mort_bal"],
        "total_interest": sum(r["mort_interest"] for r in rows),
        "total_invested": sum(r["invested"] for r in rows),
    }

# ─── Scenarios ────────────────────────────────────────────────────────────────
# Every whole-percent split from 1% to 99% invested, fixed — nothing to configure.
# Savings, return, bonus and goal are the only inputs, all global in the sidebar.
INVEST_PCTS = list(range(1, 100))
SCENARIOS = [
    {"name": f"{p}% Invest / {100-p}% Mortgage", "invest_pct": p, "color": c}
    for p, c in zip(INVEST_PCTS, generate_colors(len(INVEST_PCTS)))
]

# ─── Session State ────────────────────────────────────────────────────────────
if "inv_rate" not in st.session_state:
    st.session_state.inv_rate = 7.0
if "april_bonus" not in st.session_state:
    st.session_state.april_bonus = 10_000.0
if "goal_investment" not in st.session_state:
    st.session_state.goal_investment = 600_000.0
if "savings_amount" not in st.session_state:
    st.session_state.savings_amount = 3000.0

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

    st.markdown('<div class="section-title">Starting Position</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="info-box">
    📅 Projection starts <b>{month_label(0)}</b><br>runs to {month_label(MAX_MONTHS - 1)}<br><br>
    🏠 Mortgage: ${MORTGAGE_START_BAL:,.0f} @ {MORTGAGE_RATE_ANNUAL:.1%}<br>${MORTGAGE_WEEKLY_PMT:,.0f}/wk scheduled<br><br>
    📈 Current portfolio: ${PORTFOLIO_START_BAL:,.0f}<br><br>
    🎯 Goal: ${goal_investment:,.0f} invested + house paid off
    </div>
    """, unsafe_allow_html=True)

# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown("# 🎯 Coast FIRE Scenario Planner")
st.markdown(f"*10-year projection — find the optimal invest/mortgage split to reach ${goal_investment:,.0f} portfolio + paid-off home · savings: ${savings_amount:,.0f}/mo*")

scenarios_cfg = SCENARIOS
N = len(scenarios_cfg)
st.markdown(f'<div class="info-box">Every split from <b>1%</b> to <b>99%</b> invested is projected, all on '
            f'<b>${savings_amount:,.0f}/mo</b> savings. Adjust the inputs in the sidebar — results update instantly.</div>',
            unsafe_allow_html=True)

# ─── Run Simulations ──────────────────────────────────────────────────────────
# savings_amount from sidebar flows into every scenario here — no per-scenario copy needed
sim_results = []
for sc in scenarios_cfg:
    res = run_scenario(savings_amount, sc["invest_pct"], inv_rate, april_bonus, goal_investment)
    res.update({"name": sc["name"], "color": sc["color"], "invest_pct": sc["invest_pct"], "savings": savings_amount})
    sim_results.append(res)

goal_reached = [r for r in sim_results if r["goal_reached"]]
winner = min(goal_reached, key=lambda r: r["goal_idx"]) if goal_reached else None
# Across 99 splits the fastest date is usually a plateau rather than a single
# winner, so track everyone who ties instead of crowning the lowest percentage.
tied = [r for r in goal_reached if r["goal_idx"] == winner["goal_idx"]] if winner else []

# ─── Winner Banner ────────────────────────────────────────────────────────────
st.divider()
st.markdown("### Results")

if winner:
    st.markdown(f"""
    <div style="background:linear-gradient(90deg,#1a3a2a,#122a1e);border-left:4px solid #51cf66;
    border-radius:8px;padding:12px 20px;margin-bottom:16px;font-family:'Space Mono',monospace;">
    🏆 <b style="color:#51cf66">FASTEST PATH:</b> &nbsp;
    <span style="color:#e8eaf0">{
        f"{tied[0]['invest_pct']}%–{tied[-1]['invest_pct']}% invest" if len(tied) > 1 else winner['name']
    }</span> &nbsp;—&nbsp;
    <span style="color:#51cf66">Goal reached {winner['goal_reached']}</span> &nbsp;|&nbsp;
    {
        f"📈 {len(tied)} splits tie — anything in that band is equally fast"
        if len(tied) > 1 else f"📈 {winner['invest_pct']}% invest"
    } &nbsp;|&nbsp; 💰 ${winner['savings']:,.0f}/mo
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
    is_w = winner and r["goal_reached"] and r["goal_idx"] == winner["goal_idx"]
    comp_rows.append({
        "🏷 Scenario":        r["name"],
        "📈 Invest %":        f"{r['invest_pct']}%",
        "🏠 Mortgage %":      f"{100 - r['invest_pct']}%",
        "🎯 Goal Reached":    r["goal_reached"] or "—",
        "⏱ Months Run":      f"{r['months_run']}" + ("" if r["goal_reached"] else " (max)"),
        "🏠 Mort Paid":       r["mort_paid"],
        "📊 Portfolio at End": f"${r['final_inv']:,.0f}",
        "💸 Interest Paid":   f"${r['total_interest']:,.0f}",
        "🏆":                 "✅" if is_w else "",
    })

st.caption("Each run stops the month its goal is met, so portfolio and interest are measured "
           "at that point — not over a common 10 years. **Months Run** is the horizon behind "
           "each row; rows marked *(max)* never met the goal and ran the full 10 years.")
st.dataframe(pd.DataFrame(comp_rows), use_container_width=True,
             hide_index=True, height=min(42 * N + 60, 620))

# ─── Charts ───────────────────────────────────────────────────────────────────
st.divider()
st.markdown("### Charts")

# 99 traces make a legend useless, so it is off — the hover label names the split.
CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(13,20,34,0.8)",
    font=dict(color="#7c90b0", family="Syne"),
    showlegend=False,
    margin=dict(t=20, b=20, l=10, r=10),
    # Runs stop at different months, so pin the category order instead of letting
    # it be inferred from whichever trace happens to be drawn first.
    xaxis=dict(gridcolor="#1e2d45", linecolor="#2a3550", categoryorder="array",
               categoryarray=[month_label(i) for i in range(MAX_MONTHS)]),
    yaxis=dict(gridcolor="#1e2d45", linecolor="#2a3550", tickprefix="$"),
)
LINE_W = 1.2

st.caption("Colour runs from the lowest invest % to the highest. Hover any line to identify it.")

tab1, tab2, tab3 = st.tabs(["📈 Portfolio Growth", "🏠 Mortgage Balance", "📊 Monthly Invested"])

with tab1:
    fig = go.Figure()
    fig.add_hline(y=goal_investment, line_dash="dash", line_color="#ffd43b", line_width=1.5,
                  annotation_text=f"${goal_investment:,.0f} Goal", annotation_font_color="#ffd43b",
                  annotation_position="top left")
    for r in sim_results:
        fig.add_trace(go.Scatter(
            x=[row["label"] for row in r["rows"]], y=[row["inv_bal"] for row in r["rows"]],
            name=r["name"], line=dict(color=r["color"], width=LINE_W),
            hovertemplate="%{x}<br>$%{y:,.0f}<extra>" + r["name"] + "</extra>"
        ))
    fig.update_layout(height=500, **CHART_LAYOUT)
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    fig2 = go.Figure()
    for r in sim_results:
        fig2.add_trace(go.Scatter(
            x=[row["label"] for row in r["rows"]], y=[row["mort_bal"] for row in r["rows"]],
            name=r["name"], line=dict(color=r["color"], width=LINE_W),
            hovertemplate="%{x}<br>$%{y:,.0f}<extra>" + r["name"] + "</extra>"
        ))
    fig2.update_layout(height=500, **CHART_LAYOUT)
    st.plotly_chart(fig2, use_container_width=True)

with tab3:
    fig3 = go.Figure()
    for r in sim_results:
        fig3.add_trace(go.Scatter(
            x=[row["label"] for row in r["rows"]], y=[row["invested"] for row in r["rows"]],
            name=r["name"], line=dict(color=r["color"], width=LINE_W),
            hovertemplate="%{x}<br>$%{y:,.0f}<extra>" + r["name"] + "</extra>"
        ))
    fig3.update_layout(height=500, **CHART_LAYOUT)
    st.plotly_chart(fig3, use_container_width=True)

# ─── Month-by-Month Detail ────────────────────────────────────────────────────
st.divider()
st.markdown("### 📅 Month-by-Month Detail")

default_idx = next((i for i, r in enumerate(sim_results)
                    if winner and r["name"] == winner["name"]), 0)
sel = st.selectbox("Scenario", range(len(sim_results)), index=default_idx,
                   format_func=lambda i: sim_results[i]["name"], key="detail_scenario")
detail = sim_results[sel]
# index= only applies on first render, so the dropdown keeps whatever was picked
# even after the winner moves. Call the fastest band out separately.
if winner and detail["goal_idx"] != winner["goal_idx"]:
    band = (f"{tied[0]['invest_pct']}%–{tied[-1]['invest_pct']}% invest ({len(tied)} splits tie)"
            if len(tied) > 1 else f"**{winner['name']}**")
    st.caption(f"🏆 Fastest at these settings is {band} — goal {winner['goal_reached']}. "
               f"Showing {detail['name']}.")

# Group the projection into calendar years — the first and last are part years,
# since the run starts next month rather than in January.
years = {}
for row in detail["rows"]:
    years.setdefault(month_date(row["idx"]).year, []).append(row)

goal_row = detail["goal_idx"] if detail["goal_reached"] else None
for ytab, (yr, yrows) in zip(st.tabs([str(y) for y in years]), years.items()):
    with ytab:
        first, last = yrows[0], yrows[-1]
        c1, c2, c3 = st.columns(3)
        c1.metric("🏠 Mortgage at year end", f"${last['mort_bal']:,.0f}",
                  f"{last['mort_bal'] - first['mort_bal']:+,.0f}")
        c2.metric("📈 Portfolio at year end", f"${last['inv_bal']:,.0f}",
                  f"{last['inv_bal'] - first['inv_bal']:+,.0f}")
        c3.metric("💵 Invested this year", f"${sum(r['invested'] for r in yrows):,.0f}",
                  f"{len(yrows)} mo")
        st.dataframe(pd.DataFrame([{
            "Month":        r["label"] + ("  🎯" if r["idx"] == goal_row else ""),
            "🏠 Mortgage":  f"${r['mort_bal']:,.0f}",
            "📈 Portfolio": f"${r['inv_bal']:,.0f}",
            "💵 Invested":  f"${r['invested']:,.0f}",
            "🏠 Extra":     f"${r['mort_extra']:,.0f}",
            "💸 Interest":  f"${r['mort_interest']:,.0f}",
        } for r in yrows]), use_container_width=True, hide_index=True,
            height=42 * len(yrows) + 45)
        if goal_row is not None and any(r["idx"] == goal_row for r in yrows):
            st.caption(f"🎯 Goal reached {detail['goal_reached']} — "
                       f"${goal_investment:,.0f} invested with the mortgage cleared.")

st.markdown(f"""
<div class="info-box" style="margin-top:16px;text-align:center">
⚠️ Each scenario runs from {month_label(0)} until it reaches the goal, capped at 10 years ({MAX_MONTHS} months, {month_label(MAX_MONTHS - 1)}) ·
$441/wk mortgage · freed-up mortgage payment redirected after payoff · annual April bonus included.<br>
Savings are assumed to be <b>surplus on top of</b> the scheduled mortgage payments.<br>
Opening balances below are fixed in the code and are <b>not</b> re-dated as the start month rolls forward.
Savings: ${savings_amount:,.0f}/mo · Goal: ${goal_investment:,.0f} invested + mortgage paid off. For planning purposes only.
</div>
""", unsafe_allow_html=True)

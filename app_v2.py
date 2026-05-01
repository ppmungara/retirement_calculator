import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date

# ─── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Investment & Debt Scenario Planner",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;600;700;800&display=swap');

html, body, [class*="css"] { font-family: 'Syne', sans-serif; }
.stApp { background: linear-gradient(135deg, #0a0e1a 0%, #0d1422 50%, #0a0e1a 100%); }
h1, h2, h3 { font-family: 'Syne', sans-serif; font-weight: 800; }

div[data-testid="metric-container"] {
    background: #131929;
    border-radius: 10px;
    padding: 12px 16px;
    border: 1px solid #2a3550;
}

.stButton > button {
    background: linear-gradient(135deg, #1c6ef3 0%, #1557d4 100%);
    color: white; border: none; border-radius: 8px;
    font-family: 'Space Mono', monospace; font-weight: 700;
    letter-spacing: 0.05em; padding: 8px 20px; transition: all 0.2s;
    width: 100%;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #2980ff 0%, #1c6ef3 100%);
    transform: translateY(-1px);
    box-shadow: 0 4px 20px rgba(28,110,243,0.4);
}

.scenario-card {
    background: linear-gradient(135deg, #131929 0%, #1a2236 100%);
    border: 1px solid #2a3550;
    border-radius: 12px;
    padding: 18px 20px;
    margin-bottom: 12px;
}
.scenario-card.winner {
    border-color: #51cf66;
    box-shadow: 0 0 16px rgba(81,207,102,0.15);
}
.scenario-label {
    font-family: 'Space Mono', monospace;
    font-size: 0.72em;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: #7c90b0;
    margin-bottom: 4px;
}
.scenario-name {
    font-family: 'Syne', sans-serif;
    font-weight: 800;
    font-size: 1.1em;
    color: #e8eaf0;
    margin-bottom: 10px;
}
.stat-row {
    display: flex; gap: 16px; flex-wrap: wrap; margin-top: 8px;
}
.stat {
    background: #0f1822;
    border-radius: 8px;
    padding: 8px 12px;
    font-family: 'Space Mono', monospace;
    font-size: 0.78em;
}
.stat-val { font-size: 1.1em; font-weight: 700; color: #e8eaf0; }
.stat-key { color: #7c90b0; font-size: 0.85em; }

.info-box {
    background: #0f1e33; border: 1px solid #1c3a5e;
    border-radius: 8px; padding: 14px;
    font-family: 'Space Mono', monospace;
    font-size: 0.82em; color: #7c90b0; margin: 8px 0;
}
.section-title {
    font-family: 'Space Mono', monospace;
    font-size: 0.72em; letter-spacing: 0.15em;
    color: #4dabf7; text-transform: uppercase;
    margin: 20px 0 8px 0;
    border-bottom: 1px solid #2a3550; padding-bottom: 6px;
}
.winner-badge {
    display: inline-block;
    background: linear-gradient(135deg, #1a3a2a, #122a1e);
    border: 1px solid #51cf66;
    color: #51cf66; border-radius: 6px;
    padding: 2px 10px; font-size: 0.78em;
    font-family: 'Space Mono', monospace;
    font-weight: 700; margin-left: 8px;
}
.highlight-green { color: #51cf66; font-weight: 700; }
.highlight-blue  { color: #4dabf7; font-weight: 700; }
.highlight-gold  { color: #ffd43b; font-weight: 700; }
.highlight-red   { color: #ff6b6b; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

# ─── Constants ────────────────────────────────────────────────────────────────
MORTGAGE_RATE_ANNUAL  = 0.054
CAR_RATE_ANNUAL       = 0.068
MORTGAGE_WEEKLY_PMT   = 441.0
CAR_BIWEEKLY_PMT      = 242.0
START_MONTH           = date(2026, 5, 1)
GOAL_INVESTMENT       = 500_000.0
MONTHS_ABBR = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

SCENARIO_COLORS = ["#4dabf7","#51cf66","#ffa94d","#e599f7","#ff6b6b","#74c0fc"]

# ─── Helpers ──────────────────────────────────────────────────────────────────
def month_date(idx):
    y = START_MONTH.year + (START_MONTH.month - 1 + idx) // 12
    m = (START_MONTH.month - 1 + idx) % 12 + 1
    return date(y, m, 1)

def month_label(idx):
    d = month_date(idx)
    return f"{MONTHS_ABBR[d.month-1]} {d.year}"

# ─── Core Simulation ──────────────────────────────────────────────────────────
def run_scenario(savings, invest_pct, inv_rate_annual, april_bonus, max_months=120):
    """
    Run one scenario to completion (goal hit or max_months).
    - savings: monthly discretionary savings
    - invest_pct: % of post-car discretionary going to investments (rest → extra mortgage)
    - inv_rate_annual: annual investment return %
    - april_bonus: one-time annual April cash injection
    """
    mort_bal   = 275_000.0
    car_bal    =  30_000.0
    inv_bal    =  72_000.0   # starting portfolio

    mort_rate_m = MORTGAGE_RATE_ANNUAL / 12
    car_rate_m  = CAR_RATE_ANNUAL / 12
    inv_rate_m  = inv_rate_annual / 100 / 12

    car_monthly_pmt  = CAR_BIWEEKLY_PMT  * (26 / 12)
    mort_monthly_pmt = MORTGAGE_WEEKLY_PMT * (52 / 12)

    car_paid_label  = None
    mort_paid_label = None
    goal_label      = None
    goal_idx        = None

    rows = []

    for i in range(max_months):
        d  = month_date(i)
        lbl = month_label(i)

        bonus = april_bonus if d.month == 4 else 0.0
        car_freed = car_monthly_pmt if car_bal == 0 else 0.0
        total_avail = savings + bonus + car_freed

        # ── Scheduled mortgage ──
        mort_interest  = mort_bal * mort_rate_m
        mort_principal = max(0.0, min(mort_monthly_pmt - mort_interest, mort_bal))

        # ── Scheduled car ──
        if car_bal > 0:
            car_interest  = car_bal * car_rate_m
            car_principal = max(0.0, min(car_monthly_pmt - car_interest, car_bal))
        else:
            car_interest  = 0.0
            car_principal = 0.0

        car_extra  = 0.0
        mort_extra = 0.0
        invested   = 0.0

        if car_bal > 0:
            # All discretionary → smash car debt
            car_extra = min(total_avail, max(0.0, car_bal - car_principal))
            leftover  = total_avail - car_extra
            if leftover > 0:
                mort_extra = min(leftover * (1 - invest_pct / 100), mort_bal)
                invested   = leftover * (invest_pct / 100)
        else:
            # Car free — split by ratio
            mort_extra = min(total_avail * (1 - invest_pct / 100), mort_bal)
            invested   = total_avail * (invest_pct / 100)

        # ── Apply ──
        mort_bal = max(0.0, mort_bal - mort_principal - mort_extra)
        if car_bal > 0:
            car_bal = max(0.0, car_bal - car_principal - car_extra)
            if car_bal == 0 and car_paid_label is None:
                car_paid_label = lbl

        if mort_bal == 0 and mort_paid_label is None:
            mort_paid_label = lbl

        inv_bal = inv_bal * (1 + inv_rate_m) + invested

        if inv_bal >= GOAL_INVESTMENT and mort_bal == 0 and goal_label is None:
            goal_label = lbl
            goal_idx   = i

        rows.append({
            "idx":          i,
            "label":        lbl,
            "mort_bal":     mort_bal,
            "car_bal":      car_bal,
            "inv_bal":      inv_bal,
            "mort_interest":mort_interest,
            "car_interest": car_interest,
            "mort_extra":   mort_extra,
            "car_extra":    car_extra,
            "invested":     invested,
            "total_avail":  total_avail,
        })

        # Stop once both debts cleared and goal reached, or at 10-year cap
        if mort_bal == 0 and car_bal == 0 and inv_bal >= GOAL_INVESTMENT:
            break

    return {
        "rows":             rows,
        "car_paid":         car_paid_label  or "Not paid off",
        "mort_paid":        mort_paid_label or "Not paid off",
        "goal_reached":     goal_label,
        "goal_idx":         goal_idx,
        "final_inv":        rows[-1]["inv_bal"],
        "final_mort":       rows[-1]["mort_bal"],
        "total_interest":   sum(r["mort_interest"] + r["car_interest"] for r in rows),
        "total_invested":   sum(r["invested"] for r in rows),
    }

# ─── Session State ────────────────────────────────────────────────────────────
def _default_scenarios():
    return [
        {"name": "All Mortgage First",   "invest_pct":  0, "savings": 3000, "color": SCENARIO_COLORS[0]},
        {"name": "25% Invest",           "invest_pct": 25, "savings": 3000, "color": SCENARIO_COLORS[1]},
        {"name": "50 / 50",              "invest_pct": 50, "savings": 3000, "color": SCENARIO_COLORS[2]},
        {"name": "75% Invest",           "invest_pct": 75, "savings": 3000, "color": SCENARIO_COLORS[3]},
        {"name": "All Investments First","invest_pct":100, "savings": 3000, "color": SCENARIO_COLORS[4]},
    ]

if "scenarios" not in st.session_state:
    st.session_state.scenarios = _default_scenarios()
if "inv_rate" not in st.session_state:
    st.session_state.inv_rate = 7.0
if "april_bonus" not in st.session_state:
    st.session_state.april_bonus = 10_000.0

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Global Settings")

    st.markdown('<div class="section-title">Investment Return</div>', unsafe_allow_html=True)
    inv_rate = st.number_input("Annual return (%)", value=st.session_state.inv_rate,
                                min_value=0.0, max_value=20.0, step=0.5)
    st.session_state.inv_rate = inv_rate

    st.markdown('<div class="section-title">Annual April Bonus</div>', unsafe_allow_html=True)
    april_bonus = st.number_input("Tax refund / bonus ($)", value=st.session_state.april_bonus,
                                   min_value=0.0, step=500.0)
    st.session_state.april_bonus = april_bonus

    st.markdown('<div class="section-title">Starting Position</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="info-box">
    🏠 Mortgage: $275,000 @ 5.4%<br>$441/wk scheduled<br><br>
    🚗 Car Loan: $30,000 @ 6.8%<br>$242/biweek scheduled<br><br>
    📈 Current portfolio: $72,000<br><br>
    🎯 Goal: ${GOAL_INVESTMENT} invested + house paid off
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">Scenarios</div>', unsafe_allow_html=True)
    if st.button("➕ Add Scenario"):
        used = {s["color"] for s in st.session_state.scenarios}
        color = next((c for c in SCENARIO_COLORS if c not in used), SCENARIO_COLORS[0])
        st.session_state.scenarios.append({
            "name": f"Scenario {len(st.session_state.scenarios)+1}",
            "invest_pct": 50,
            "savings": 3000,
            "color": color,
        })
        st.rerun()
    if st.button("🔄 Reset to Defaults"):
        st.session_state.scenarios = _default_scenarios()
        st.rerun()

# ─── Scenario Editors ─────────────────────────────────────────────────────────
st.markdown("# 🎯 Investment & Debt Scenario Planner")
st.markdown("*10-year Coast FIRE plan — find the optimal invest/mortgage split to reach $600k portfolio + paid-off home*")

st.markdown("### Configure Scenarios")
cols = st.columns(min(len(st.session_state.scenarios), 3))
scenarios_cfg = []

for i, sc in enumerate(st.session_state.scenarios):
    col = cols[i % len(cols)]
    with col:
        with st.container():
            st.markdown(f'<div style="height:4px;background:{sc["color"]};border-radius:4px;margin-bottom:10px"></div>', unsafe_allow_html=True)
            name = st.text_input("Name", value=sc["name"], key=f"name_{i}")
            savings = st.number_input("Monthly savings ($)", value=float(sc["savings"]),
                                       min_value=0.0, step=100.0, key=f"sav_{i}")
            invest_pct = st.slider("% to investments", 0, 100, int(sc["invest_pct"]),
                                    step=1, key=f"pct_{i}",
                                    help="Rest goes to extra mortgage payments")
            st.caption(f"🏠 {100-invest_pct}% extra mortgage  |  📈 {invest_pct}% invest")
            if len(st.session_state.scenarios) > 1:
                if st.button("🗑 Remove", key=f"del_{i}"):
                    st.session_state.scenarios.pop(i)
                    st.rerun()

            scenarios_cfg.append({
                "name": name,
                "savings": savings,
                "invest_pct": invest_pct,
                "color": sc["color"],
            })

# Sync back
for i, cfg in enumerate(scenarios_cfg):
    st.session_state.scenarios[i].update(cfg)

# ─── Run All Scenarios ────────────────────────────────────────────────────────
sim_results = []
for sc in scenarios_cfg:
    result = run_scenario(
        savings=sc["savings"],
        invest_pct=sc["invest_pct"],
        inv_rate_annual=inv_rate,
        april_bonus=april_bonus,
    )
    result["name"]  = sc["name"]
    result["color"] = sc["color"]
    result["invest_pct"] = sc["invest_pct"]
    result["savings"] = sc["savings"]
    sim_results.append(result)

# Find winner (fastest to reach goal)
winners = [r for r in sim_results if r["goal_reached"]]
winner = min(winners, key=lambda r: r["goal_idx"]) if winners else None

# ─── Scenario Cards ───────────────────────────────────────────────────────────
st.divider()
st.markdown("### Results")

card_cols = st.columns(len(sim_results))
for i, r in enumerate(sim_results):
    is_winner = winner and r["name"] == winner["name"]
    with card_cols[i]:
        badge = '<span class="winner-badge">🏆 FASTEST</span>' if is_winner else ""
        goal_str = f'<span class="highlight-green">{r["goal_reached"]}</span>' if r["goal_reached"] else '<span class="highlight-red">Not reached</span>'
        mort_color = "highlight-green" if r["final_mort"] == 0 else "highlight-blue"

        st.markdown(f"""
        <div class="scenario-card {'winner' if is_winner else ''}">
            <div style="height:3px;background:{r['color']};border-radius:3px;margin-bottom:12px"></div>
            <div class="scenario-label">Scenario</div>
            <div class="scenario-name">{r['name']} {badge}</div>
            <div style="font-family:'Space Mono',monospace;font-size:0.8em;color:#7c90b0;margin-bottom:8px">
                📈 {r['invest_pct']}% invest &nbsp;|&nbsp; 💰 ${r['savings']:,.0f}/mo
            </div>
            <div class="stat-row">
                <div class="stat">
                    <div class="stat-key">🎯 Goal reached</div>
                    <div class="stat-val">{goal_str if r["goal_reached"] else "—"}</div>
                </div>
                <div class="stat">
                    <div class="stat-key">🏠 Mortgage paid</div>
                    <div class="stat-val"><span class="{mort_color}">{r['mort_paid']}</span></div>
                </div>
                <div class="stat">
                    <div class="stat-key">🚗 Car paid</div>
                    <div class="stat-val">{r['car_paid']}</div>
                </div>
                <div class="stat">
                    <div class="stat-key">📈 Final portfolio</div>
                    <div class="stat-val">${r['final_inv']:,.0f}</div>
                </div>
                <div class="stat">
                    <div class="stat-key">💸 Total interest</div>
                    <div class="stat-val">${r['total_interest']:,.0f}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

# ─── Charts ───────────────────────────────────────────────────────────────────
st.divider()
st.markdown("### Charts")

# Determine common x-axis length (longest scenario, capped at 360)
max_idx = max(len(r["rows"]) for r in sim_results)
all_labels = [month_label(i) for i in range(max_idx)]

tab1, tab2, tab3 = st.tabs(["📈 Portfolio Growth", "🏠 Mortgage Balance", "📊 Monthly Invested"])

with tab1:
    fig = go.Figure()
    # Goal line
    fig.add_hline(y=GOAL_INVESTMENT, line_dash="dash", line_color="#ffd43b", line_width=1.5,
                  annotation_text="$600k Goal", annotation_font_color="#ffd43b",
                  annotation_position="top left")
    for r in sim_results:
        labels = [row["label"] for row in r["rows"]]
        vals   = [row["inv_bal"] for row in r["rows"]]
        fig.add_trace(go.Scatter(
            x=labels, y=vals, name=r["name"],
            line=dict(color=r["color"], width=2.5),
            hovertemplate="%{x}<br>Portfolio: $%{y:,.0f}<extra>" + r["name"] + "</extra>"
        ))
    fig.update_layout(
        height=420, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(13,20,34,0.8)",
        font=dict(color="#7c90b0", family="Syne"),
        legend=dict(bgcolor="rgba(19,25,41,0.9)", bordercolor="#2a3550", borderwidth=1),
        margin=dict(t=20, b=20, l=10, r=10), yaxis_tickprefix="$",
        xaxis=dict(gridcolor="#1e2d45"), yaxis=dict(gridcolor="#1e2d45"),
    )
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    fig2 = go.Figure()
    for r in sim_results:
        labels = [row["label"] for row in r["rows"]]
        vals   = [row["mort_bal"] for row in r["rows"]]
        fig2.add_trace(go.Scatter(
            x=labels, y=vals, name=r["name"],
            line=dict(color=r["color"], width=2.5),
            hovertemplate="%{x}<br>Mortgage: $%{y:,.0f}<extra>" + r["name"] + "</extra>"
        ))
    fig2.update_layout(
        height=420, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(13,20,34,0.8)",
        font=dict(color="#7c90b0", family="Syne"),
        legend=dict(bgcolor="rgba(19,25,41,0.9)", bordercolor="#2a3550", borderwidth=1),
        margin=dict(t=20, b=20, l=10, r=10), yaxis_tickprefix="$",
        xaxis=dict(gridcolor="#1e2d45"), yaxis=dict(gridcolor="#1e2d45"),
    )
    st.plotly_chart(fig2, use_container_width=True)

with tab3:
    fig3 = go.Figure()
    for r in sim_results:
        labels = [row["label"] for row in r["rows"]]
        vals   = [row["invested"] for row in r["rows"]]
        fig3.add_trace(go.Bar(
            x=labels, y=vals, name=r["name"],
            marker_color=r["color"],
            hovertemplate="%{x}<br>Invested: $%{y:,.0f}<extra>" + r["name"] + "</extra>"
        ))
    fig3.update_layout(
        height=420, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(13,20,34,0.8)",
        font=dict(color="#7c90b0", family="Syne"), barmode="group",
        legend=dict(bgcolor="rgba(19,25,41,0.9)", bordercolor="#2a3550", borderwidth=1),
        margin=dict(t=20, b=20, l=10, r=10), yaxis_tickprefix="$",
        xaxis=dict(gridcolor="#1e2d45"), yaxis=dict(gridcolor="#1e2d45"),
    )
    st.plotly_chart(fig3, use_container_width=True)

# ─── Comparison Table ─────────────────────────────────────────────────────────
st.divider()
st.markdown("### Side-by-Side Comparison")

comp_rows = []
for r in sim_results:
    comp_rows.append({
        "Scenario":        r["name"],
        "Savings/mo":      f"${r['savings']:,.0f}",
        "Invest %":        f"{r['invest_pct']}%",
        "Mortgage %":      f"{100 - r['invest_pct']}%",
        "Car Paid Off":    r["car_paid"],
        "Mortgage Paid":   r["mort_paid"],
        "Goal Reached":    r["goal_reached"] or "—",
        "Final Portfolio": f"${r['final_inv']:,.0f}",
        "Total Interest":  f"${r['total_interest']:,.0f}",
        "Total Invested":  f"${r['total_invested']:,.0f}",
    })

st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)

st.markdown("""
<div class="info-box" style="margin-top:16px;text-align:center">
⚠️ All scenarios run exactly 10 years (120 months) from May 2026. Simulator uses your $72k starting portfolio, $441/wk mortgage, $242/biweek car payments, freed-up car payment reinvested after payoff, and annual April bonus. For planning purposes only.
</div>
""", unsafe_allow_html=True)
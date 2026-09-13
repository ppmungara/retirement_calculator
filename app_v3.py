"""Coast FIRE Scenario Planner.

Projects a household's path to a target portfolio plus a paid-off home, sweeping
every invest-vs-prepay split. Contributions flow through real registered
accounts (RRSP / TFSA / non-registered) with contribution room enforced, and the
RRSP deduction generates an Alberta + federal tax refund that is recycled back
into the plan. Every input below is configurable from the sidebar.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import streamlit.components.v1 as components
from dataclasses import dataclass, field
from datetime import date
import pathlib
import colorsys
import json
import base64
import zlib

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

MONTHS_ABBR = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

# ─── Tax engine ───────────────────────────────────────────────────────────────
# Brackets are (upper limit, rate) pairs, lowest first. The top entry's limit is
# ignored — the highest bracket always runs to infinity. Defaults are the 2025
# federal and Alberta schedules; both tables are editable in the app, so they can
# be rolled forward without touching this file.
FED_BRACKETS_DEFAULT = [(57_375.0, 0.145), (114_750.0, 0.205), (177_882.0, 0.26),
                        (253_414.0, 0.29), (float("inf"), 0.33)]
AB_BRACKETS_DEFAULT  = [(60_000.0, 0.08), (151_234.0, 0.10), (181_481.0, 0.12),
                        (241_974.0, 0.13), (362_961.0, 0.14), (float("inf"), 0.15)]
FED_BPA_DEFAULT = 16_129.0
AB_BPA_DEFAULT  = 22_323.0

# CPP and EI, 2025 employee figures. Every one of these is editable in the app.
# CPP is split: contributions at the base rate are a non-refundable credit, while
# the "enhanced" slice above it — and all of CPP2 — come off income as deductions.
# EI is a credit in full.
CPP_RATE_DEFAULT      = 5.95     # employee rate on pensionable earnings
CPP_BASE_RATE_DEFAULT = 4.95     # the part of that rate credited rather than deducted
CPP_EXEMPT_DEFAULT    = 3_500.0  # basic exemption
CPP_YMPE_DEFAULT      = 71_300.0
CPP2_RATE_DEFAULT     = 4.00
CPP2_YAMPE_DEFAULT    = 81_200.0
EI_RATE_DEFAULT       = 1.64
EI_MIE_DEFAULT        = 65_700.0


def bracket_tax(income, brackets):
    """Tax before credits on `income` under a progressive bracket table."""
    tax, lower = 0.0, 0.0
    for limit, rate in brackets:
        if income <= lower:
            break
        tax += (min(income, limit) - lower) * rate
        lower = limit
    return tax


def schedule_tax(taxable, brackets, credit_base):
    """Tax for one jurisdiction, net of its non-refundable credits.

    `credit_base` is the total of the amounts credited at the lowest bracket rate
    — the basic personal amount, plus base CPP and EI when those are modelled.
    They reduce tax rather than income, which is why they are netted off here.
    """
    return max(0.0, bracket_tax(max(0.0, taxable), brackets) - max(0.0, credit_base) * brackets[0][1])


def cpp_ei_for(gross, cfg):
    """Employee CPP and EI on a year's employment income.

    Returns (base CPP, enhanced CPP, CPP2, EI). The split matters: the base slice
    and EI are credits, while the enhanced slice and CPP2 are deductions, so they
    move taxable income and can change which bracket an RRSP deduction unwinds.
    """
    if not cfg.model_cpp_ei or gross <= 0:
        return 0.0, 0.0, 0.0, 0.0
    pensionable = max(0.0, min(gross, cfg.cpp_ympe) - cfg.cpp_exempt)
    enhanced = pensionable * max(0.0, cfg.cpp_rate - cfg.cpp_base_rate) / 100
    base = pensionable * cfg.cpp_base_rate / 100
    cpp2 = max(0.0, min(gross, cfg.cpp2_yampe) - cfg.cpp_ympe) * cfg.cpp2_rate / 100
    ei = min(gross, cfg.ei_mie) * cfg.ei_rate / 100
    return base, enhanced, cpp2, ei


def taxable_income(gross, cfg, rrsp_deduction=0.0):
    _, enhanced, cpp2, _ = cpp_ei_for(gross, cfg)
    return max(0.0, gross - enhanced - cpp2 - max(0.0, rrsp_deduction))


def total_tax(gross, cfg, rrsp_deduction=0.0):
    """Combined federal and Alberta income tax on a salary."""
    base, _, _, ei = cpp_ei_for(gross, cfg)
    taxable = taxable_income(gross, cfg, rrsp_deduction)
    return (schedule_tax(taxable, cfg.fed_brackets, cfg.fed_bpa + base + ei)
            + schedule_tax(taxable, cfg.ab_brackets, cfg.ab_bpa + base + ei))


def marginal_rate(gross, cfg):
    """Combined rate on the next dollar of taxable income.

    Measured at income after the CPP deductions, since that is the rate an RRSP
    contribution actually unwinds. It is not a full marginal cost of earning one
    more dollar — that would also carry CPP and EI on the dollar itself.
    """
    taxable = taxable_income(gross, cfg)

    def rate_at(brackets):
        for limit, rate in brackets:
            if taxable <= limit:
                return rate
        return brackets[-1][1]

    return rate_at(cfg.fed_brackets) + rate_at(cfg.ab_brackets)


def refund_for(gross, deduction, cfg):
    """Refund generated by an RRSP deduction: the tax delta it actually removes.

    Computed as a difference of two full tax calculations rather than
    `deduction x marginal rate`, so a deduction that spans a bracket boundary is
    valued correctly. CPP and EI credits are identical on both sides and cancel
    out; their deductible slices do not, because they shift where the deduction
    lands in the brackets.
    """
    if deduction <= 0 or gross <= 0:
        return 0.0
    return max(0.0, total_tax(gross, cfg) - total_tax(gross, cfg, min(deduction, gross)))


def take_home(gross, cfg, rrsp_deduction=0.0):
    """What actually reaches the bank: pay less income tax, CPP and EI."""
    base, enhanced, cpp2, ei = cpp_ei_for(gross, cfg)
    return gross - total_tax(gross, cfg, rrsp_deduction) - base - enhanced - cpp2 - ei


def payroll_schedule(gross, cfg):
    """This year's CPP and EI month by month, stopping once each annual maximum is hit.

    Deductions come off every paycheque at the statutory rate until the year's
    maximum is reached, and then stop — which is why take-home rises partway
    through the year. Annual totals are exact; CPP2's lower rate is not given its
    own slower stretch at the end, so the month it stops can be slightly early.
    """
    base, enhanced, cpp2, ei_total = cpp_ei_for(gross, cfg)
    cpp_left, ei_left = base + enhanced + cpp2, ei_total
    monthly = max(0.0, gross) / 12
    cpp_per_month = max(0.0, monthly - cfg.cpp_exempt / 12) * cfg.cpp_rate / 100
    ei_per_month = monthly * cfg.ei_rate / 100
    months = []
    for _ in range(12):
        taken_cpp = min(cpp_per_month, cpp_left)
        taken_ei = min(ei_per_month, ei_left)
        cpp_left -= taken_cpp
        ei_left -= taken_ei
        # The third value is what a still-deducting month would have cost, so the
        # simulation can see how much take-home frees up once they stop.
        months.append((taken_cpp, taken_ei, cpp_per_month + ei_per_month))
    return months


# ─── Configuration ────────────────────────────────────────────────────────────
BUCKETS = ["RRSP – You", "RRSP – Spouse", "TFSA – You", "TFSA – Spouse", "Non-registered"]
NONREG = "Non-registered"


@dataclass
class Person:
    label: str
    income: float
    rrsp_bal: float
    tfsa_bal: float
    rrsp_room: float
    tfsa_room: float
    ytd_rrsp: float = 0.0     # RRSP already contributed earlier in the start year
    employee_pct: float = 0.0  # group-plan contribution, % of salary
    employer_pct: float = 0.0  # employer match, % of salary


@dataclass
class Cfg:
    you: Person
    spouse: Person
    # cash flow
    savings: float
    savings_growth: float
    salary_growth: float
    bonus: float
    bonus_month: int
    # balances & returns
    nonreg_bal: float
    inv_return: float
    nonreg_drag: float
    # contribution room accrual
    tfsa_annual: float
    rrsp_accrual_pct: float
    rrsp_annual_max: float
    limit_indexation: float
    # group plan
    group_is_rrsp: bool         # True: group RRSP. False: DC pension (PA model).
    payroll_from_savings: bool
    # mortgage
    mort_bal: float
    mort_rate: float
    mort_weekly: float
    mort_orig: float
    prepay_pct: float
    prepay_enforce: bool
    redirect_freed: bool
    # allocation
    waterfall: list
    spill_to_invest: bool
    # refund
    refund_month: int
    refund_rule: str
    # tax tables
    fed_brackets: list
    ab_brackets: list
    fed_bpa: float
    ab_bpa: float
    # payroll
    model_cpp_ei: bool
    cpp_rate: float
    cpp_base_rate: float
    cpp_exempt: float
    cpp_ympe: float
    cpp2_rate: float
    cpp2_yampe: float
    ei_rate: float
    ei_mie: float
    cpp_ei_bump: bool       # add the freed-up take-home to savings once they max out
    # goal
    goal: float
    goal_basis: str             # "gross" | "net"
    rrsp_withdraw_rate: float
    require_mort_paid: bool
    # horizon
    max_months: int
    start: date


def month_date(cfg, idx):
    y = cfg.start.year + (cfg.start.month - 1 + idx) // 12
    m = (cfg.start.month - 1 + idx) % 12 + 1
    return date(y, m, 1)


def month_label(cfg, idx):
    d = month_date(cfg, idx)
    return f"{MONTHS_ABBR[d.month - 1]} {d.year}"


def next_month_start(today=None):
    """First of the month after `today` — the projection always starts next month."""
    d = today or date.today()
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)


# ─── Simulation ───────────────────────────────────────────────────────────────
def run_scenario(cfg, invest_pct):
    """Project one invest-vs-prepay split month by month.

    `invest_pct` of each month's free cash goes into the investment waterfall and
    the rest at the mortgage. The run stops the month the goal is met, so every
    summary it returns is "as at stop" — see `months_run` for the horizon behind
    the numbers.
    """
    p = invest_pct / 100.0

    bal = {"RRSP – You": cfg.you.rrsp_bal, "TFSA – You": cfg.you.tfsa_bal,
           "RRSP – Spouse": cfg.spouse.rrsp_bal, "TFSA – Spouse": cfg.spouse.tfsa_bal,
           NONREG: cfg.nonreg_bal}
    room = {"RRSP – You": cfg.you.rrsp_room, "TFSA – You": cfg.you.tfsa_room,
            "RRSP – Spouse": cfg.spouse.rrsp_room, "TFSA – Spouse": cfg.spouse.tfsa_room}
    contrib_total = {k: 0.0 for k in BUCKETS}

    inc = {"you": cfg.you.income, "sp": cfg.spouse.income}
    # Contributions already made earlier in the start calendar year still generate
    # a refund, so they seed this year's deduction pool. They are assumed to be
    # already reflected in the remaining room entered above, so room is untouched.
    deduct = {"you": cfg.you.ytd_rrsp, "sp": cfg.spouse.ytd_rrsp}
    grp_pct = cfg.spouse.employee_pct + cfg.spouse.employer_pct
    # Under a group RRSP the employer's share of those YTD contributions was also
    # taxable income, so it has to be added back before the refund is valued.
    extra_inc_sp = (cfg.spouse.ytd_rrsp * cfg.spouse.employer_pct / grp_pct
                    if cfg.group_is_rrsp and grp_pct > 0 else 0.0)

    savings      = cfg.savings
    tfsa_annual  = cfg.tfsa_annual
    rrsp_max     = cfg.rrsp_annual_max
    mort         = cfg.mort_bal
    mort_rate_m  = cfg.mort_rate / 12
    mort_monthly = cfg.mort_weekly * 52 / 12
    inv_rate_m   = cfg.inv_return / 100 / 12
    nonreg_rate_m = cfg.inv_return / 100 * (1 - cfg.nonreg_drag / 100) / 12

    # This year's CPP and EI, month by month, for each person. Rebuilt every
    # January because salaries and the maximums both move.
    sched_you = payroll_schedule(cfg.you.income, cfg)
    sched_sp = payroll_schedule(cfg.spouse.income + (cfg.spouse.income * cfg.spouse.employer_pct
                                                    / 100 if cfg.group_is_rrsp else 0.0), cfg)

    prepay_used = refund_due = pa_accum = 0.0
    total_refund = total_idle = total_payroll = 0.0
    total_cpp_ei = 0.0
    mort_paid_label = goal_label = None
    goal_idx = None
    rows = []

    for i in range(cfg.max_months):
        d, lbl = month_date(cfg, i), month_label(cfg, i)

        # ── New calendar year: file last year's return, then accrue new room ──
        if d.month == 1 and i > 0:
            refund_due = (refund_for(inc["you"], deduct["you"], cfg)
                          + refund_for(inc["sp"] + extra_inc_sp, deduct["sp"], cfg))
            # RRSP room accrues on the year just ended, net of any pension
            # adjustment; TFSA room accrues at the flat annual amount.
            room["RRSP – You"] += min(inc["you"] * cfg.rrsp_accrual_pct / 100, rrsp_max)
            room["RRSP – Spouse"] += max(0.0, min(inc["sp"] * cfg.rrsp_accrual_pct / 100,
                                                  rrsp_max) - pa_accum)
            room["TFSA – You"] += tfsa_annual
            room["TFSA – Spouse"] += tfsa_annual
            pa_accum = prepay_used = extra_inc_sp = 0.0
            deduct = {"you": 0.0, "sp": 0.0}
            inc["you"] *= 1 + cfg.salary_growth / 100
            inc["sp"]  *= 1 + cfg.salary_growth / 100
            savings    *= 1 + cfg.savings_growth / 100
            tfsa_annual *= 1 + cfg.limit_indexation / 100
            rrsp_max    *= 1 + cfg.limit_indexation / 100
            sched_you = payroll_schedule(inc["you"], cfg)
            sched_sp = payroll_schedule(inc["sp"] + (inc["sp"] * cfg.spouse.employer_pct / 100
                                                     if cfg.group_is_rrsp else 0.0), cfg)

        # ── Spouse's group plan, deducted at source before any other saving ──
        ee = inc["sp"] * cfg.spouse.employee_pct / 100 / 12
        er = inc["sp"] * cfg.spouse.employer_pct / 100 / 12
        if cfg.group_is_rrsp:
            # A group RRSP consumes the member's own RRSP room, so both halves are
            # scaled back together once that room runs out.
            if ee + er > room["RRSP – Spouse"]:
                scale = room["RRSP – Spouse"] / (ee + er) if ee + er > 0 else 0.0
                ee, er = ee * max(0.0, scale), er * max(0.0, scale)
            room["RRSP – Spouse"] -= ee + er
            deduct["sp"] += ee + er
            extra_inc_sp += er          # employer match is a taxable benefit
        else:
            # DC pension: employer money is not income, only the employee half is
            # deductible, and the pension adjustment eats next year's RRSP room.
            deduct["sp"] += ee
            pa_accum += ee + er
        # Deposited after the growth step below, alongside every other
        # contribution, so a month's return is not credited on it twice.
        payroll_in = ee + er
        contrib_total["RRSP – Spouse"] += payroll_in
        total_payroll += payroll_in

        # ── CPP and EI for this month ──
        cpp_you, ei_you, full_you = sched_you[d.month - 1]
        cpp_sp, ei_sp, full_sp = sched_sp[d.month - 1]
        cpp_ei_month = cpp_you + ei_you + cpp_sp + ei_sp
        total_cpp_ei += cpp_ei_month
        # Once the year's maximums are reached the deductions stop and take-home
        # rises. Whether that shows up as extra saving is the household's call.
        freed_payroll = ((full_you - cpp_you - ei_you) + (full_sp - cpp_sp - ei_sp)
                         if cfg.cpp_ei_bump else 0.0)

        # ── Cash available this month ──
        bonus = cfg.bonus if d.month == cfg.bonus_month else 0.0
        freed = mort_monthly if (mort <= 0 and cfg.redirect_freed) else 0.0
        base_cash = (savings + bonus + freed + freed_payroll
                     - (ee if cfg.payroll_from_savings else 0.0))
        base_cash = max(0.0, base_cash)

        refund_paid = 0.0
        if d.month == cfg.refund_month and refund_due > 0:
            refund_paid, refund_due = refund_due, 0.0
            total_refund += refund_paid
        deploy = 0.0 if cfg.refund_rule == "Spend it" else refund_paid

        if cfg.refund_rule == "All to investments":
            invest_cash, mort_cash = base_cash * p + deploy, base_cash * (1 - p)
        elif cfg.refund_rule == "All to mortgage":
            invest_cash, mort_cash = base_cash * p, base_cash * (1 - p) + deploy
        else:   # "Follow the split" and "Spend it" (deploy is 0 for the latter)
            invest_cash = (base_cash + deploy) * p
            mort_cash   = (base_cash + deploy) - invest_cash

        # ── Mortgage: scheduled payment first, then prepayment ──
        interest = mort * mort_rate_m
        sched_principal = min(mort_monthly - interest, mort) if mort > 0 else 0.0
        # Prepayment can only touch what the scheduled principal leaves behind.
        room_to_prepay = max(0.0, mort - sched_principal)
        cap = (max(0.0, cfg.mort_orig * cfg.prepay_pct / 100 - prepay_used)
               if cfg.prepay_enforce else float("inf"))
        extra = max(0.0, min(mort_cash, room_to_prepay, cap))
        prepay_used += extra
        mort = max(0.0, mort - sched_principal - extra)
        if mort <= 0 and mort_paid_label is None:
            mort_paid_label = lbl

        # Cash the annual prepayment privilege refuses either gets invested or
        # sits idle, depending on the spill setting. Once the mortgage is gone
        # there is nothing to prepay, so it is always invested.
        idle = mort_cash - extra
        if mort <= 0 or cfg.spill_to_invest:
            invest_cash += idle
            idle = 0.0
        total_idle += idle

        # ── Growth, then this month's contributions ──
        for k in bal:
            bal[k] *= 1 + (nonreg_rate_m if k == NONREG else inv_rate_m)

        contrib = {k: 0.0 for k in BUCKETS}
        bal["RRSP – Spouse"] += payroll_in
        contrib["RRSP – Spouse"] += payroll_in
        order = list(cfg.waterfall)
        if NONREG not in order:
            order.append(NONREG)        # always the overflow of last resort
        remaining = invest_cash
        for b in order:
            if remaining <= 1e-9:
                break
            amt = remaining if b == NONREG else min(remaining, max(0.0, room.get(b, 0.0)))
            if amt <= 0:
                continue
            bal[b] += amt
            contrib[b] += amt
            contrib_total[b] += amt
            if b in room:
                room[b] -= amt
            if b.startswith("RRSP"):
                deduct["you" if "You" in b else "sp"] += amt
            remaining -= amt

        rrsp_bal = bal["RRSP – You"] + bal["RRSP – Spouse"]
        gross_total = sum(bal.values())
        net_total = gross_total - rrsp_bal * cfg.rrsp_withdraw_rate / 100
        measure = net_total if cfg.goal_basis == "net" else gross_total

        rows.append({"idx": i, "label": lbl, "mort_bal": mort, "inv_bal": gross_total,
                     "net_bal": net_total, "mort_interest": interest, "mort_extra": extra,
                     "invested": invest_cash, "refund": refund_paid, "idle": idle,
                     "rrsp": rrsp_bal, "tfsa": bal["TFSA – You"] + bal["TFSA – Spouse"],
                     "nonreg": bal[NONREG], "group": payroll_in, "cpp_ei": cpp_ei_month,
                     "contrib_in": sum(contrib.values()),
                     **{f"c_{b}": contrib[b] for b in BUCKETS}})

        if goal_label is None and measure >= cfg.goal and (mort <= 0 or not cfg.require_mort_paid):
            goal_label, goal_idx = lbl, i
            break       # stop at the goal; scenarios that miss it run the full horizon

    return {
        "rows": rows, "months_run": len(rows),
        "mort_paid": mort_paid_label or "Not paid off",
        "goal_reached": goal_label,
        "goal_idx": goal_idx if goal_idx is not None else 10 ** 9,
        "final_inv": rows[-1]["inv_bal"], "final_net": rows[-1]["net_bal"],
        "final_mort": rows[-1]["mort_bal"], "final_rrsp": rows[-1]["rrsp"],
        "final_tfsa": rows[-1]["tfsa"], "final_nonreg": rows[-1]["nonreg"],
        "total_interest": sum(r["mort_interest"] for r in rows),
        "total_invested": sum(r["invested"] for r in rows),
        "total_prepaid": sum(r["mort_extra"] for r in rows),
        "total_refund": total_refund, "total_idle": total_idle,
        "total_cpp_ei": total_cpp_ei,
        "total_payroll": total_payroll, "contrib_total": contrib_total,
        "room_left": dict(room),
    }


def generate_colors(n):
    colors = []
    for i in range(max(n, 1)):
        r, g, b = colorsys.hls_to_rgb((i / max(n, 1) + 0.56) % 1.0, 0.62, 0.85)
        colors.append(f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}")
    return colors


def money(x):
    return f"${x:,.0f}"


# ─── Saved settings ───────────────────────────────────────────────────────────
# Every sidebar widget's default lives in one table, so the same definition drives
# the initial render, what gets stored, and the type a loaded value has to conform
# to.

DEFAULTS = {
    "inc_you": 130_000.0, "inc_sp": 67_000.0, "salary_growth": 0.0,
    "savings": 4_500.0, "expenses": 7_000.0, "savings_growth": 0.0,
    "bonus": 0.0, "bonus_month": 4,
    "rrsp_bal_you": 34_289.0, "tfsa_bal_you": 1_097.0,
    "rrsp_bal_sp": 35_000.0, "tfsa_bal_sp": 11_756.0, "nonreg_bal": 0.0,
    "rrsp_room_you": 50_000.0, "rrsp_room_sp": 13_833.0,
    "tfsa_room_you": 63_000.0, "tfsa_room_sp": 52_169.72,
    "tfsa_annual": 7_000.0, "rrsp_accrual_pct": 18.0,
    "rrsp_annual_max": 32_490.0, "limit_indexation": 0.0,
    "ytd_you": 6_194.0, "ytd_sp": 0.0,
    "employee_pct": 7.0, "employer_pct": 7.0,
    "plan_kind": "Group RRSP", "payroll_from_savings": False,
    "inv_return": 6.0, "nonreg_drag": 20.0,
    "mort_bal": 268_000.0, "mort_rate": 5.4, "mort_weekly": 441.96,
    "prepay_enforce": True, "prepay_pct": 20.0, "mort_orig": 290_000.0,
    "spill_to_invest": True, "redirect_freed": True,
    "waterfall": ["RRSP – You", "TFSA – You", "TFSA – Spouse", "RRSP – Spouse"],
    "refund_month": 4, "refund_rule": "Follow the split",
    "goal": 700_000.0, "goal_basis": "Gross balances",
    "rrsp_withdraw_rate": 25.0, "require_mort_paid": True,
    "horizon_years": 10, "lo": 1, "hi": 99, "step": 1,
    "fed_bpa": FED_BPA_DEFAULT, "ab_bpa": AB_BPA_DEFAULT,
    "model_cpp_ei": True, "cpp_ei_bump": False,
    "cpp_rate": CPP_RATE_DEFAULT, "cpp_base_rate": CPP_BASE_RATE_DEFAULT,
    "cpp_exempt": CPP_EXEMPT_DEFAULT, "cpp_ympe": CPP_YMPE_DEFAULT,
    "cpp2_rate": CPP2_RATE_DEFAULT, "cpp2_yampe": CPP2_YAMPE_DEFAULT,
    "ei_rate": EI_RATE_DEFAULT, "ei_mie": EI_MIE_DEFAULT,
    "detail_view": "💵 Money in",
    "fed_brackets": [[None if l == float("inf") else l, r] for l, r in FED_BRACKETS_DEFAULT],
    "ab_brackets": [[None if l == float("inf") else l, r] for l, r in AB_BRACKETS_DEFAULT],
}

# Keys whose value has to be one of a fixed set — a hand-edited file naming
# something else is rejected rather than crashing the widget that reads it.
CHOICES = {
    "plan_kind": ["Group RRSP", "DC pension"],
    "refund_rule": ["Follow the split", "All to investments", "All to mortgage", "Spend it"],
    "goal_basis": ["Gross balances", "After-tax (RRSP discounted)"],
    "detail_view": ["💵 Money in", "📊 Balances", "Both"],
    "bonus_month": list(range(1, 13)),
    "refund_month": list(range(1, 13)),
}
BRACKET_KEYS = ("fed_brackets", "ab_brackets")


def coerce(key, val):
    """Conform a loaded value to the shape of its default, or None if unusable."""
    default = DEFAULTS[key]
    try:
        if key in BRACKET_KEYS:
            rows = [[None if lim is None else float(lim), float(rate)] for lim, rate in val]
            return rows or None
        if key == "waterfall":
            return [b for b in val if b in BUCKETS]   # an empty waterfall is legitimate
        if isinstance(default, bool):                 # before int: bools are ints
            out = bool(val)
        elif isinstance(default, int):
            out = int(val)
        elif isinstance(default, float):
            out = float(val)
        else:
            out = str(val)
    except (TypeError, ValueError):
        return None
    return out if key not in CHOICES or out in CHOICES[key] else None


def parse_config(raw):
    """Validate decoded JSON into settings. Returns (settings, note)."""
    if not isinstance(raw, dict):
        return {}, "That is not a settings file."
    cfg, rejected = {}, []
    for key, val in raw.items():
        if key not in DEFAULTS:
            continue            # a key from an older version: ignore it quietly
        clean = coerce(key, val)
        if clean is None:
            rejected.append(key)
        else:
            cfg[key] = clean
    note = f"Ignored unusable values for: {', '.join(sorted(rejected))}." if rejected else None
    return cfg, note


def encode_settings(cfg):
    """Pack settings into a short code that survives being emailed or messaged.

    Only the settings that differ from the built-in defaults are carried, which
    keeps a typical code short; loading one overwrites every widget, so the keys
    left out land on their defaults rather than on whatever the other device had.
    Compressed before encoding, and urlsafe base64 so that nothing in it gets
    mangled by a chat client or a URL bar.
    """
    changed = {k: v for k, v in cfg.items() if k not in DEFAULTS or v != DEFAULTS[k]}
    raw = json.dumps(changed, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii")


def decode_settings(text):
    """Read back a share code, or plain settings JSON. Returns (settings, error)."""
    text = (text or "").strip()
    if not text:
        return None, "Nothing pasted."
    if text.startswith("{"):
        try:
            return json.loads(text), None
        except ValueError as err:
            return None, f"That looks like settings JSON but will not parse ({err})."
    # Mail and chat clients wrap long codes, so put the line back together and
    # restore any padding that got trimmed along the way.
    packed = "".join(text.split())
    try:
        blob = base64.urlsafe_b64decode(packed + "=" * (-len(packed) % 4))
        return json.loads(zlib.decompress(blob).decode("utf-8")), None
    except (ValueError, zlib.error, UnicodeDecodeError):
        return None, "That is not a settings code. Copy the whole code and try again."


def gather_config(fed_brackets, ab_brackets):
    """Snapshot every widget's current value, plus the parsed bracket tables."""
    cfg = {k: st.session_state[k] for k in DEFAULTS
           if k not in BRACKET_KEYS and k in st.session_state}
    for key, brackets in (("fed_brackets", fed_brackets), ("ab_brackets", ab_brackets)):
        cfg[key] = [[None if lim == float("inf") else lim, rate] for lim, rate in brackets]
    return cfg


WIDGET_KEYS = [k for k in DEFAULTS if k not in BRACKET_KEYS]


def apply_config(cfg, source):
    """Adopt a different set of settings and restart the script.

    The settings are only queued here. They are written into the widgets at the
    top of the next run by `consume_pending`, because a widget's value cannot be
    set through session_state once that widget has been created — and most of the
    callers of this are buttons at the bottom of the script.
    """
    st.session_state._pending_cfg = (cfg, source)
    st.rerun()


def consume_pending():
    """Push queued settings into the widgets. Must run before any widget exists.

    Assigning through session_state is the only thing that actually moves a keyed
    widget: a `value=` argument is ignored once the browser holds a value for that
    widget, which is exactly the case when settings arrive from storage after the
    first render.
    """
    if "_pending_cfg" not in st.session_state:
        return
    cfg, source = st.session_state.pop("_pending_cfg")
    st.session_state._cfg = cfg
    st.session_state._cfg_source = source
    for key in WIDGET_KEYS:
        st.session_state[key] = cfg.get(key, DEFAULTS[key])
    # The bracket editors hold pending cell edits rather than values, so they are
    # rebuilt under a fresh key instead — see `editor_key`.
    st.session_state._cfg_gen = st.session_state.get("_cfg_gen", 0) + 1
    for key in [k for k in st.session_state if k.startswith(("fed_df_", "ab_df_"))]:
        st.session_state.pop(key, None)


def seed_widgets():
    """Give every widget its starting value before the sidebar is built."""
    for key in WIDGET_KEYS:
        st.session_state.setdefault(key, d(key))


def editor_key(name):
    """A key that changes whenever settings are loaded, so the grid is rebuilt."""
    return f"{name}_{st.session_state.get('_cfg_gen', 0)}"


# ─── Browser storage ──────────────────────────────────────────────────────────
# Settings live in the browser's localStorage, not on the server. A hosted
# deployment wipes its disk on every redeploy, and a file there would be shared
# with everyone who opens the app — including these salary and balance figures.
# localStorage is per-browser, private, and survives redeploys.
_store = components.declare_component("coast_fire_store",
                                      path=str(pathlib.Path(__file__).parent / "store"))
st.markdown('<style>iframe[title="coast_fire_store"]{display:none!important;height:0!important}</style>',
            unsafe_allow_html=True)


def browser_store():
    """Exchange one message with localStorage.

    Returns the browser's reply, or None on the first run — the iframe has not
    answered yet, so the app renders defaults and adopts the stored settings when
    they arrive. A write is requested by leaving JSON in `_ls_write`; an empty
    string clears the store. The nonce makes Streamlit re-render the component for
    a repeated write of identical settings, which it would otherwise skip.
    """
    payload = st.session_state.pop("_ls_write", None)
    return _store(action="write" if payload is not None else "read", data=payload,
                  nonce=st.session_state.get("_ls_nonce", 0), key="_ls", default=None)


if "_cfg" not in st.session_state:
    st.session_state._cfg = {}
    st.session_state._cfg_source = "defaults"
    st.session_state._cfg_note = None
    st.session_state._saved = None          # nothing known to be stored yet
    st.session_state._ls_status = "waiting"

_reply = browser_store()
if _reply is not None:
    if not _reply.get("ok"):
        st.session_state._ls_status = "unavailable"
    else:
        st.session_state._ls_status = "ready"
        # Adopt what the browser had exactly once; later replies are echoes of
        # this same value and must not restart the script again.
        if _reply.get("action") == "read" and not st.session_state.get("_ls_adopted"):
            st.session_state._ls_adopted = True
            try:
                _decoded = json.loads(_reply["data"]) if _reply.get("data") else None
            except ValueError:
                _decoded = None
                st.session_state._cfg_note = "Stored settings were unreadable. Using defaults."
            if _decoded is not None:
                _found, _note = parse_config(_decoded)
                if _found:
                    st.session_state._saved = dict(_found)
                    st.session_state._cfg_note = _note
                    apply_config(_found, "browser storage")


def d(key):
    """The default a widget should render with: saved value, else built-in."""
    return st.session_state.get("_cfg", {}).get(key, DEFAULTS[key])


consume_pending()
seed_widgets()

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Settings")
    # Filled in at the end of the script, once the bracket tables have been parsed
    # and there is a complete picture of the settings to save.
    settings_io = st.container()

    with st.expander("👤 Household income", expanded=True):
        inc_you = st.number_input("Your gross salary ($/yr)",  min_value=0.0,
                                  step=1_000.0, format="%.0f", key="inc_you")
        inc_sp = st.number_input("Spouse gross salary ($/yr)",  min_value=0.0,
                                 step=1_000.0, format="%.0f", key="inc_sp")
        salary_growth = st.number_input("Annual salary growth (%)", 
                                        min_value=0.0, max_value=15.0, step=0.5,
                                        key="salary_growth")

    with st.expander("💵 Cash flow", expanded=True):
        savings = st.number_input("Monthly savings ($)",  min_value=0.0,
                                  step=100.0, format="%.0f", key="savings")
        expenses = st.number_input("Monthly expenses ($)",  min_value=0.0,
                                   step=100.0, format="%.0f", key="expenses")
        st.caption(f"Expenses are for reference only — they size the FIRE target below, "
                   f"they are not deducted from savings. 25× annual expenses = "
                   f"{money(expenses * 12 * 25)}.")
        savings_growth = st.number_input("Annual savings growth (%)", 
                                         min_value=0.0, max_value=20.0, step=0.5,
                                         key="savings_growth")
        bonus = st.number_input("Extra annual bonus ($)",  min_value=0.0,
                                step=500.0, format="%.0f", key="bonus")
        bonus_month = st.selectbox("Bonus month", CHOICES["bonus_month"],
                                   
                                   format_func=lambda m: MONTHS_ABBR[m - 1], key="bonus_month")
        st.caption("Separate from the tax refund, which is computed below.")

    with st.expander("🏦 Current balances"):
        rrsp_bal_you = st.number_input("RRSP – you ($)",  min_value=0.0,
                                       step=1_000.0, format="%.0f", key="rrsp_bal_you")
        tfsa_bal_you = st.number_input("TFSA – you ($)",  min_value=0.0,
                                       step=1_000.0, format="%.0f", key="tfsa_bal_you")
        rrsp_bal_sp = st.number_input("RRSP – spouse ($)",  min_value=0.0,
                                      step=1_000.0, format="%.0f", key="rrsp_bal_sp")
        tfsa_bal_sp = st.number_input("TFSA – spouse ($)",  min_value=0.0,
                                      step=1_000.0, format="%.0f", key="tfsa_bal_sp")
        nonreg_bal = st.number_input("Non-registered ($)",  min_value=0.0,
                                     step=1_000.0, format="%.0f", key="nonreg_bal")
        _tot = rrsp_bal_you + tfsa_bal_you + rrsp_bal_sp + tfsa_bal_sp + nonreg_bal
        st.caption(f"Total invested today: **{money(_tot)}**")

    with st.expander("📥 Contribution room"):
        rrsp_room_you = st.number_input("RRSP room – you ($)", 
                                        min_value=0.0, step=1_000.0, format="%.0f",
                                        key="rrsp_room_you")
        rrsp_room_sp = st.number_input("RRSP room – spouse ($)", 
                                       min_value=0.0, step=1_000.0, format="%.0f",
                                       key="rrsp_room_sp")
        tfsa_room_you = st.number_input("TFSA room – you ($)", 
                                        min_value=0.0, step=1_000.0, format="%.0f",
                                        key="tfsa_room_you")
        tfsa_room_sp = st.number_input("TFSA room – spouse ($)", 
                                       min_value=0.0, step=1_000.0, format="%.0f",
                                       key="tfsa_room_sp")
        st.caption("Enter each person's own remaining room from their latest CRA notice — "
                   "TFSA and RRSP room is per person, not per household.")
        tfsa_annual = st.number_input("New TFSA room each year ($)", 
                                      min_value=0.0, step=500.0, format="%.0f", key="tfsa_annual")
        rrsp_accrual_pct = st.number_input("RRSP accrual (% of prior-year income)",
                                            min_value=0.0,
                                           max_value=30.0, step=0.5, key="rrsp_accrual_pct")
        rrsp_annual_max = st.number_input("RRSP annual dollar limit ($)", 
                                          min_value=0.0, step=500.0, format="%.0f",
                                          key="rrsp_annual_max")
        limit_indexation = st.number_input("Annual indexation of those limits (%)",
                                            min_value=0.0,
                                           max_value=10.0, step=0.5, key="limit_indexation")
        ytd_you = st.number_input("RRSP already contributed this year – you ($)", 
                                  min_value=0.0, step=500.0, format="%.0f", key="ytd_you")
        ytd_sp = st.number_input("RRSP already contributed this year – spouse ($)",
                                  min_value=0.0, step=500.0, format="%.0f",
                                 key="ytd_sp")
        st.caption("Contributions made earlier this calendar year still earn a refund at the "
                   "next filing, so enter them here. Assumed already netted out of the "
                   "remaining room above.")

    with st.expander("🤝 Spouse group plan"):
        employee_pct = st.number_input("Spouse contributes (% of salary)", 
                                       min_value=0.0, max_value=30.0, step=0.5, key="employee_pct")
        employer_pct = st.number_input("Employer matches (% of salary)", 
                                       min_value=0.0, max_value=30.0, step=0.5, key="employer_pct")
        plan_kind = st.radio("Plan type", CHOICES["plan_kind"], 
                             key="plan_kind",
                             help="Group RRSP: the employer match is taxable income, both halves "
                                  "are deductible, and both consume the spouse's RRSP room. "
                                  "DC pension: employer money is not income, only the employee "
                                  "half is deductible, and a pension adjustment reduces next "
                                  "year's RRSP room instead.")
        payroll_from_savings = st.checkbox("Fund the spouse's share out of monthly savings",
                                           
                                           key="payroll_from_savings",
                                           help="Off = it comes off her paycheque, so the monthly "
                                                "savings figure above is already net of it.")
        st.caption(f"Group plan flow: {money(inc_sp * (employee_pct + employer_pct) / 100)}/yr "
                   f"({money(inc_sp * employee_pct / 100)} hers + "
                   f"{money(inc_sp * employer_pct / 100)} matched).")

    with st.expander("📈 Returns"):
        inv_return = st.number_input("Annual return (%)",  min_value=0.0,
                                     max_value=20.0, step=0.5, key="inv_return")
        nonreg_drag = st.number_input("Tax drag on non-registered returns (%)",
                                       min_value=0.0, max_value=60.0,
                                      step=1.0, key="nonreg_drag")
        st.caption("Drag is applied as a haircut to the return earned inside the "
                   "non-registered account only.")

    with st.expander("🏠 Mortgage"):
        mort_bal = st.number_input("Balance ($)",  min_value=0.0,
                                   step=5_000.0, format="%.0f", key="mort_bal")
        mort_rate = st.number_input("Interest rate (%)",  min_value=0.0,
                                    max_value=20.0, step=0.1, key="mort_rate") / 100
        mort_weekly = st.number_input("Scheduled payment ($/week)", 
                                      min_value=0.0, step=10.0, format="%.0f", key="mort_weekly")
        prepay_enforce = st.checkbox("Enforce annual prepayment privilege",
                                      key="prepay_enforce")
        prepay_pct = st.number_input("Privilege (% of original principal per year)",
                                      min_value=0.0, max_value=100.0,
                                     step=1.0, key="prepay_pct", disabled=not prepay_enforce)
        mort_orig = st.number_input("Original principal ($)",  min_value=0.0,
                                    step=5_000.0, format="%.0f", key="mort_orig",
                                    disabled=not prepay_enforce,
                                    help="The privilege is a percentage of the original amount "
                                         "borrowed, not of the balance outstanding today.")
        spill_to_invest = st.checkbox("Invest cash the privilege blocks", 
                                      key="spill_to_invest",
                                      help="Off = that cash is held back out of the plan "
                                           "entirely rather than invested. It is reported "
                                           "separately, not carried into a later month.")
        redirect_freed = st.checkbox("Redirect the payment once the mortgage is gone",
                                      key="redirect_freed")
        st.caption(f"Scheduled payment is {money(mort_weekly * 52 / 12)}/mo and is assumed to be "
                   f"paid *outside* the monthly savings figure. Privilege resets each January.")

    with st.expander("🪜 Allocation waterfall"):
        waterfall = st.multiselect("Priority order for invested dollars", BUCKETS,
                                    key="waterfall")
        st.caption("Each bucket fills to its remaining room before the next one starts. "
                   "Non-registered always catches whatever is left over, so it does not need "
                   "to be listed unless you want it earlier in the queue.")

    with st.expander("🧾 Tax refund"):
        refund_month = st.selectbox("Refund lands in", CHOICES["refund_month"],
                                    
                                    format_func=lambda m: MONTHS_ABBR[m - 1], key="refund_month")
        refund_rule = st.radio("What happens to it", CHOICES["refund_rule"],
                                key="refund_rule")
        st.caption("The refund is computed each January from that year's RRSP deductions at "
                   "the household's actual Alberta + federal rates, then paid out in the month "
                   "chosen here.")

    with st.expander("🎯 Goal & horizon", expanded=True):
        goal = st.number_input("Target portfolio ($)",  min_value=10_000.0,
                               step=10_000.0, format="%.0f", key="goal")
        goal_basis = st.radio("Measured on", CHOICES["goal_basis"],
                               key="goal_basis")
        rrsp_withdraw_rate = st.number_input("Assumed RRSP withdrawal tax rate (%)",
                                              min_value=0.0,
                                             max_value=60.0, step=1.0, key="rrsp_withdraw_rate")
        require_mort_paid = st.checkbox("Goal also requires the mortgage cleared",
                                         key="require_mort_paid")
        horizon_years = st.number_input("Horizon (years)",  min_value=1,
                                        max_value=40, step=1, key="horizon_years")
        st.markdown("**Splits to sweep**")
        c1, c2, c3 = st.columns(3)
        sweep_lo = c1.number_input("From %",  min_value=0, max_value=100, step=1,
                                   key="lo")
        sweep_hi = c2.number_input("To %",  min_value=0, max_value=100, step=1,
                                   key="hi")
        sweep_step = c3.number_input("Step",  min_value=1, max_value=50, step=1,
                                     key="step")

# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown("# 🎯 Coast FIRE Scenario Planner")
st.markdown(f"*{horizon_years}-year projection — find the optimal invest/prepay split to reach "
            f"{money(goal)} invested{' + a paid-off home' if require_mort_paid else ''} · "
            f"savings: {money(savings)}/mo · RRSP + TFSA room and the Alberta tax refund modelled*")

# ─── Read me ──────────────────────────────────────────────────────────────────
# Rendered straight from README.md rather than duplicated here, so the reference
# in the app and the one in the repo cannot drift apart.
_readme = pathlib.Path(__file__).parent / "README.md"
if _readme.is_file():
    with st.expander("📖 Read me — what every setting does and how a month is simulated"):
        text = _readme.read_text(encoding="utf-8")
        # Drop the file's own H1; the page already carries the title above.
        if text.lstrip().startswith("# "):
            text = text.split("\n", 1)[1] if "\n" in text else ""
        st.markdown(text)

# ─── Tax tables ───────────────────────────────────────────────────────────────
# Rendered before the simulation so an edit here feeds straight into the run.
def bracket_df(brackets):
    return pd.DataFrame([{"Up to ($)": None if lim == float("inf") else lim,
                          "Rate (%)": rate * 100} for lim, rate in brackets])


def parse_brackets(df, fallback):
    """Turn the edited table back into (limit, rate) pairs, lowest bracket first.

    Rows are sorted by limit and the top one always runs to infinity, so a partly
    filled or out-of-order table still produces a usable schedule.
    """
    rows = []
    for _, r in df.iterrows():
        rate = r.get("Rate (%)")
        if rate is None or pd.isna(rate):
            continue
        lim = r.get("Up to ($)")
        rows.append((float("inf") if lim is None or pd.isna(lim) else float(lim), float(rate) / 100))
    if not rows:
        return fallback
    rows.sort(key=lambda t: t[0])
    rows[-1] = (float("inf"), rows[-1][1])
    return rows


with st.expander("🧾 Tax engine — federal & Alberta brackets (editable)"):
    st.caption("Defaults are the 2025 federal and Alberta schedules. Leave the top row's "
               "limit blank — the highest bracket always runs to infinity. Add or delete rows "
               "to roll the tables forward.")
    tc1, tc2, tc3 = st.columns([2, 2, 1.4])
    with tc1:
        st.markdown("**Federal**")
        fed_df = st.data_editor(bracket_df(d("fed_brackets")), num_rows="dynamic",
                                hide_index=True, width="stretch", key=editor_key("fed_df"))
    with tc2:
        st.markdown("**Alberta**")
        ab_df = st.data_editor(bracket_df(d("ab_brackets")), num_rows="dynamic",
                               hide_index=True, width="stretch", key=editor_key("ab_df"))
    with tc3:
        st.markdown("**Personal amounts**")
        fed_bpa = st.number_input("Federal BPA ($)",  min_value=0.0,
                                  step=100.0, format="%.0f", key="fed_bpa")
        ab_bpa = st.number_input("Alberta BPA ($)",  min_value=0.0,
                                 step=100.0, format="%.0f", key="ab_bpa")
        st.caption("Credited at the lowest bracket rate.")
    fed_brackets = parse_brackets(fed_df, FED_BRACKETS_DEFAULT)
    ab_brackets = parse_brackets(ab_df, AB_BRACKETS_DEFAULT)

    st.markdown("**Payroll — CPP & EI**")
    model_cpp_ei = st.checkbox("Model CPP and EI", key="model_cpp_ei",
                               help="Base CPP and EI are non-refundable credits; the enhanced "
                                    "slice of CPP and all of CPP2 are deductions, so they lower "
                                    "taxable income and can change which bracket an RRSP "
                                    "contribution unwinds.")
    pc1, pc2, pc3, pc4 = st.columns(4)
    with pc1:
        cpp_rate = st.number_input("CPP rate (%)", min_value=0.0, max_value=20.0, step=0.05,
                                   key="cpp_rate", disabled=not model_cpp_ei)
        cpp_base_rate = st.number_input("…of which credited (%)", min_value=0.0, max_value=20.0,
                                        step=0.05, key="cpp_base_rate",
                                        disabled=not model_cpp_ei,
                                        help="The rest is the enhanced slice, which is deducted "
                                             "from income instead of credited against tax.")
    with pc2:
        cpp_exempt = st.number_input("Basic exemption ($)", min_value=0.0, step=100.0,
                                     format="%.0f", key="cpp_exempt", disabled=not model_cpp_ei)
        cpp_ympe = st.number_input("YMPE ($)", min_value=0.0, step=100.0, format="%.0f",
                                   key="cpp_ympe", disabled=not model_cpp_ei)
    with pc3:
        cpp2_rate = st.number_input("CPP2 rate (%)", min_value=0.0, max_value=20.0, step=0.05,
                                    key="cpp2_rate", disabled=not model_cpp_ei)
        cpp2_yampe = st.number_input("YAMPE ($)", min_value=0.0, step=100.0, format="%.0f",
                                     key="cpp2_yampe", disabled=not model_cpp_ei)
    with pc4:
        ei_rate = st.number_input("EI rate (%)", min_value=0.0, max_value=20.0, step=0.01,
                                  key="ei_rate", disabled=not model_cpp_ei)
        ei_mie = st.number_input("EI max earnings ($)", min_value=0.0, step=100.0, format="%.0f",
                                 key="ei_mie", disabled=not model_cpp_ei)
    cpp_ei_bump = st.checkbox("Save the take-home freed up once CPP and EI max out",
                              key="cpp_ei_bump", disabled=not model_cpp_ei,
                              help="Both stop partway through the year, so pay rises for the "
                                   "remaining months. Off = the monthly savings figure is taken "
                                   "as an average that already allows for it.")
    st.caption("Defaults are the 2025 employee figures. Employer-side contributions are not "
               "modelled — they cost the household nothing. Credits beyond these and the basic "
               "personal amount are not modelled either.")

# ─── Build the configuration ──────────────────────────────────────────────────
START_MONTH = next_month_start()
cfg = Cfg(
    you=Person("You", inc_you, rrsp_bal_you, tfsa_bal_you, rrsp_room_you, tfsa_room_you, ytd_you),
    spouse=Person("Spouse", inc_sp, rrsp_bal_sp, tfsa_bal_sp, rrsp_room_sp, tfsa_room_sp,
                  ytd_sp, employee_pct, employer_pct),
    savings=savings, savings_growth=savings_growth, salary_growth=salary_growth,
    bonus=bonus, bonus_month=bonus_month,
    nonreg_bal=nonreg_bal, inv_return=inv_return, nonreg_drag=nonreg_drag,
    tfsa_annual=tfsa_annual, rrsp_accrual_pct=rrsp_accrual_pct,
    rrsp_annual_max=rrsp_annual_max, limit_indexation=limit_indexation,
    group_is_rrsp=(plan_kind == "Group RRSP"), payroll_from_savings=payroll_from_savings,
    mort_bal=mort_bal, mort_rate=mort_rate, mort_weekly=mort_weekly, mort_orig=mort_orig,
    prepay_pct=prepay_pct, prepay_enforce=prepay_enforce, redirect_freed=redirect_freed,
    waterfall=waterfall, spill_to_invest=spill_to_invest,
    refund_month=refund_month, refund_rule=refund_rule,
    fed_brackets=fed_brackets, ab_brackets=ab_brackets, fed_bpa=fed_bpa, ab_bpa=ab_bpa,
    model_cpp_ei=model_cpp_ei, cpp_rate=cpp_rate, cpp_base_rate=cpp_base_rate,
    cpp_exempt=cpp_exempt, cpp_ympe=cpp_ympe, cpp2_rate=cpp2_rate, cpp2_yampe=cpp2_yampe,
    ei_rate=ei_rate, ei_mie=ei_mie, cpp_ei_bump=cpp_ei_bump,
    goal=goal, goal_basis="net" if goal_basis.startswith("After-tax") else "gross",
    rrsp_withdraw_rate=rrsp_withdraw_rate, require_mort_paid=require_mort_paid,
    max_months=int(horizon_years) * 12, start=START_MONTH,
)

if cfg.mort_bal > 0 and cfg.mort_weekly * 52 / 12 <= cfg.mort_bal * cfg.mort_rate / 12:
    st.warning(f"The scheduled payment of {money(cfg.mort_weekly * 52 / 12)}/mo does not cover "
               f"the first month's interest of {money(cfg.mort_bal * cfg.mort_rate / 12)}. "
               f"The balance will grow unless prepayments cover the gap.")

# ─── Today's tax position ─────────────────────────────────────────────────────
# The spouse's employer match is taxable employment income under a group RRSP, so
# it is pensionable and insurable too and belongs in her gross here.
sp_match_now = cfg.spouse.income * employer_pct / 100 if cfg.group_is_rrsp else 0.0
sp_gross_now = cfg.spouse.income + sp_match_now
sp_own_now = cfg.spouse.income * employee_pct / 100

st.markdown("### 🧾 Tax position this year")
people = [("You", cfg.you.income, 0.0), ("Spouse", sp_gross_now, sp_own_now + sp_match_now)]
tax_rows = []
for label, gross, rrsp_now in people:
    base, enhanced, cpp2, ei = cpp_ei_for(gross, cfg)
    tax_rows.append({
        "": label,
        "💼 Gross": money(gross),
        "🧾 Income tax": money(total_tax(gross, cfg, rrsp_now)),
        "🍁 CPP": money(base + enhanced + cpp2),
        "🛟 EI": money(ei),
        "🏠 Take-home": money(take_home(gross, cfg, rrsp_now)),
        "📈 Marginal rate": f"{marginal_rate(gross, cfg):.1%}",
        "💰 Refund per $10k RRSP": money(refund_for(gross, 10_000, cfg)),
    })
total_row = {"": "Household"}
for col in list(tax_rows[0])[1:]:
    if col.endswith("rate"):
        total_row[col] = "—"
    else:
        total_row[col] = money(sum(float(r[col].replace("$", "").replace(",", ""))
                                   for r in tax_rows))
tax_rows.append(total_row)
st.dataframe(pd.DataFrame(tax_rows), width="stretch", hide_index=True)
st.caption(
    ("CPP and EI are modelled: base CPP and EI are credits, while the enhanced slice of CPP "
     "and all of CPP2 are deductions, so they lower taxable income. Both stop once the annual "
     "maximum is reached, which is why take-home rises later in the year. "
     if cfg.model_cpp_ei else
     "CPP and EI are switched off in the tax engine above, so these are income tax only. ")
    + "Income tax already reflects the RRSP contributions shown — the spouse's group plan runs "
      "all year, so her figures are net of it. The refund column prices a *further* $10,000 "
      "contribution as a full recalculation of tax with and without it, so a contribution "
      "straddling a bracket is valued correctly.")

# ─── Run the sweep ────────────────────────────────────────────────────────────
pcts = sorted({min(100, max(0, p)) for p in range(int(sweep_lo), int(sweep_hi) + 1, int(sweep_step))})
if not pcts:
    pcts = [50]
colors = generate_colors(len(pcts))
sim_results = []
for pct, color in zip(pcts, colors):
    res = run_scenario(cfg, pct)
    res.update({"name": f"{pct}% Invest / {100 - pct}% Mortgage", "color": color,
                "invest_pct": pct})
    sim_results.append(res)
N = len(sim_results)

# Mirror how run_scenario resolves the waterfall, so the caption cannot claim an
# order the simulation does not actually use.
display_order = list(waterfall)
if NONREG not in display_order:
    display_order.append(NONREG)
st.markdown(f'<div class="info-box">Every split from <b>{pcts[0]}%</b> to <b>{pcts[-1]}%</b> '
            f'invested (step {int(sweep_step)}) is projected on <b>{money(savings)}/mo</b> '
            f'savings. Invested dollars fill <b>{" → ".join(display_order)}</b> in that order, '
            f'to the room available. Adjust anything in the sidebar — results update '
            f'instantly.</div>', unsafe_allow_html=True)

goal_reached = [r for r in sim_results if r["goal_reached"]]
winner = min(goal_reached, key=lambda r: r["goal_idx"]) if goal_reached else None
# Across the sweep the fastest date is usually a plateau rather than a single
# winner, so track everyone who ties instead of crowning the lowest percentage.
tied = [r for r in goal_reached if r["goal_idx"] == winner["goal_idx"]] if winner else []

# ─── Winner banner ────────────────────────────────────────────────────────────
st.divider()
st.markdown("### Results")

if winner:
    band = (f"{tied[0]['invest_pct']}%–{tied[-1]['invest_pct']}% invest"
            if len(tied) > 1 else winner["name"])
    note = (f"📈 {len(tied)} splits tie — anything in that band is equally fast"
            if len(tied) > 1 else f"📈 {winner['invest_pct']}% invest")
    st.markdown(f"""
    <div style="background:linear-gradient(90deg,#1a3a2a,#122a1e);border-left:4px solid #51cf66;
    border-radius:8px;padding:12px 20px;margin-bottom:16px;font-family:'Space Mono',monospace;">
    🏆 <b style="color:#51cf66">FASTEST PATH:</b> &nbsp;
    <span style="color:#e8eaf0">{band}</span> &nbsp;—&nbsp;
    <span style="color:#51cf66">Goal reached {winner['goal_reached']}</span> &nbsp;|&nbsp;
    {note} &nbsp;|&nbsp; 💰 {money(savings)}/mo &nbsp;|&nbsp;
    🧾 {money(winner['total_refund'])} of refunds along the way
    </div>
    """, unsafe_allow_html=True)
    w1, w2, w3, w4, w5 = st.columns(5)
    w1.metric("🏠 Mortgage cleared", winner["mort_paid"])
    w2.metric("🧓 RRSP", money(winner["final_rrsp"]))
    w3.metric("🛡 TFSA", money(winner["final_tfsa"]))
    w4.metric("📇 Non-registered", money(winner["final_nonreg"]))
    w5.metric("💸 Mortgage interest", money(winner["total_interest"]))
else:
    st.markdown(f"""
    <div style="background:linear-gradient(90deg,#3a1a1a,#2a1212);border-left:4px solid #ff6b6b;
    border-radius:8px;padding:12px 20px;margin-bottom:16px;font-family:'Space Mono',monospace;color:#ff6b6b;">
    ⚠️ No split reaches {money(goal)}{' + a paid-off home' if require_mort_paid else ''} within
    {horizon_years} years. Try a longer horizon, more savings, or a higher return.
    </div>
    """, unsafe_allow_html=True)

# ─── Results table ────────────────────────────────────────────────────────────
comp_rows = []
for r in sim_results:
    is_w = bool(winner and r["goal_reached"] and r["goal_idx"] == winner["goal_idx"])
    comp_rows.append({
        "🏷 Scenario":     r["name"],
        "📈 Invest %":     f"{r['invest_pct']}%",
        "🏠 Mortgage %":   f"{100 - r['invest_pct']}%",
        "🎯 Goal Reached": r["goal_reached"] or "—",
        "⏱ Months Run":   f"{r['months_run']}" + ("" if r["goal_reached"] else " (max)"),
        "🏠 Mort Paid":    r["mort_paid"],
        "🧓 RRSP":         money(r["final_rrsp"]),
        "🛡 TFSA":         money(r["final_tfsa"]),
        "📇 Non-reg":      money(r["final_nonreg"]),
        "📊 Total":        money(r["final_inv"]),
        "💧 After-tax":    money(r["final_net"]),
        "🧾 Refunds":      money(r["total_refund"]),
        "💸 Interest":     money(r["total_interest"]),
        "🏆":              "✅" if is_w else "",
    })

st.caption("Each run stops the month its goal is met, so balances and interest are measured at "
           "that point — not over a common horizon. **Months Run** is the window behind each "
           f"row; rows marked *(max)* never met the goal and ran the full {horizon_years} years. "
           f"**After-tax** discounts RRSP balances by {rrsp_withdraw_rate:.0f}%.")
st.dataframe(pd.DataFrame(comp_rows), width="stretch", hide_index=True,
             height=min(42 * N + 60, 620))

# ─── Charts ───────────────────────────────────────────────────────────────────
st.divider()
st.markdown("### Charts")

# A sweep this wide makes a legend useless, so it is off — hover names the split.
CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(13,20,34,0.8)",
    font=dict(color="#7c90b0", family="Syne"),
    showlegend=False,
    margin=dict(t=20, b=20, l=10, r=10),
    # Runs stop at different months, so pin the category order instead of letting
    # it be inferred from whichever trace happens to be drawn first.
    xaxis=dict(gridcolor="#1e2d45", linecolor="#2a3550", categoryorder="array",
               categoryarray=[month_label(cfg, i) for i in range(cfg.max_months)]),
    yaxis=dict(gridcolor="#1e2d45", linecolor="#2a3550", tickprefix="$"),
)
LINE_W = 1.2
st.caption("Colour runs from the lowest invest % to the highest. Hover any line to identify it.")

tabs = st.tabs(["📈 Portfolio Growth", "🏠 Mortgage Balance", "💧 After-tax Portfolio",
                "📊 Monthly Invested", "🧩 Account Mix"])

def sweep_chart(tab, key, goal_line=False):
    with tab:
        fig = go.Figure()
        if goal_line:
            fig.add_hline(y=goal, line_dash="dash", line_color="#ffd43b", line_width=1.5,
                          annotation_text=f"{money(goal)} Goal", annotation_font_color="#ffd43b",
                          annotation_position="top left")
        for r in sim_results:
            fig.add_trace(go.Scatter(
                x=[row["label"] for row in r["rows"]], y=[row[key] for row in r["rows"]],
                name=r["name"], line=dict(color=r["color"], width=LINE_W),
                hovertemplate="%{x}<br>$%{y:,.0f}<extra>" + r["name"] + "</extra>"))
        fig.update_layout(height=500, **CHART_LAYOUT)
        st.plotly_chart(fig, width="stretch")

sweep_chart(tabs[0], "inv_bal", goal_line=(cfg.goal_basis == "gross"))
sweep_chart(tabs[1], "mort_bal")
sweep_chart(tabs[2], "net_bal", goal_line=(cfg.goal_basis == "net"))
sweep_chart(tabs[3], "invested")

with tabs[4]:
    mix_src = winner or sim_results[0]
    st.caption(f"Where the money sits over time under **{mix_src['name']}**"
               + (" (the fastest split)." if winner else "."))
    figm = go.Figure()
    for key, label, col in [("rrsp", "RRSP", "#4dabf7"), ("tfsa", "TFSA", "#51cf66"),
                            ("nonreg", "Non-registered", "#ffd43b")]:
        figm.add_trace(go.Scatter(
            x=[row["label"] for row in mix_src["rows"]], y=[row[key] for row in mix_src["rows"]],
            name=label, mode="lines", stackgroup="one", line=dict(width=0.5, color=col),
            hovertemplate="%{x}<br>$%{y:,.0f}<extra>" + label + "</extra>"))
    figm.update_layout(height=500, **{**CHART_LAYOUT, "showlegend": True,
                                      "legend": dict(orientation="h", y=1.08)})
    st.plotly_chart(figm, width="stretch")

# ─── Month-by-month detail ────────────────────────────────────────────────────
st.divider()
st.markdown("### 📅 Month-by-Month Detail")

default_idx = next((i for i, r in enumerate(sim_results)
                    if winner and r["invest_pct"] == winner["invest_pct"]), 0)
sel = st.selectbox("Scenario", range(N), index=default_idx,
                   format_func=lambda i: sim_results[i]["name"], key="detail_scenario")
detail = sim_results[sel]
# index= only applies on first render, so the dropdown keeps whatever was picked
# even after the winner moves. Call the fastest band out separately.
if winner and detail["goal_idx"] != winner["goal_idx"]:
    band = (f"{tied[0]['invest_pct']}%–{tied[-1]['invest_pct']}% invest ({len(tied)} splits tie)"
            if len(tied) > 1 else f"**{winner['name']}**")
    st.caption(f"🏆 Fastest at these settings is {band} — goal {winner['goal_reached']}. "
               f"Showing {detail['name']}.")

d1, d2, d3, d4 = st.columns(4)
d1.metric("🧾 Refunds received", money(detail["total_refund"]))
d2.metric("🏠 Extra to mortgage", money(detail["total_prepaid"]))
d3.metric("🤝 Group plan in", money(detail["total_payroll"]))
d4.metric("💤 Cash left idle", money(detail["total_idle"]),
          help="Cash the annual prepayment privilege refused while spilling was off. It is "
               "held back out of the plan rather than carried into a later month.")

left = detail["room_left"]
st.markdown(f'<div class="info-box">Room left at stop — '
            f'RRSP you {money(left["RRSP – You"])} · RRSP spouse {money(left["RRSP – Spouse"])} · '
            f'TFSA you {money(left["TFSA – You"])} · TFSA spouse {money(left["TFSA – Spouse"])}'
            f'</div>', unsafe_allow_html=True)

# Group the projection into calendar years — the first and last are part years,
# since the run starts next month rather than in January.
years = {}
for row in detail["rows"]:
    years.setdefault(month_date(cfg, row["idx"]).year, []).append(row)

goal_row = detail["goal_idx"] if detail["goal_reached"] else None
detail_view = st.radio("Show", CHOICES["detail_view"], horizontal=True, key="detail_view")
show_in = detail_view in ("💵 Money in", "Both")
show_bal = detail_view in ("📊 Balances", "Both")


def money_in_columns(r):
    """What went where this month, per account and per person."""
    cols = {
        "🧓 RRSP – You":    money(r["c_RRSP – You"]),
        "🧓 RRSP – Spouse": money(r["c_RRSP – Spouse"]),
        "↳ of which group plan": money(r["group"]),
        "🛡 TFSA – You":     money(r["c_TFSA – You"]),
        "🛡 TFSA – Spouse":  money(r["c_TFSA – Spouse"]),
        "📇 Non-registered": money(r[f"c_{NONREG}"]),
        "Σ Into investments": money(r["contrib_in"]),
        "🏠 Extra to mortgage": money(r["mort_extra"]),
        "🧾 Refund in":      money(r["refund"]),
    }
    if cfg.model_cpp_ei:
        cols["💸 CPP + EI paid"] = money(r["cpp_ei"])
    return cols


def balance_columns(r):
    return {
        "🏠 Mortgage":  money(r["mort_bal"]),
        "🧓 RRSP":      money(r["rrsp"]),
        "🛡 TFSA":      money(r["tfsa"]),
        "📇 Non-reg":   money(r["nonreg"]),
        "📊 Total":     money(r["inv_bal"]),
        "💧 After-tax": money(r["net_bal"]),
    }


for ytab, (yr, yrows) in zip(st.tabs([str(y) for y in years]), years.items()):
    with ytab:
        first, last = yrows[0], yrows[-1]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🏠 Mortgage at year end", money(last["mort_bal"]),
                  f"{last['mort_bal'] - first['mort_bal']:+,.0f}")
        c2.metric("📊 Portfolio at year end", money(last["inv_bal"]),
                  f"{last['inv_bal'] - first['inv_bal']:+,.0f}")
        c3.metric("💵 Into investments", money(sum(r["contrib_in"] for r in yrows)),
                  f"{len(yrows)} mo")
        c4.metric("🧾 Refund this year", money(sum(r["refund"] for r in yrows)))

        table = []
        for r in yrows:
            row = {"Month": r["label"] + ("  🎯" if r["idx"] == goal_row else "")}
            if show_in:
                row.update(money_in_columns(r))
            if show_bal:
                row.update(balance_columns(r))
            table.append(row)
        if show_in:
            # A totals line, since the per-person yearly figures are the ones worth
            # checking against contribution room. Balances are point-in-time and
            # would be meaningless summed, so they are blanked out.
            totals = {"Month": f"— {yr} total —"}
            totals.update(money_in_columns({
                k: sum(r[k] for r in yrows) for k in
                ["c_RRSP – You", "c_RRSP – Spouse", "group", "c_TFSA – You", "c_TFSA – Spouse",
                 f"c_{NONREG}", "contrib_in", "mort_extra", "refund", "cpp_ei"]}))
            if show_bal:
                totals.update({k: "" for k in balance_columns(yrows[0])})
            table.append(totals)
        st.dataframe(pd.DataFrame(table), width="stretch", hide_index=True,
                     height=42 * (len(table) + 1) + 3)
        if goal_row is not None and any(r["idx"] == goal_row for r in yrows):
            st.caption(f"🎯 Goal reached {detail['goal_reached']} — {money(goal)} "
                       + ("after tax" if cfg.goal_basis == "net" else "invested")
                       + (" with the mortgage cleared." if require_mort_paid else "."))

if show_in:
    st.caption("**of which group plan** is the slice of the spouse's RRSP funded by her payroll "
               "contribution and the employer match, rather than out of household savings — so "
               "it is already counted inside her RRSP column, not on top of it. "
               "**Into investments** is the five account columns added up."
               + (" **CPP + EI** is the household's own contributions, which stop once the "
                  "year's maximums are reached." if cfg.model_cpp_ei else ""))

# ─── Save / load settings ─────────────────────────────────────────────────────
# Rendered into the placeholder at the top of the sidebar, but run here at the end
# so the snapshot it stores includes the bracket tables parsed above.
current_cfg = gather_config(fed_brackets, ab_brackets)
store_status = st.session_state.get("_ls_status", "waiting")
stored_cfg = st.session_state.get("_saved")
unsaved = (stored_cfg is None
           or json.dumps(current_cfg, sort_keys=True) != json.dumps(stored_cfg, sort_keys=True))


def queue_write(payload):
    """Hand the browser something to store on the next run."""
    st.session_state._ls_write = payload
    st.session_state._ls_nonce = st.session_state.get("_ls_nonce", 0) + 1


with settings_io:
    status = st.empty()     # written last, so it reflects a save made just below
    if st.session_state.get("_cfg_note"):
        st.warning(st.session_state["_cfg_note"])
    if store_status == "unavailable":
        st.warning("This browser will not let the app store anything — a private window, or "
                   "site data turned off. Settings will not be remembered; use Download and "
                   "Load below instead.")

    # The panel is built only once the browser has reported back. `expanded` is
    # honoured on the run that first creates an expander and ignored afterwards,
    # so deciding it while storage is still unknown would wedge it shut for
    # exactly the first-time user who needs to see it. Remembering the decision
    # keeps it from fighting the reader later.
    if store_status != "waiting":
        st.session_state.setdefault("_panel_open", stored_cfg is None)
    with st.expander("💾 Save & load", expanded=st.session_state.get("_panel_open", False)):
        bc1, bc2 = st.columns(2)
        if bc1.button("💾 Save", key="btn_save", disabled=store_status != "ready"):
            queue_write(json.dumps(current_cfg, sort_keys=True))
            st.session_state._saved = dict(current_cfg)
            st.session_state._cfg_source = "browser storage"
            st.session_state._cfg_note = None
            st.rerun()
        if bc2.button("↩️ Defaults", key="btn_reset"):
            apply_config({}, "defaults")
        st.caption("Save keeps every setting on this sidebar, tax brackets included, in this "
                   "browser. It is restored automatically next time you open the app — on this "
                   "browser only, and nobody else who opens the app can see it. "
                   "**Defaults** only refills the form; press Save afterwards to replace what "
                   "is stored.")

        st.download_button("⬇️ Download a copy", key="btn_download",
                           data=json.dumps(current_cfg, indent=2, sort_keys=True),
                           file_name="coast_fire_config.json", mime="application/json")
        upload = st.file_uploader("⬆️ Load from a file", type="json", key="uploader")
        if upload is not None:
            # Only act on a genuinely new file: the uploader keeps handing back the
            # same one on every rerun, which would fight any edit made since.
            uid = getattr(upload, "file_id", None) or (upload.name, upload.size)
            if st.session_state.get("_upload_id") != uid:
                st.session_state._upload_id = uid
                try:
                    loaded, note = parse_config(json.loads(upload.getvalue().decode("utf-8")))
                except (ValueError, UnicodeDecodeError) as err:
                    st.error(f"Not readable JSON: {err}")
                else:
                    if loaded:
                        st.session_state._cfg_note = note
                        apply_config(loaded, upload.name)
                    else:
                        st.error(note or "No usable settings in that file.")
        st.caption("A download is a backup you keep, and works even where the browser will not "
                   "store anything. Loading one does not save it — press Save as well.")

        st.markdown("**Move to another device**")
        st.caption("Settings live in one browser, so a phone starts out empty. Copy this code, "
                   "send it to yourself, then paste it on the other device and press Load. It "
                   "always describes what is on screen right now.")
        st.code(encode_settings(current_cfg), language=None)
        pasted = st.text_area("Paste a settings code — or settings JSON", key="paste_box",
                              height=80, placeholder="Paste here…")
        if st.button("📥 Load pasted settings", key="btn_paste"):
            decoded, err = decode_settings(pasted)
            if err:
                st.error(err)
            else:
                loaded, note = parse_config(decoded)
                if loaded:
                    st.session_state._cfg_note = note
                    apply_config(loaded, "pasted settings")
                else:
                    st.error(note or "No usable settings in that code.")
        st.caption("Loading does not save — press Save on the new device too.")

        if st.button("🗑 Forget saved settings", key="btn_forget",
                     disabled=store_status != "ready" or stored_cfg is None):
            queue_write("")             # empty payload clears the store
            st.session_state._saved = None
            apply_config({}, "defaults")

    # Recomputed after the buttons above, so a save made this run shows as saved.
    stored_cfg = st.session_state.get("_saved")
    unsaved = (stored_cfg is None
               or json.dumps(current_cfg, sort_keys=True) != json.dumps(stored_cfg, sort_keys=True))
    if store_status == "waiting":
        status.caption("📂 Checking this browser for saved settings…")
    elif store_status == "unavailable":
        status.caption("📂 Storage unavailable · settings will not be remembered")
    elif stored_cfg is None:
        status.caption("📂 Nothing saved in this browser yet · press **Save** below")
    else:
        status.caption(f"📂 Loaded from this browser · "
                       f"{'**unsaved changes**' if unsaved else 'saved'}")

st.markdown(f"""
<div class="info-box" style="margin-top:16px;text-align:center">
⚠️ Each scenario runs from {month_label(cfg, 0)} until it reaches the goal, capped at
{horizon_years} years ({cfg.max_months} months, {month_label(cfg, cfg.max_months - 1)}) ·
{money(mort_weekly)}/wk mortgage at {mort_rate:.2%} · the freed-up payment is redirected after payoff ·
RRSP and TFSA room is enforced and tops up every January · the refund is computed from each
year's RRSP deductions at Alberta + federal rates and paid the following {MONTHS_ABBR[refund_month - 1]}.<br>
Monthly savings are assumed to be <b>surplus on top of</b> the scheduled mortgage payment, and
opening balances are taken as at today rather than re-dated as the start month rolls forward.<br>
Income tax only — CPP and EI are excluded, and provincial/federal credits beyond the basic
personal amount are not modelled. For planning purposes only, not tax advice.
</div>
""", unsafe_allow_html=True)

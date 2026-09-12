# Coast FIRE Scenario Planner

A Streamlit app that projects a two-income Alberta household's path to a target
portfolio plus a paid-off home, and sweeps **every** invest-vs-prepay split to
find which one gets there first.

The point of the sweep is that the answer is rarely obvious. Dollars sent at the
mortgage earn a guaranteed, tax-free return equal to the mortgage rate. Dollars
sent at an RRSP earn a market return *and* trigger a refund at your marginal
rate. Which wins depends on your bracket, your remaining contribution room, and
the prepayment privilege your lender allows — so the app runs all of them.

```bash
pip install -r requirements.txt
streamlit run app_v3.py
```

This file is also rendered inside the app, under **📖 Read me** near the top.

---

## Saving your settings

There are a lot of inputs, so you should only have to enter them once. Fill the
sidebar in, open **💾 Save & load** at the top of it, and press **Save**. Every
setting — including the edited tax brackets — is remembered, and restored
automatically the next time you open the app.

Settings are kept in **your browser**, not on the server. That matters for a
hosted deployment: a server file would be wiped on every redeploy, and a single
public app would serve one person's salary and balances to everybody else who
opened it. Browser storage is private to you and survives redeploys.

The consequences are worth knowing:

- It is **per browser and per device**. Saving on your laptop does not carry to
  your phone, and a different browser starts fresh.
- Clearing site data, or a private window, wipes it. Use **Download a copy** for
  anything you would be annoyed to lose.
- Anyone else using the same browser profile on the same machine sees it.

The status line at the top of the sidebar always says where the current settings
came from and whether you have unsaved changes.

- **Save** replaces what is stored with what is currently on screen.
- **Defaults** refills the form with the built-in values. It does *not* clear
  what is stored — press Save afterwards if that is what you want.
- **Download a copy** / **Load from a file** are the backup route, and work even
  where the browser refuses to store anything.
- **Move to another device** shows a short code describing what is on screen.
  Send it to yourself however you like — message, email, notes — then paste it on
  the other device and press Load. The box also accepts plain settings JSON, so
  a downloaded file works too if you would rather paste its contents.
- **Forget saved settings** wipes the stored copy and returns the form to
  defaults.

Loading, by any route, does not save. Press **Save** on the new device as well,
or it will be gone next time.

The code carries only the settings you have changed from the defaults, which is
why it stays short — around 40 characters for a single change, and still under
300 for a dozen. Loading one overwrites *every* setting, so anything left out of
the code lands on its default rather than on whatever that device had before.

A browser that blocks storage is handled rather than ignored: the app says so,
disables Save, and still runs normally on defaults. Anything unusable in a
stored or uploaded file falls back to the built-in default for that one setting,
and the app names the values it ignored.

---

## How a month is simulated

Every scenario walks forward one month at a time, starting the first of next
month, in this order:

1. **If it is January** — last year's tax return is filed and the refund is
   queued; new RRSP room (a % of last year's income, capped at the dollar limit,
   less any pension adjustment) and new TFSA room are added; the prepayment
   privilege resets; salary, savings and the contribution limits step up by
   their growth rates.
2. **The spouse's group plan runs off payroll** — her contribution and the
   employer match go into her RRSP, consuming room and generating a deduction.
3. **Cash is totalled** — monthly savings, plus any bonus due this month, plus
   the freed-up mortgage payment once the mortgage is gone, less her payroll
   contribution if you have chosen to fund it from savings.
4. **The refund lands** if this is the refund month, and is deployed by the rule
   you picked.
5. **Cash is split** — `invest %` to the waterfall, the rest at the mortgage.
6. **The mortgage takes its scheduled payment first** (interest, then
   principal), and only what is left of the balance can be prepaid — capped by
   the annual privilege.
7. **Cash the privilege refuses** either spills into investments or is reported
   as held back, depending on the spill setting. Once the mortgage is gone there
   is nothing to prepay, so it is always invested.
8. **Growth is applied** to every balance, then this month's contributions are
   deposited through the waterfall.
9. **The goal is checked.** A run stops the month it succeeds — so two scenarios
   in the results table are usually measured over *different* horizons. The
   **Months Run** column tells you which.

## How the refund is calculated

Not `contribution × marginal rate`. Each January the app computes combined
federal + Alberta tax twice — once on gross income, once on income less that
year's RRSP deductions — and the difference is the refund.

That matters when a contribution straddles a bracket. At $130k, a $10k
contribution is worth the full 36% ($3,600). A $30k contribution is *not* worth
$10,800: only the first $15,250 sits in the 36% band, and the rest falls to
30.5%, making it $9,989. A flat-rate estimate would overstate it by $811.

Non-refundable credits are identical on both sides of that subtraction, so they
cancel out and do not affect the refund. Both bracket tables and the basic
personal amounts are editable in the app under **🧾 Tax engine**, so they can be
rolled forward to a new tax year without touching the code.

## The settings

| Panel | What it controls |
| --- | --- |
| **👤 Household income** | Both gross salaries and an annual growth rate. Drives tax, refunds and RRSP room accrual. |
| **💵 Cash flow** | Monthly savings and its growth, plus a separate annual bonus. Monthly expenses are reference only — they size the 25× FIRE number in the caption and are not deducted from savings. |
| **🏦 Current balances** | What is invested today, per account. |
| **📥 Contribution room** | Each person's remaining RRSP and TFSA room, how much new room accrues each January, and anything already contributed this calendar year. |
| **🤝 Spouse group plan** | Employee and employer percentages, whether it is a group RRSP or a DC pension, and whether her share comes out of the savings figure or off her paycheque. |
| **📈 Returns** | One expected return, plus a tax drag applied only to the non-registered account. |
| **🏠 Mortgage** | Balance, rate, weekly payment, the annual prepayment privilege, and what happens to blocked or freed-up cash. |
| **🪜 Allocation waterfall** | The order invested dollars fill accounts. Each fills to its room before the next starts. |
| **🧾 Tax refund** | When it lands, and whether it follows the split, goes entirely to investments, entirely to the mortgage, or is spent. |
| **🎯 Goal & horizon** | The target, whether it is measured gross or after tax, whether the mortgage must be clear, the horizon, and which splits to sweep. |

### Two settings worth understanding

**Group RRSP vs DC pension.** Under a group RRSP the employer match is a taxable
benefit, both halves are deductible, and both consume her RRSP room. Under a DC
pension the employer money is not income, only her half is deductible, and a
pension adjustment reduces *next* year's room instead. Same cash into the
account, materially different tax and room consequences.

**Gross vs after-tax goal.** A dollar in an RRSP is not a dollar in a TFSA — one
is taxed on the way out. If most of your portfolio ends up in RRSPs, the gross
target flatters you. The after-tax basis discounts RRSP balances at an assumed
withdrawal rate so the two are comparable.

## Reading the output

- **🏆 Fastest path** — the winning split. It is usually a *band* rather than a
  single percentage, because many splits land in the same month; the banner says
  how many tie.
- **Results table** — one row per split. Balances and interest are measured at
  each run's own stopping point, not over a common horizon.
- **Charts** — every split overlaid. The legend is off because the sweep is too
  wide for one; hover any line to identify it. **Account Mix** shows where the
  money sits over time under the winning split.
- **Month-by-month detail** — the full schedule for any one split, tabbed by
  calendar year, with remaining contribution room at the stopping point.

## What is deliberately not modelled

Worth knowing before you lean on a number:

- **Income tax only.** CPP and EI are excluded. They cancel out of the refund,
  but the tax figures shown are not full payroll withholding.
- **Credits beyond the basic personal amount** are not modelled, and the federal
  BPA phase-out at high incomes is not applied.
- **A flat expected return**, applied every month. No sequence-of-returns risk,
  no volatility, no rebalancing.
- **A constant mortgage rate** — no renewal at a different rate, and the weekly
  payment is converted to monthly as `× 52 ÷ 12` rather than simulated weekly.
- **The prepayment privilege resets each January**, not on your mortgage
  anniversary.
- **Cash the privilege blocks, with spilling off, leaves the plan.** It is
  reported as idle, not banked and redeployed later.
- **Opening balances are taken as at today** and are not re-dated as the start
  month rolls forward.
- **Bracket defaults are the 2025 federal and Alberta schedules.** Update them in
  the app for a different year.

For planning purposes only. It is not tax advice.

---

## Other files in this repo

| File | What it is |
| --- | --- |
| `app_v3.py` | This app — the current Coast FIRE Scenario Planner. |
| `store/` | A tiny invisible component that reads and writes browser storage. |
| `app_v2.py`, `app.py` | Earlier versions, kept for reference. |
| `mortgage_payoff.py` | A standalone mortgage payoff explorer. |
| `spending_calculator` | A spending categoriser. |

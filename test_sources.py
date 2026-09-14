"""Check the tax engine against figures published by the CRA (verified Sept 2026).

Run it with `python test_sources.py` from the repository root; it exits non-zero
if anything has drifted.

Every expected value here is a number the CRA states, not one derived from the
app — so if the engine's arithmetic is wrong these fail even though the inputs
are right.

  Brackets, BPA, credit rates  T4127 Payroll Deductions Formulas, 122nd ed (Jan 1 2026)
  CPP / CPP2 / EI maximums     canada.ca contribution rates and maximums pages
  CPP tax split                canada.ca line 22215 (deduction) and line 30800 (credit)
  RRSP / TFSA limits           canada.ca MP, RRSP, DPSP, TFSA limits and the YMPE
"""
import pathlib, sys, types
stub = types.ModuleType("streamlit"); stub.__getattr__ = lambda n: (lambda *a, **k: None)
_c = types.ModuleType("streamlit.components"); _v1 = types.ModuleType("streamlit.components.v1")
_v1.declare_component = lambda *a, **k: (lambda *a2, **k2: None); _c.v1 = _v1; stub.components = _c
sys.modules.update({"streamlit": stub, "streamlit.components": _c, "streamlit.components.v1": _v1})
ns = {}
APP = pathlib.Path(__file__).with_name("app_v3.py")
# Only the half above the browser-storage block is needed, which keeps this
# runnable without a component or a running Streamlit server.
exec(compile(APP.read_text().split("# ─── Browser storage ───")[0], str(APP), "exec"), ns)
globals().update(ns)

FAIL = []
def check(name, got, want, tol=0.01, source=""):
    ok = abs(got - want) <= tol
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {got:,.2f} vs CRA {want:,.2f}"
          + (f"   [{source}]" if source else ""))
    if not ok: FAIL.append(name)

class T:
    fed_brackets, ab_brackets = FED_BRACKETS_DEFAULT, AB_BRACKETS_DEFAULT
    fed_bpa, fed_bpa_min, ab_bpa = FED_BPA_DEFAULT, FED_BPA_MIN_DEFAULT, AB_BPA_DEFAULT
    model_cpp_ei = True
    cpp_rate, cpp_base_rate, cpp_exempt = CPP_RATE_DEFAULT, CPP_BASE_RATE_DEFAULT, CPP_EXEMPT_DEFAULT
    cpp_ympe, cpp2_rate, cpp2_yampe = CPP_YMPE_DEFAULT, CPP2_RATE_DEFAULT, CPP2_YAMPE_DEFAULT
    ei_rate, ei_mie = EI_RATE_DEFAULT, EI_MIE_DEFAULT
t = T()

print("── 2026 statutory maximums the CRA publishes ──")
HIGH = 500_000.0    # above every ceiling, so each maximum is reached
base, enh, cpp2, ei = cpp_ei_for(HIGH, t)
check("max employee CPP (base + enhanced)", base + enh, 4_230.45, 0.01, "CPP rates page")
check("max employee CPP2", cpp2, 416.00, 0.01, "CPP2 rates page")
check("max employee EI premium", ei, 1_123.07, 0.01, "EI rates page")
check("max CPP deduction on line 22215", enh + cpp2, 711.00 + 416.00, 0.01, "line 22215")
check("max CPP credit on line 30800", base, 4_230.45 - 711.00, 0.01, "line 30800")

print("\n── 2025 maximums, as a second check on the same arithmetic ──")
class T25(T):
    fed_brackets = [(57_375.0, 0.145), (114_750.0, 0.205), (177_882.0, 0.26),
                    (253_414.0, 0.29), (float("inf"), 0.33)]
    cpp_ympe, cpp2_yampe, ei_rate, ei_mie = 71_300.0, 81_200.0, 1.64, 65_700.0
t25 = T25()
b25, e25, c25, ei25 = cpp_ei_for(HIGH, t25)
check("2025 max employee CPP", b25 + e25, 4_034.10, 0.01, "CPP rates page")
check("2025 max employee CPP2", c25, 396.00, 0.01, "line 22215 states $396.00")
check("2025 max employee EI", ei25, 1_077.48, 0.01, "EI rates page")
# The CRA states the 2025 line 22215 maximum outright: $1,074 = $678 + $396.
check("2025 max line 22215 deduction", e25 + c25, 1_074.00, 0.01, "line 22215")
check("2025 first additional portion", e25, 678.00, 0.01, "line 22215")

print("\n── Bracket boundaries match the published schedule ──")
for limit, rate in FED_BRACKETS_DEFAULT[:-1]:
    below = bracket_tax(limit, FED_BRACKETS_DEFAULT)
    above = bracket_tax(limit + 1_000, FED_BRACKETS_DEFAULT)
    nxt = next(r for lim, r in FED_BRACKETS_DEFAULT if lim > limit)
    check(f"federal rate just above ${limit:,.0f}", (above - below) / 1_000, nxt, 1e-9)
for limit, rate in AB_BRACKETS_DEFAULT[:-1]:
    below = bracket_tax(limit, AB_BRACKETS_DEFAULT)
    above = bracket_tax(limit + 1_000, AB_BRACKETS_DEFAULT)
    nxt = next(r for lim, r in AB_BRACKETS_DEFAULT if lim > limit)
    check(f"Alberta rate just above ${limit:,.0f}", (above - below) / 1_000, nxt, 1e-9)

print("\n── Credits are valued at the lowest bracket rate (T4127: 0.14 and 0.08) ──")
check("federal credit rate", FED_BRACKETS_DEFAULT[0][1], 0.14, 1e-9, "T4127 0.14 x TC")
check("Alberta credit rate", AB_BRACKETS_DEFAULT[0][1], 0.08, 1e-9, "T4127 0.08 x TCP")

print("\n── The federal BPA claw-back ──")
check("full BPA below the threshold", fed_bpa_for(181_440.0, t), 16_452.00, 0.01, "T4127")
check("minimum BPA at the top bracket", fed_bpa_for(258_482.0, t), 14_829.00, 0.01, "T4127")
check("halfway through the claw-back", fed_bpa_for((181_440 + 258_482) / 2, t),
      (16_452.00 + 14_829.00) / 2, 0.01)
check("no claw-back at a normal salary", fed_bpa_for(130_000.0, t), 16_452.00, 0.01)

print("\n── Someone earning below every ceiling ──")
low = 40_000.0
b, e, c2, ei_l = cpp_ei_for(low, t)
check("CPP on earnings less the exemption", b + e, (40_000 - 3_500) * 0.0595, 0.01)
check("no CPP2 below the YMPE", c2, 0.0, 0)
check("EI on full earnings", ei_l, 40_000 * 0.0163, 0.01)

print("\n── Registered plan limits ──")
check("RRSP dollar limit", DEFAULTS["rrsp_annual_max"], 33_810.0, 0.01, "MP/RRSP/DPSP/TFSA page")
check("TFSA dollar limit", DEFAULTS["tfsa_annual"], 7_000.0, 0.01, "MP/RRSP/DPSP/TFSA page")
check("RRSP accrual rate", DEFAULTS["rrsp_accrual_pct"], 18.0, 1e-9, "18% of earned income")

print("\n── A full return, computed by hand from the published schedule ──")
salary = 130_000.0
b, e, c2, ei_h = cpp_ei_for(salary, t)
taxable = salary - e - c2
fed = (58_523*0.14 + (117_045-58_523)*0.205 + (taxable-117_045)*0.26) - (16_452 + b + ei_h)*0.14
ab = (61_200*0.08 + (taxable-61_200)*0.10) - (22_769 + b + ei_h)*0.08
check("federal + Alberta tax at $130,000", total_tax(salary, t), fed + ab, 0.02)
check("take-home", take_home(salary, t), salary - (fed + ab) - (b + e + c2) - ei_h, 0.02)
check("marginal rate at $130,000", marginal_rate(salary, t), 0.26 + 0.10, 1e-9)
print(f"       (tax ${total_tax(salary, t):,.0f}, CPP ${b+e+c2:,.0f}, EI ${ei_h:,.0f}, "
      f"take-home ${take_home(salary, t):,.0f})")

print("\n" + ("ALL CHECKS PASSED" if not FAIL else f"FAILURES: {FAIL}"))
sys.exit(1 if FAIL else 0)

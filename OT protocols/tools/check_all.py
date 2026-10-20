"""End-to-end checks: simulates the protocol for every setting and the expected-error cases,
and runs a two-round BO loop through bo_bridge.py with fake plate-reader data.

    python tools/check_all.py [path/to/opentrons_simulate]

Needs the opentrons package (8.x - the last series whose simulator runs OT-2 protocols).
Scratch files go to a temporary folder.
"""
import csv, os, random, re, subprocess, sys, tempfile
P = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
T = tempfile.mkdtemp(prefix="sdl_check_")
SIM = sys.argv[1] if len(sys.argv) > 1 else "opentrons_simulate"
B = os.path.join(P, "bo_bridge.py")
PROTO = open(os.path.join(P, "sdl_solubility_ot2.py")).read()
results = []

def sh(*args):
    r = subprocess.run([sys.executable, "-I", *args], capture_output=True, text=True, cwd=T)
    return r.returncode, r.stdout + r.stderr

def setdef(src, var, val):
    i = src.index(f'variable_name="{var}"'); j = src.index("default=", i); k = src.index(",", j)
    return src[:j] + f"default={val}" + src[k:]

def proto_with(csv_path=None, rows=None, **defaults):
    s = PROTO
    if csv_path or rows:
        rows = rows or [r for r in csv.reader(open(csv_path))]
        s = re.sub(r"TEST_CSV = \[.*?\n\]\n", "TEST_CSV = " + repr(rows) + "\n", s, count=1, flags=re.S)
    for k, v in defaults.items():
        s = setdef(s, k, v)
    return s

def sim(name, src, expect_ok=True, expect_text=None):
    path = os.path.join(T, name + ".py")
    open(path, "w").write(src)
    r = subprocess.run([SIM, "-L", os.path.join(P, "labware"), path], capture_output=True, text=True)
    out = r.stdout + r.stderr
    ok = (r.returncode == 0) == expect_ok and (expect_text is None or expect_text in out)
    stats = f"asp={len(re.findall(r'^Aspirating', out, re.M))} disp={len(re.findall(r'^Dispensing', out, re.M))} tips={out.count('Picking up')} moves={len(re.findall(r'^Moving', out, re.M))}"
    last = out.strip().splitlines()[-1][:90] if out.strip() else ""
    results.append(("PASS" if ok else "FAIL", "sim " + name, stats if expect_ok else last))

def check(name, cond, info=""):
    results.append(("PASS" if cond else "FAIL", name, info))

def fake_reader(plate_map, path, seed):
    random.seed(seed)
    pm = list(csv.DictReader(open(plate_map)))
    vals = {m["well"]: (1.0 if m["role"] == "control" else random.uniform(0.2, 1.1)) + random.gauss(0, 0.02) for m in pm}
    with open(path, "w") as f:
        f.write(",1,2,3,4,5,6,7,8,9,10,11,12\n")
        for r in "ABCDEFGH":
            f.write(r + "," + ",".join(f"{vals.get(f'{r}{c}', 0.05):.4f}" for c in range(1, 13)) + "\n")

# --- protocol settings -------------------------------------------------------------
sim("default_testdata", proto_with())
ex = os.path.join(P, "examples", "ot_input_round1.csv")
sim("round1_3plates", proto_with(ex))
sim("round1_2plates", proto_with(ex, n_plates=2))
sim("round1_1plate", proto_with(ex, n_plates=1))
sim("resume_shake_plate2", proto_with(ex, start_step='"2"'))
sim("resume_shake_plate3", proto_with(ex, start_step='"3"'))
sim("heated_45C", proto_with(ex, temperature_c=45))
sim("ERR_temp_30C", proto_with(ex, temperature_c=30), False, "below 37")
sim("ERR_resume_plate3_of_2", proto_with(ex, n_plates=2, start_step='"3"'), False, "only 2 plate")
rows = [r for r in csv.reader(open(ex))]
over = [rows[0]] + [r[:] for r in rows[1:]]; over[1][3] = "350"
sim("ERR_overvolume", proto_with(rows=over), False, "exceeds")
bad = [rows[0][:3] + ["vol_Toluene_ul"], ["A1", "S1", "x", "100"]]
sim("ERR_unknown_solvent", proto_with(rows=bad), False, "no reservoir trough")
flood = [rows[0][:3] + ["vol_2MeTHF_ul"]] + [[f"{r}{c}", "S1", "x", "300"] for r in "ABCDEFGH" for c in range(1, 13)]
sim("ERR_trough_overflow", proto_with(rows=flood), False, "only supply")

# --- BO loop: 2 rounds ---------------------------------------------------------------
rc, out = sh(B, "grid", "--round", "1", "-o", "s1.csv"); check("grid round 1", rc == 0, out.strip().splitlines()[-1])
rc, out = sh(B, "layout", "--round", "1", "--suggestions", "s1.csv", "--outdir", "r1"); check("layout round 1", rc == 0)
check("examples match fresh layout", open(os.path.join(T, "r1", "ot_input_round1.csv")).read() == open(ex).read())
sim("loop_round1", proto_with(os.path.join(T, "r1", "ot_input_round1.csv")))
for p in (1, 2, 3):
    fake_reader(os.path.join(T, "r1", "plate_map_round1.csv"), os.path.join(T, "r1", f"plate{p}.csv"), p)
rc, out = sh(B, "merge", "--plate-map", "r1/plate_map_round1.csv", "--reader", "r1/plate1.csv", "r1/plate2.csv", "r1/plate3.csv", "--dataset", "ds.csv")
check("merge round 1", rc == 0, out.strip().splitlines()[1] if rc == 0 else out[-200:])
# round 2: BO output mixing per-solute and shared rows
with open(os.path.join(T, "s2.csv"), "w") as f:
    f.write("solute,frac_2MeTHF,frac_EtOAc,frac_DMC,frac_CPME,frac_MeCN,frac_iPrOAc\n")
    random.seed(9)
    for s in ("S1", "S2", "S3", "S4"):
        for _ in range(18):
            k = random.choice([1, 2, 3]); idx = random.sample(range(6), k); w = [random.random() for _ in idx]
            fr = [0.0] * 6
            for i, x in zip(idx, w): fr[i] = x / sum(w)
            f.write(s + "," + ",".join(f"{x:.3f}" for x in fr) + "\n")
    for _ in range(5):
        f.write(",0.5,0,0.5,0,0,0\n" if _ == 0 else ",0.34,0.33,0,0.33,0,0\n" if _ == 1 else f",{0.2*_:.1f},0,0,{1-0.2*_:.1f},0,0\n")
rc, out = sh(B, "layout", "--round", "2", "--suggestions", "s2.csv", "--outdir", "r2"); check("layout round 2 (per-solute + shared)", rc == 0, out[-160:] if rc else "")
sim("loop_round2", proto_with(os.path.join(T, "r2", "ot_input_round2.csv")))
for p in (1, 2, 3):
    fake_reader(os.path.join(T, "r2", "plate_map_round2.csv"), os.path.join(T, "r2", f"plate{p}.csv"), 10 + p)
args = ["merge", "--plate-map", "r2/plate_map_round2.csv", "--reader", "r2/plate1.csv", "r2/plate2.csv", "r2/plate3.csv", "--dataset", "ds.csv"]
rc, out = sh(B, *args); check("merge round 2", rc == 0)
n1 = len(open(os.path.join(T, "ds.csv")).readlines())
rc, out = sh(B, *args); n2 = len(open(os.path.join(T, "ds.csv")).readlines())
check("re-merge is idempotent", rc == 0 and n1 == n2, f"{n1 - 1} rows")
ds = list(csv.DictReader(open(os.path.join(T, "ds.csv"))))
check("dataset has both rounds", {r["round"] for r in ds} == {"1", "2"}, f"{len(ds)} rows")
sh_rows = list(csv.DictReader(open(os.path.join(T, "ds_shared.csv"))))
check("shared dataset: 24 (r1) + 6 (r2 incl. DMF)", len(sh_rows) == 30, f"{len(sh_rows)} rows")
check("fractions sum to 1 in dataset", all(abs(sum(float(r[f"frac_{s}"]) for s in ["DMF","2MeTHF","EtOAc","DMC","CPME","MeCN","iPrOAc"]) - 1) < 1e-3 for r in ds))
check("DMF reference rel = 1", all(abs(float(r["rel_mean"]) - 1) < 1e-9 for r in ds if r["is_reference"] == "1"))
rc, _ = sh(B, "plate-svg", "--plate-map", "r2/plate_map_round2.csv", "-o", "r2.svg"); check("plate-svg", rc == 0)

# --- layout generality --------------------------------------------------------------
for name, extra in [("replicates2", ["--replicates", "2"]), ("3solutes_2ctrl", ["--solutes", "A,B,C", "--controls-per-solute", "2"])]:
    rc, _ = sh(B, "grid", "-o", f"g_{name}.csv", *extra)
    rc2, _ = sh(B, "layout", "--round", "7", "--suggestions", f"g_{name}.csv", "--outdir", name, *extra)
    check(f"layout {name}", rc == 0 and rc2 == 0)
    sim(f"layout_{name}", proto_with(os.path.join(T, name, "ot_input_round7.csv")))

# --- Flex analog replays the OT-2 liquid handling step for step -------------------------
flex_path = os.path.join(P, "..", "OTFlex analog", "sdl_solubility_flex_analog.py")
if os.path.exists(flex_path):
    def handling_steps(src, name):
        path = os.path.join(T, name + ".py")
        open(path, "w").write(re.sub(r"TEST_CSV = \[.*?\n\]\n", "TEST_CSV = " + repr(rows) + "\n", src, count=1, flags=re.S))
        r = subprocess.run([SIM, "-L", os.path.join(P, "labware"), path], capture_output=True, text=True)
        steps = []
        for ln in (r.stdout + r.stderr).splitlines():
            ln = ln.strip()
            if re.match(r"(Aspirating|Dispensing|Air gap|Mixing|Blowing out|Delaying for 0 minutes and 1)", ln):
                ln = re.sub(r" on slot \w+| on (Heater-Shaker|opentrons).*$", "", ln)
                steps.append(re.sub(r"Opentrons (OT-2|Flex) 96 Tip Rack \d+ µL", "tiprack", ln))
        return r.returncode, steps
    rc1, a_steps = handling_steps(PROTO, "cmp_ot2")
    rc2, b_steps = handling_steps(open(flex_path).read(), "cmp_flex_analog")
    check("Flex analog = OT-2 liquid handling", rc1 == 0 and rc2 == 0 and a_steps == b_steps and len(a_steps) > 0,
          f"{len(a_steps)} vs {len(b_steps)} steps")

w = max(len(n) for _, n, _ in results)
for st, n, info in results:
    print(f"{st}  {n:<{w}}  {info}")
n_pass = sum(r[0] == "PASS" for r in results)
print(f"\n{n_pass}/{len(results)} passed (scratch files in {T})")
sys.exit(0 if n_pass == len(results) else 1)

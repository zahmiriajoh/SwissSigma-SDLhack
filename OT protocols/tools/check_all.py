"""End-to-end checks: simulates the protocol for every setting and the expected-error cases, runs a two-round BO
loop through bo_bridge.py with fake plate-reader data, and drives the production campaign (production/run_bo.sh,
rounds 0-2 with real SDL_BO suggestions) checking that every round's robot CSV runs, that the robot dispenses exactly
the CSV volumes into every well of every plate, and that every well gets a well-formed, unique sample id.

    python tools/check_all.py [path/to/opentrons_simulate]

Needs the opentrons package (8.x - the last series whose simulator runs OT-2 protocols).
Scratch files go to a temporary folder.
"""
import csv, os, random, re, subprocess, sys, tempfile
P = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(P))
from production.config import GREEN_SOLVENTS, is_allowed  # noqa: E402
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
    return out

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
ex = os.path.join(P, "examples", "ot_input_round0.csv")
sim("round0_3plates", proto_with(ex))
sim("round0_2plates", proto_with(ex, n_plates=2))
sim("round0_1plate", proto_with(ex, n_plates=1))
sim("resume_shake_plate1", proto_with(ex, start_step='"1"'))
sim("resume_shake_plate2", proto_with(ex, start_step='"2"'))
sim("heated_45C", proto_with(ex, temperature_c=45))
sim("resume_shake_plate0", proto_with(ex, start_step='"0"'))
sim("heated_37C_min", proto_with(ex, temperature_c=37))
sim("heated_60C_max", proto_with(ex, temperature_c=60))
sim("no_shake_0min", proto_with(ex, shake_minutes=0))
sim("no_blank_plate", proto_with(ex, blank_plate=False))
sim("no_backup_reservoir", proto_with(ex, backup_reservoir=False))
sim("minimal_1plate_no_extras", proto_with(ex, n_plates=1, blank_plate=False, backup_reservoir=False))
sim("ERR_temp_30C", proto_with(ex, temperature_c=30), False, "below 37")
sim("ERR_resume_plate2_of_2", proto_with(ex, n_plates=2, start_step='"2"'), False, "only 2 plate")
rows = [r for r in csv.reader(open(ex))]
over = [rows[0]] + [r[:] for r in rows[1:]]; over[1][3] = "350"
sim("ERR_overvolume", proto_with(rows=over), False, "exceeds")
bad = [rows[0][:3] + ["vol_Toluene_ul"], ["A1", "Glutarimide", "x", "100"]]
sim("ERR_unknown_solvent", proto_with(rows=bad), False, "no reservoir trough")
hdr = rows[0]
sim("ERR_bad_header", proto_with(rows=[["Well"] + hdr[1:]] + rows[1:]), False, "Header must start")
sim("ERR_unknown_well", proto_with(rows=[hdr, ["Z9"] + rows[1][1:]]), False, "unknown well")
sim("ERR_duplicate_well", proto_with(rows=[hdr, rows[1], rows[1]]), False, "listed twice")
sim("ERR_below_min_volume", proto_with(rows=[hdr, rows[1][:3] + ["0.5"] + ["299.5"] + rows[1][5:]]), False, "below pipette minimum")
sim("ERR_negative_volume", proto_with(rows=[hdr, rows[1][:3] + ["-5"] + rows[1][4:]]), False, "negative")
sim("ERR_empty_well", proto_with(rows=[hdr, rows[1][:3] + ["0"] * (len(hdr) - 3)]), False, "receives no liquid")
sim("blank_csv_lines_ignored", proto_with(rows=rows + [[""] * len(hdr), []]))
flood = [rows[0][:3] + ["vol_acetone_ul"]] + [[f"{r}{c}", "Glutarimide", "x", "300"] for r in "ABCDEFGH" for c in range(1, 13)]
sim("ERR_trough_overflow", proto_with(rows=flood), False, "only supply")  # 86 mL > both reservoirs
# one plate of pure acetone needs 28.8 mL: more than one trough (24 mL usable), so the slot-4 backup takes over
sim("backup_reservoir_takes_over", proto_with(rows=flood, n_plates=1, blank_plate=False), True, "Backup solvent reservoir")
sim("ERR_no_backup_reservoir", proto_with(rows=flood, n_plates=1, blank_plate=False, backup_reservoir=False), False, "only supply")

# --- BO loop: 2 rounds ---------------------------------------------------------------
rc, out = sh(B, "grid", "--round", "0", "-o", "s0.csv"); check("grid round 0", rc == 0, out.strip().splitlines()[-1])
rc, out = sh(B, "layout", "--round", "0", "--suggestions", "s0.csv", "--outdir", "r0"); check("layout round 0", rc == 0)
check("examples match fresh layout", open(os.path.join(T, "r0", "ot_input_round0.csv")).read() == open(ex).read())
sim("loop_round0", proto_with(os.path.join(T, "r0", "ot_input_round0.csv")))
for p in (0, 1, 2):
    fake_reader(os.path.join(T, "r0", "plate_map_round0.csv"), os.path.join(T, "r0", f"plate{p}.csv"), p)
rc, out = sh(B, "merge", "--plate-map", "r0/plate_map_round0.csv", "--reader", "r0/plate0.csv", "r0/plate1.csv", "r0/plate2.csv", "--dataset", "ds.csv")
check("merge round 0", rc == 0, out.strip().splitlines()[1] if rc == 0 else out[-200:])
# round 1: BO output mixing per-solute and shared rows
with open(os.path.join(T, "s1.csv"), "w") as f:
    f.write("solute,frac_acetone,frac_EtOH,frac_iPrOH,frac_water,frac_iPrOAc,frac_tBuOAc\n")
    random.seed(10)  # a seed whose random design fits the troughs
    for s in ("Glutarimide", "Boc-hydroxyproline", "Phthalimide", "Succinimide"):
        for _ in range(18):
            while True:
                k = random.choice([1, 2, 3]); idx = random.sample(range(6), k)
                if is_allowed([GREEN_SOLVENTS[i] for i in idx]): break
            w = [random.random() for _ in idx]
            fr = [0.0] * 6
            for i, x in zip(idx, w): fr[i] = x / sum(w)
            f.write(s + "," + ",".join(f"{x:.3f}" for x in fr) + "\n")
    for _ in range(5):
        f.write(",0.5,0,0.5,0,0,0\n" if _ == 0 else ",0.34,0.33,0,0.33,0,0\n" if _ == 1 else f",{0.2*_:.1f},0,0,{1-0.2*_:.1f},0,0\n")
rc, out = sh(B, "layout", "--round", "1", "--suggestions", "s1.csv", "--outdir", "r1"); check("layout round 1 (per-solute + shared)", rc == 0, out[-160:] if rc else "")
sim("loop_round1", proto_with(os.path.join(T, "r1", "ot_input_round1.csv")))
for p in (0, 1, 2):
    fake_reader(os.path.join(T, "r1", "plate_map_round1.csv"), os.path.join(T, "r1", f"plate{p}.csv"), 10 + p)
args = ["merge", "--plate-map", "r1/plate_map_round1.csv", "--reader", "r1/plate0.csv", "r1/plate1.csv", "r1/plate2.csv", "--dataset", "ds.csv"]
rc, out = sh(B, *args); check("merge round 1", rc == 0)
n1 = len(open(os.path.join(T, "ds.csv")).readlines())
rc, out = sh(B, *args); n2 = len(open(os.path.join(T, "ds.csv")).readlines())
check("re-merge is idempotent", rc == 0 and n1 == n2, f"{n1 - 1} rows")
ds = list(csv.DictReader(open(os.path.join(T, "ds.csv"))))
check("dataset has both rounds", {r["round"] for r in ds} == {"0", "1"}, f"{len(ds)} rows")
sh_rows = list(csv.DictReader(open(os.path.join(T, "ds_shared.csv"))))
check("shared dataset: 24 (r0) + 6 (r1 incl. DMF)", len(sh_rows) == 30, f"{len(sh_rows)} rows")
check("fractions sum to 1 in dataset", all(abs(sum(float(r[f"frac_{s}"]) for s in ["DMF","acetone","EtOH","iPrOH","water","iPrOAc","tBuOAc"]) - 1) < 1e-3 for r in ds))
check("DMF reference rel = 1", all(abs(float(r["rel_mean"]) - 1) < 1e-9 for r in ds if r["is_reference"] == "1"))
rc, _ = sh(B, "plate-svg", "--plate-map", "r1/plate_map_round1.csv", "-o", "r1.svg"); check("plate-svg", rc == 0)

# --- layout generality --------------------------------------------------------------
for name, extra in [("replicates2", ["--replicates", "2"]), ("3solutes_2ctrl", ["--solutes", "A,B,C", "--controls-per-solute", "2"])]:
    rc, _ = sh(B, "grid", "-o", f"g_{name}.csv", *extra)
    rc2, _ = sh(B, "layout", "--round", "7", "--suggestions", f"g_{name}.csv", "--outdir", name, *extra)
    check(f"layout {name}", rc == 0 and rc2 == 0)
    sim(f"layout_{name}", proto_with(os.path.join(T, name, "ot_input_round7.csv")))

# --- production campaign: run_bo.sh rounds 0-2 with real SDL_BO suggestions --------------------------------------
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
REPO = os.path.dirname(P)
sys.path.insert(0, os.path.join(REPO, "analysis", "examples"))
import fake_plate_reader as fpr  # noqa: E402
from production.config import FIRST_PLATE, N_PLATES, SOLUTES, SOLVENT_TROUGHS, TOTAL_UL, sample_id  # noqa: E402
CSVS = os.path.join(T, "campaign")
AIR_GAP = {10.0: 2, 92.0: 10}  # dispense flow rate -> that pipette's air gap (P20, P300 in PIPETTES)
SAMPLE_ID = re.compile(r"round(\d+)_plate(\d+)_solute(\d+)_cond(\d+)")

def run_bo():
    env = {**os.environ, "PATH": f"{os.path.dirname(sys.executable)}{os.pathsep}{os.environ['PATH']}"}
    r = subprocess.run(["bash", os.path.join(REPO, "production", "run_bo.sh"), CSVS, "--no-figures"],
                       capture_output=True, text=True, cwd=REPO, env=env)
    return r.returncode, r.stdout + r.stderr

def dispensed(log):
    """{(labware, well, solvent): uL} actually dispensed, from the simulator log (air gaps removed)."""
    out, solvent = {}, None
    for ln in log.splitlines():
        if m := re.match(r"(\w+) with p\d+_single_gen2: \d+ dispenses", ln):
            solvent = m.group(1)
        elif m := re.match(r"Dispensing ([\d.]+) uL into (\w+) of (Readout plate \d|Solvent blank plate) on slot \w+ at ([\d.]+) uL/sec", ln):
            key = (m.group(3), m.group(2), solvent)
            out[key] = out.get(key, 0) + float(m.group(1)) - AIR_GAP[float(m.group(4))]
    return out

def expected(ot_csv, n_plates, blank=True):
    rows = list(csv.DictReader(open(ot_csv)))
    out = {}
    for r in rows:
        for col, v in r.items():
            if col.startswith("vol_") and float(v or 0) > 0:
                for p in range(n_plates):
                    out[(f"Readout plate {p}", r["well"], col[4:-3])] = float(v)
    if blank:
        out.update({("Solvent blank plate", SOLVENT_TROUGHS[sv][0], sv): float(TOTAL_UL) for sv in SOLVENT_TROUGHS})
    return out

def same_volumes(got, want):
    keys = set(got) | set(want)
    bad = [k for k in keys if abs(got.get(k, 0) - want.get(k, 0)) > 1e-6]
    return not bad, f"{len(want)} (plate, well, solvent) volumes" if not bad else f"{len(bad)} mismatches, e.g. {sorted(bad)[:2]}"

rc, out = run_bo()
check("campaign: run_bo.sh writes the round-0 seed design", rc == 0, out[-150:] if rc else "")
ids = []
for r in range(3):
    ratios = os.path.join(CSVS, "ratios")
    ot_csv, pm_path = os.path.join(ratios, f"ot_input_round{r}.csv"), os.path.join(ratios, f"plate_map_round{r}.csv")
    pm = pd.read_csv(pm_path)
    # the robot CSV runs and every plate well gets exactly its CSV volumes (plus the blank plate)
    log = sim(f"campaign_round{r}_3plates", proto_with(ot_csv))
    check(f"campaign round {r}: robot dispenses exactly the CSV volumes", *same_volumes(dispensed(log), expected(ot_csv, 3)))
    log = sim(f"campaign_round{r}_1plate_no_blank_no_backup", proto_with(ot_csv, n_plates=1, blank_plate=False, backup_reservoir=False))
    check(f"campaign round {r}: 1 plate, no blank: volumes", *same_volumes(dispensed(log), expected(ot_csv, 1, blank=False)))
    ot = pd.read_csv(ot_csv).set_index("well")
    vols = [c for c in ot.columns if c.startswith("vol_")]
    check(f"campaign round {r}: robot CSV = plate map volumes, {TOTAL_UL} uL per well",
          (pm.set_index("well")[vols].loc[ot.index].to_numpy() == ot[vols].to_numpy()).all() and (ot[vols].sum(axis=1) == TOTAL_UL).all())
    # plate map carries the sample-id parts: cond = position in the block, cond0 = the DMF control
    ctrl = pm[pm["cond"] == 0]
    check(f"campaign round {r}: plate map cond0 = DMF control, one per solute",
          set(ctrl["role"]) == {"control"} and sorted(ctrl["solute"]) == sorted(SOLUTES) and (pm.loc[pm["cond"] > 0, "role"] == "sample").all())
    # the lab's reader exports for round r, then merge round r and design round r + 1
    rng = np.random.default_rng(r + 1)
    for p in range(FIRST_PLATE, FIRST_PLATE + N_PLATES):
        fpr.spectra_export(pm.set_index("well"), rng).to_csv(os.path.join(CSVS, "uvvis", f"reader_round{r}_plate{p}.csv"), index=False)
    rc, out = run_bo()
    check(f"campaign: merge round {r} and lay out round {r + 1}", rc == 0 and os.path.exists(os.path.join(ratios, f"plate_map_round{r + 1}.csv")),
          out[-150:] if rc else "")
    wells = pd.read_csv(os.path.join(CSVS, f"results_round{r}_wells.csv"))
    parts = wells["sample_id"].str.fullmatch(SAMPLE_ID.pattern)
    solute_no = {s: i for i, s in enumerate(SOLUTES)}
    want = [sample_id(r, p, solute_no[s], c) for p, s, c in zip(wells["plate"], wells["solute"], pm.set_index("well").loc[wells["well"], "cond"])]
    check(f"campaign round {r}: every well on every plate has its sample id",
          parts.all() and len(wells) == 96 * N_PLATES and list(wells["sample_id"]) == want,
          f"e.g. {wells.loc[(wells.plate == FIRST_PLATE + 1) & (wells.well == 'A1'), 'sample_id'].iloc[0]}")
    ids += list(wells["sample_id"])
dataset = pd.read_csv(os.path.join(CSVS, "bo_dataset.csv"))
check("campaign: sample ids unique over rounds 0-2", len(ids) == len(set(ids)) == 3 * 96 * N_PLATES, f"{len(ids)} ids")
check("campaign: bo_dataset has 96 rows per round for rounds 0-2", dataset.groupby("round").size().to_dict() == {0: 96, 1: 96, 2: 96})

w = max(len(n) for _, n, _ in results)
for st, n, info in results:
    print(f"{st}  {n:<{w}}  {info}")
n_pass = sum(r[0] == "PASS" for r in results)
print(f"\n{n_pass}/{len(results)} passed (scratch files in {T})")
sys.exit(0 if n_pass == len(results) else 1)

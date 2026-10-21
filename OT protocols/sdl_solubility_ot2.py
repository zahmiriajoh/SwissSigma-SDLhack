from opentrons import protocol_api
from opentrons.protocol_api import RuntimeParameterRequiredError

requirements = {"robotType": "OT-2", "apiLevel": "2.27"}

metadata = {
    "protocolName": "SDL Solubility: green-solvent mixtures (one BO round, OT-2)",
    "author": "SwissSigma",
    "description": (
        "Reads one round of well-by-well solvent mixtures (CSV from bo_bridge.py layout) and "
        "builds them directly in up to 3 identical UV-Vis readout plates (solids pre-loaded). "
        "All plates are filled in one pass, sealed by hand, then shaken one at a time on the "
        "heater-shaker."
    ),
}

# The CSV is well-level: every row is one well with its own mixture, so the plate layout
# (which solute sits where, how many DMF controls, how many replicate wells, how many
# conditions per solute) is decided entirely by bo_bridge.py - this script never assumes it.
# Every listed well gets the same mixture in each of the n_plates identical plates.
#
# Single-channel pipettes: P20 for volumes below the P300 minimum, P300 for the rest.
# One tip per solvent and pipette: it aspirates enough for several wells, dispensing the
# same well on every plate back to back, each from above the well with an air gap between
# shots. Tips only ever touch their own solvent, so they are reused across wells and plates.
#
# Deck (OT-2, trash 12):
#   10 heater-shaker + universal flat adapter   11 -               12 trash
#    7 -                                          8 P300 tips        9 P20 tips
#    4 backup solvent reservoir                   5 solvent reservoir 6 solvent blank plate
#    1 readout plate 0                            2 readout plate 1  3 readout plate 2
# Slots 7 and 11 (next to the heater-shaker) are kept free of tall labware.


# ---------------------------------------------------------------------------
# Deck / hardware configuration - keep solvent names in sync with bo_bridge.py
# ---------------------------------------------------------------------------

# Liquid name -> trough(s) on the 8-trough reservoir (wells A1..H1). Names must match the
# CSV columns "vol_<name>_ul". List more than one trough to give a liquid more volume.
# Hand-kept mirror of ../production/config.toml (the robot cannot import the repo);
# tests/test_interfaces.py checks that the two agree.
SOLVENT_TROUGHS = {
    "DMF": ["A1"],
    "acetone": ["B1"],
    "EtOH": ["C1"],
    "iPrOH": ["D1"],
    "water": ["E1"],
    "iPrOAc": ["F1"],
    "tBuOAc": ["G1"],
    "diluent": ["H1"],  # only used if the CSV has a vol_diluent_ul column
}
TROUGH_FILL_UL = 25000  # volume loaded into every used trough before the run (config: trough_fill_ul)
TROUGH_DEAD_UL = 1000   # single channel: ~1 mm of liquid left in the trough (config: trough_dead_ul)

# Custom labware (labware/ folder, import into the Opentrons app)
READOUT_PLATE = "sarstedt_96_wellplate_390ul_flat"   # file ..._flatbottom.json
# Sarstedt 83.3924 is polystyrene, which acetone, the esters and DMF attack (clouding raises
# absorbance). Known limitation - see README. Swap for a quartz/glass-bottom plate if available.
SOLVENT_RESERVOIR = "axygen_8_reservoir_30000ul"
HS_ADAPTER = "opentrons_universal_flat_adapter"      # custom JSONs declare this stacking offset

PLATE_SLOTS = ["1", "2", "3"]   # up to 3 identical plates
BLANK_SLOT = "6"                # solvent blank plate: well X1 = pure solvent from trough X1, no solids
BLANK_UL = 300                  # per blank well; matches total_ul in production/config.toml
BLANK_SOLVENTS = [n for n in SOLVENT_TROUGHS if n != "diluent"]
RESERVOIR_SLOT = "5"
BACKUP_RESERVOIR_SLOT = "4"  # same trough layout as slot 5; a solvent switches here once its slot-5 trough is used up
HS_SLOT = "10"

# Pipettes, smallest first. Each dispense uses the first pipette whose range covers it
# (volume >= next pipette's minimum moves up); a dispense too big for one shot is split.
#   (pipette, mount, tip rack, slot, air_gap_ul, disposal_ul, (aspirate, dispense) uL/s)
PIPETTES = [
    ("p20_single_gen2", "right", "opentrons_96_tiprack_20ul", "9", 2, 2, (5, 10)),
    ("p300_single_gen2", "left", "opentrons_96_tiprack_300ul", "8", 10, 10, (46, 92)),
]

WELL_MAX_UL = 320  # readout plate well (390 uL) minus headspace for shaking

# ---------------------------------------------------------------------------
# CSV import
# ---------------------------------------------------------------------------

FIXED_HEADER = ["well", "solute", "condition_id"]

# Used only when no CSV is selected (e.g. local simulation).
# Note: real CSV data arrives as strings, so the test data does too.
TEST_CSV = [
    FIXED_HEADER + ["vol_DMF_ul", "vol_acetone_ul", "vol_EtOH_ul", "vol_water_ul"],
    ["A1", "Glutarimide", "R0_DMFref", "300", "0", "0", "0"],
    ["A2", "Glutarimide", "R0_C00", "0", "300", "0", "0"],
    ["A3", "Glutarimide", "R0_C01", "0", "150", "150", "0"],
    ["A4", "Glutarimide", "R0_C02", "0", "100", "100", "100"],
    ["C1", "Boc-hydroxyproline", "R0_DMFref", "300", "0", "0", "0"],
    ["C2", "Boc-hydroxyproline", "R0_C00", "0", "300", "0", "0"],
    ["C3", "Boc-hydroxyproline", "R0_C01", "0", "150", "150", "0"],
    ["C4", "Boc-hydroxyproline", "R0_C03", "0", "0", "12", "288"],
]


def add_parameters(parameters: protocol_api.ParameterContext):
    parameters.add_csv_file(
        variable_name="input_csv",
        display_name="Round conditions (CSV)",
        description="ot_input_roundN.csv from bo_bridge.py: well, solute, condition_id, vol_<solvent>_ul...",
    )
    parameters.add_int(
        variable_name="n_plates",
        display_name="Identical plates",
        description="Replicate readout plates, all filled from the same CSV (slots 1, 2, 3)",
        default=3,
        minimum=1,
        maximum=3,
    )
    parameters.add_bool(
        variable_name="backup_reservoir",
        display_name="Backup reservoir (slot 4)",
        description="Second 8-trough reservoir, same layout as slot 5, used when a slot-5 trough runs low",
        default=True,
    )
    parameters.add_bool(
        variable_name="blank_plate",
        display_name="Solvent blank plate (slot 6)",
        description="Fill A1-G1 of a plate in slot 6 with pure solvent (one well per trough)",
        default=True,
    )
    parameters.add_str(
        variable_name="start_step",
        display_name="Start at",
        description="Resume an interrupted run (plates already filled and sealed)",
        choices=[
            {"display_name": "Fill all plates", "value": "fill"},
            {"display_name": "Shake plate 0", "value": "0"},
            {"display_name": "Shake plate 1", "value": "1"},
            {"display_name": "Shake plate 2", "value": "2"},
        ],
        default="fill",
    )
    parameters.add_int(
        variable_name="shake_rpm",
        display_name="Shake speed",
        default=800,
        minimum=200,
        maximum=1500,
        unit="rpm",
    )
    parameters.add_int(
        variable_name="shake_minutes",
        display_name="Shake time per plate",
        default=20,
        minimum=0,
        maximum=480,
        unit="min",
    )
    parameters.add_int(
        variable_name="temperature_c",
        display_name="Heater-shaker temperature",
        description="0 = no heating (ambient). Otherwise 37-60 C.",
        default=0,
        minimum=0,
        maximum=60,
        unit="C",
    )


def load_rows(protocol):
    try:
        rows = protocol.params.input_csv.parse_as_csv()
    except RuntimeParameterRequiredError:
        protocol.comment("No CSV selected - using built-in test data")
        rows = TEST_CSV
    # drop blank trailing lines that spreadsheet programs like to add
    return [r for r in rows if any(c.strip() for c in r)]


def validate(rows, min_volume, plate, n_plates, extra_ul=None, n_reservoirs=1):
    """Returns (liquid_names, [(well, solute, condition_id, {liquid: vol_ul})]).
    extra_ul: per-liquid volume needed on top of the plates (e.g. blank wells);
    n_reservoirs: how many reservoirs carry each liquid's troughs (2 with the backup)."""
    header = [c.strip() for c in rows[0]]
    if header[:3] != FIXED_HEADER:
        raise ValueError(f"Header must start with {FIXED_HEADER}, got {header}")
    solvents = []
    for col_name in header[3:]:
        if not (col_name.startswith("vol_") and col_name.endswith("_ul")):
            raise ValueError(f"Unexpected column '{col_name}', expected vol_<solvent>_ul")
        name = col_name[len("vol_"):-len("_ul")]
        if name not in SOLVENT_TROUGHS:
            raise ValueError(
                f"Solvent '{name}' has no reservoir trough; known: {list(SOLVENT_TROUGHS)}"
            )
        solvents.append(name)

    errors, parsed, seen = [], [], set()
    for line_no, row in enumerate(rows[1:], start=2):
        row = [c.strip() for c in row]
        if len(row) != len(header):
            errors.append(f"line {line_no}: expected {len(header)} columns, got {len(row)}")
            continue
        well, solute, cond_id = row[0].upper(), row[1], row[2]
        if well not in plate.wells_by_name():
            errors.append(f"line {line_no}: unknown well '{row[0]}'")
        if well in seen:
            errors.append(f"line {line_no}: well {well} listed twice")
        seen.add(well)

        vols = {}
        for name, vol_str in zip(solvents, row[3:]):
            try:
                vol = float(vol_str) if vol_str else 0.0
            except ValueError:
                errors.append(f"line {line_no}: {name} volume '{vol_str}' is not a number")
                continue
            if vol < 0:
                errors.append(f"line {line_no}: {name} volume {vol} is negative")
            elif 0 < vol < min_volume:
                errors.append(
                    f"line {line_no}: {name} {vol} uL below pipette minimum {min_volume} uL"
                )
            vols[name] = vol
        total = sum(vols.values())
        if total <= 0:
            errors.append(f"line {line_no}: well {well} receives no liquid")
        elif total > WELL_MAX_UL:
            errors.append(f"line {line_no}: {total} uL exceeds {WELL_MAX_UL} uL per well")
        parsed.append((well, solute, cond_id, vols))

    usable = TROUGH_FILL_UL - TROUGH_DEAD_UL
    for name in solvents:
        need = n_plates * sum(v[name] for *_, v in parsed) + (extra_ul or {}).get(name, 0)
        have = usable * len(SOLVENT_TROUGHS[name]) * n_reservoirs
        if need > have:
            errors.append(
                f"{name}: needs {need / 1000:.1f} mL but troughs {SOLVENT_TROUGHS[name]} on {n_reservoirs} "
                f"reservoir(s) only supply {have / 1000:.1f} mL - "
                + ("turn on the backup reservoir" if n_reservoirs == 1 else "add a spare trough to SOLVENT_TROUGHS")
            )
    if errors:
        raise ValueError("Invalid CSV:\n" + "\n".join(errors))
    return solvents, parsed


class Trough:
    """Tracks remaining volume of one liquid across its troughs, main reservoir first, then the backup."""

    def __init__(self, reservoirs, wells):
        self.wells = [res[w] for res in reservoirs for w in wells]
        self.remaining = [TROUGH_FILL_UL] * len(self.wells)

    def take(self, vol):
        for i, left in enumerate(self.remaining):
            if left - vol >= TROUGH_DEAD_UL:
                self.remaining[i] -= vol
                return self.wells[i]
        raise RuntimeError("Solvent troughs exhausted")  # prevented by validate()


def distribute(protocol, pipette, trough, targets, air_gap, disposal):
    """Multi-dispense: aspirate several wells' worth plus a disposal volume, then dispense
    each well from above with an air gap in between. Leftover goes back to the trough."""
    tip_ul = pipette.max_volume
    max_shot = tip_ul - air_gap - disposal
    shots = []
    for well, vol in targets:
        n = int(-(-vol // max_shot))  # ceil: split dispenses larger than one tip
        shots += [(well, vol / n)] * n
    i = 0
    while i < len(shots):
        batch, liquid = [], 0.0
        while i < len(shots) and liquid + shots[i][1] + disposal + air_gap <= tip_ul:
            batch.append(shots[i])
            liquid += shots[i][1]
            i += 1
        src = trough.take(liquid)
        pipette.aspirate(liquid + disposal, src.bottom(z=1))
        protocol.delay(seconds=1)  # let the meniscus settle (volatile, low viscosity)
        for well, vol in batch:
            pipette.air_gap(air_gap)
            pipette.dispense(vol + air_gap, well.top(z=-1))
        pipette.blow_out(src.top(z=-2))  # disposal volume back into its own trough


def run(protocol: protocol_api.ProtocolContext) -> None:
    params = protocol.params
    if params.temperature_c and params.temperature_c < 37:
        raise ValueError("Heater-shaker can't hold below 37 C - use 0 for ambient")
    first_shake = 0 if params.start_step == "fill" else int(params.start_step)  # plates count from 0
    if first_shake >= params.n_plates:
        raise ValueError(f"Start at plate {first_shake} but only {params.n_plates} plate(s)")

    # Load Modules:
    heater_shaker = protocol.load_module("heaterShakerModuleV1", HS_SLOT)
    hs_adapter = heater_shaker.load_adapter(HS_ADAPTER)

    # Load Labware:
    reservoirs = [protocol.load_labware(SOLVENT_RESERVOIR, RESERVOIR_SLOT, "Solvent reservoir")]
    if params.backup_reservoir:
        reservoirs.append(protocol.load_labware(SOLVENT_RESERVOIR, BACKUP_RESERVOIR_SLOT, "Backup solvent reservoir"))
    plates = [
        protocol.load_labware(READOUT_PLATE, slot, f"Readout plate {i}")
        for i, slot in enumerate(PLATE_SLOTS[: params.n_plates])
    ]
    blank = protocol.load_labware(READOUT_PLATE, BLANK_SLOT, "Solvent blank plate") if params.blank_plate else None
    blank_ul = {n: BLANK_UL for n in BLANK_SOLVENTS} if blank else {}

    # Load Pipettes (smallest first, see PIPETTES):
    pipettes = []
    for name, mount, rack, slot, air_gap, disposal, flow in PIPETTES:
        tips = protocol.load_labware(rack, slot)
        pip = protocol.load_instrument(name, mount, tip_racks=[tips])
        pip.flow_rate.aspirate, pip.flow_rate.dispense = flow
        pipettes.append((pip, air_gap, disposal))

    def pipette_for(vol):
        """Smallest pipette, unless the volume reaches the next pipette's minimum."""
        for (pip, *_), nxt in zip(pipettes, pipettes[1:] + [None]):
            if nxt is None or vol < nxt[0].min_volume:
                return pip

    csv_liquids, wells = validate(load_rows(protocol), pipettes[0][0].min_volume, plates[0], len(plates), blank_ul,
                                  len(reservoirs))
    liquids = [n for n in SOLVENT_TROUGHS if n in csv_liquids or n in blank_ul]

    # Define + load liquids (for the deck map in the app)
    colors = ["#e2d9e2", "#a6bfca", "#6d90c0", "#5f58b0", "#531e7c", "#64194b", "#9f3c50", "#c0755e"]
    for i, name in enumerate(liquids):
        need = len(plates) * sum(v.get(name, 0) for *_, v in wells) + blank_ul.get(name, 0)
        if need == 0:
            continue
        liquid = protocol.define_liquid(name, display_color=colors[i % len(colors)])
        for res in reservoirs:
            res.load_liquid(wells=SOLVENT_TROUGHS[name], liquid=liquid, volume=TROUGH_FILL_UL)
        protocol.comment(f"{name}: {need / 1000:.2f} mL needed from {SOLVENT_TROUGHS[name]}")

    # PROTOCOL STEPS

    # Step 1: fill all plates in one pass - same well on every plate back to back
    if params.start_step == "fill":
        protocol.pause(
            f"Check: {len(plates)} readout plate(s) with solids in slot(s) {', '.join(PLATE_SLOTS[: len(plates)])}, "
            f"solvent troughs filled ({TROUGH_FILL_UL / 1000:.0f} mL each"
            + (f", in slots {RESERVOIR_SLOT} and {BACKUP_RESERVOIR_SLOT})" if len(reservoirs) > 1 else ")")
            + (f", empty blank plate in slot {BLANK_SLOT}" if blank else "") + ". Resume to start."
        )
        heater_shaker.close_labware_latch()
        for name in liquids:
            trough = Trough(reservoirs, SOLVENT_TROUGHS[name])
            for pip, air_gap, disposal in pipettes:
                targets = [
                    (plate[well], v.get(name, 0)) for well, _, _, v in wells for plate in plates
                    if v.get(name, 0) > 0 and pipette_for(v[name]) is pip
                ]
                if name in blank_ul and pipette_for(BLANK_UL) is pip:  # blank well = trough well
                    targets.append((blank[SOLVENT_TROUGHS[name][0]], BLANK_UL))
                if not targets:
                    continue
                protocol.comment(f"{name} with {pip.name}: {len(targets)} dispenses")
                pip.pick_up_tip()
                # pre-wet: saturates the tip headspace with solvent vapour
                pip.mix(2, 0.8 * (pip.max_volume - air_gap), trough.wells[0].bottom(z=1))
                distribute(protocol, pip, trough, targets, air_gap, disposal)
                pip.drop_tip()

        protocol.pause("Seal every readout plate" + (" and the blank plate" if blank else "")
                       + " now (solvent-resistant seal), then resume.")

    # Step 2: shake each plate in turn (manual moves - the OT-2 has no gripper)
    for i, (plate, home) in enumerate(zip(plates, PLATE_SLOTS)):
        if i < first_shake:
            continue
        heater_shaker.open_labware_latch()
        protocol.move_labware(plate, hs_adapter, use_gripper=False)
        heater_shaker.close_labware_latch()
        if params.temperature_c:
            heater_shaker.set_and_wait_for_temperature(params.temperature_c)
        if params.shake_minutes:
            heater_shaker.set_and_wait_for_shake_speed(params.shake_rpm)
            protocol.delay(minutes=params.shake_minutes, msg=f"Dissolution / incubation: {plate.name}")
            heater_shaker.deactivate_shaker()
        heater_shaker.open_labware_latch()
        protocol.move_labware(plate, home, use_gripper=False)
        protocol.comment(f"{plate.name} done - it can go to the UV-Vis reader now.")
    heater_shaker.close_labware_latch()
    heater_shaker.deactivate_heater()

    protocol.comment(
        f"Done: {len(plates)} plate(s), {len(wells)} wells each. Read each plate, then: "
        "python bo_bridge.py merge --reader plate0.csv plate1.csv plate2.csv ..."
    )

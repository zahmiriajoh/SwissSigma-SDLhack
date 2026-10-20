from opentrons import protocol_api
from opentrons.protocol_api import RuntimeParameterRequiredError

requirements = {"robotType": "Flex", "apiLevel": "2.27"}

metadata = {
    "protocolName": "SDL Solubility: OT-2 workflow on a Flex (timing analog)",
    "author": "SwissSigma",
    "description": (
        "Flex replica of sdl_solubility_ot2.py for timing tests: same CSV, same liquid "
        "handling (P50 stands in for the P20, P1000 for the P300). "
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
# FLEX ANALOG of "OT protocols/sdl_solubility_ot2.py", for timing one round on a Flex.
# The liquid handling is the same step for step: same volume routing (< 20 uL small
# pipette, >= 20 uL large pipette), same tip capacities (20 / 300 uL, so every batch of
# aspirate + multi-dispense is identical), same air gaps, disposal volumes, flow rates,
# delays, pre-wet and tip use. The Flex P50 stands in for the OT-2 P20 and the Flex P1000
# for the OT-2 P300. Plate moves to the heater-shaker are manual (no gripper), like the OT-2.
# Timing is still approximate: Flex slots are ~20% further apart, and tip pickup, homing
# and z-heights differ between the robots. Look for the "TIMER" comments in the run log.
#
# OT-2 description (unchanged behaviour):
# Single-channel pipettes: P20 for volumes below the P300 minimum, P300 for the rest.
# One tip per solvent and pipette: it aspirates enough for several wells, dispensing the
# same well on every plate back to back, each from above the well with an air gap between
# shots. Tips only ever touch their own solvent, so they are reused across wells and plates.
#
# Deck: the OT-2 layout mapped slot for slot onto the Flex (OT-2 slot -> Flex slot):
#   10 -> A1 heater-shaker + universal flat adapter   11 -> A2 -           12 -> A3 trash bin
#    7 -> B1 -                         8 -> B2 P1000 tips   9 -> B3 P50 tips
#    4 -> C1 -                         5 -> C2 solvent reservoir   6 -> C3 -
#    1 -> D1 readout plate 1           2 -> D2 readout plate 2     3 -> D3 readout plate 3
# With the "Waste chute (D3)" trash setting, plate 3 moves to C3 instead.


# ---------------------------------------------------------------------------
# Deck / hardware configuration - keep solvent names in sync with bo_bridge.py
# ---------------------------------------------------------------------------

# Liquid name -> trough(s) on the 8-trough reservoir (wells A1..H1). Names must match the
# CSV columns "vol_<name>_ul". List more than one trough to give a liquid more volume.
SOLVENT_TROUGHS = {
    "DMF": ["A1"],
    "2MeTHF": ["B1"],
    "EtOAc": ["C1"],
    "DMC": ["D1"],
    "CPME": ["E1"],
    "MeCN": ["F1"],
    "iPrOAc": ["G1"],
    "diluent": ["H1"],  # only used if the CSV has a vol_diluent_ul column
}
TROUGH_FILL_UL = 25000  # volume loaded into every used trough before the run
TROUGH_DEAD_UL = 1000   # single channel: ~1 mm of liquid left in the trough

# Custom labware (../OT protocols/labware/, import into the Opentrons app)
READOUT_PLATE = "sarstedt_96_wellplate_390ul_flat"   # file ..._flatbottom.json
# Sarstedt 83.3924 is polystyrene, which esters, ethers and DMF attack (clouding raises
# absorbance). Known limitation - see README. Swap for a quartz/glass-bottom plate if available.
SOLVENT_RESERVOIR = "axygen_8_reservoir_30000ul"
HS_ADAPTER = "opentrons_universal_flat_adapter"      # custom JSONs declare this stacking offset

PLATE_SLOTS = {"bin": ["D1", "D2", "D3"], "chute": ["D1", "D2", "C3"]}  # by trash setting
RESERVOIR_SLOT = "C2"
HS_SLOT = "A1"

# Pipettes, smallest first, each standing in for an OT-2 pipette. The routing threshold
# and tip capacity are the OT-2 values, not the Flex pipettes' own, so the run matches
# the OT-2 step for step: a dispense goes to the small pipette below ot2_route_up_ul.
#   (pipette, mount, tip rack, slot, air_gap_ul, disposal_ul, (aspirate, dispense) uL/s,
#    OT-2 tip capacity uL, OT-2 blow-out uL/s)
PIPETTES = [
    ("flex_1channel_50", "right", "opentrons_flex_96_tiprack_50ul", "B3", 2, 2, (5, 10), 20, 7.56),      # P20
    ("flex_1channel_1000", "left", "opentrons_flex_96_tiprack_1000ul", "B2", 10, 10, (46, 92), 300, 92.86),  # P300
]
OT2_ROUTE_UP_UL = 20  # OT-2: volumes >= the P300 minimum (20 uL) go to the large pipette

WELL_MAX_UL = 320  # readout plate well (390 uL) minus headspace for shaking

# ---------------------------------------------------------------------------
# CSV import
# ---------------------------------------------------------------------------

FIXED_HEADER = ["well", "solute", "condition_id"]

# Used only when no CSV is selected (e.g. local simulation).
# Note: real CSV data arrives as strings, so the test data does too.
TEST_CSV = [
    FIXED_HEADER + ["vol_DMF_ul", "vol_2MeTHF_ul", "vol_EtOAc_ul", "vol_DMC_ul"],
    ["A1", "S1", "R1_DMFref", "300", "0", "0", "0"],
    ["A2", "S1", "R1_C01", "0", "300", "0", "0"],
    ["A3", "S1", "R1_C02", "0", "150", "150", "0"],
    ["A4", "S1", "R1_C03", "0", "100", "100", "100"],
    ["C1", "S2", "R1_DMFref", "300", "0", "0", "0"],
    ["C2", "S2", "R1_C01", "0", "300", "0", "0"],
    ["C3", "S2", "R1_C02", "0", "150", "150", "0"],
    ["C4", "S2", "R1_C04", "0", "0", "12", "288"],
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
    parameters.add_str(
        variable_name="start_step",
        display_name="Start at",
        description="Resume an interrupted run (plates already filled and sealed)",
        choices=[
            {"display_name": "Fill all plates", "value": "fill"},
            {"display_name": "Shake plate 1", "value": "1"},
            {"display_name": "Shake plate 2", "value": "2"},
            {"display_name": "Shake plate 3", "value": "3"},
        ],
        default="fill",
    )
    parameters.add_str(
        variable_name="trash",
        display_name="Trash",
        description="Trash bin in A3 matches the OT-2 (trash at the back right)",
        choices=[
            {"display_name": "Trash bin (A3)", "value": "bin"},
            {"display_name": "Waste chute (D3)", "value": "chute"},
        ],
        default="bin",
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


def validate(rows, min_volume, plate, n_plates):
    """Returns (liquid_names, [(well, solute, condition_id, {liquid: vol_ul})])."""
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
        need = n_plates * sum(v[name] for *_, v in parsed)
        have = usable * len(SOLVENT_TROUGHS[name])
        if need > have:
            errors.append(
                f"{name}: needs {need / 1000:.1f} mL but troughs {SOLVENT_TROUGHS[name]} "
                f"only supply {have / 1000:.1f} mL - add a spare trough to SOLVENT_TROUGHS"
            )
    if errors:
        raise ValueError("Invalid CSV:\n" + "\n".join(errors))
    return solvents, parsed


class Trough:
    """Tracks remaining volume of one liquid across its troughs."""

    def __init__(self, reservoir, wells):
        self.wells = [reservoir[w] for w in wells]
        self.remaining = [TROUGH_FILL_UL] * len(wells)

    def take(self, vol):
        for i, left in enumerate(self.remaining):
            if left - vol >= TROUGH_DEAD_UL:
                self.remaining[i] -= vol
                return self.wells[i]
        raise RuntimeError("Solvent troughs exhausted")  # prevented by validate()


def distribute(protocol, pipette, trough, targets, air_gap, disposal, tip_ul):
    """Multi-dispense: aspirate several wells' worth plus a disposal volume, then dispense
    each well from above with an air gap in between. Leftover goes back to the trough.
    tip_ul is the OT-2 tip capacity, so the batches match the OT-2 run."""
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
    first_shake = 1 if params.start_step == "fill" else int(params.start_step)
    if first_shake > params.n_plates:
        raise ValueError(f"Start at plate {first_shake} but only {params.n_plates} plate(s)")

    plate_slots = PLATE_SLOTS[params.trash]

    # Load trash + modules:
    if params.trash == "bin":
        protocol.load_trash_bin("A3")
    else:
        protocol.load_waste_chute()
    heater_shaker = protocol.load_module("heaterShakerModuleV1", HS_SLOT)
    hs_adapter = heater_shaker.load_adapter(HS_ADAPTER)

    # Load Labware:
    reservoir = protocol.load_labware(SOLVENT_RESERVOIR, RESERVOIR_SLOT, "Solvent reservoir")
    plates = [
        protocol.load_labware(READOUT_PLATE, slot, f"Readout plate {i + 1}")
        for i, slot in enumerate(plate_slots[: params.n_plates])
    ]

    # Load Pipettes (smallest first, see PIPETTES):
    pipettes = []
    for name, mount, rack, slot, air_gap, disposal, flow, tip_ul, blow in PIPETTES:
        tips = protocol.load_labware(rack, slot)
        pip = protocol.load_instrument(name, mount, tip_racks=[tips])
        pip.flow_rate.aspirate, pip.flow_rate.dispense = flow
        pip.flow_rate.blow_out = blow
        pip.default_speed = 400  # OT-2 default gantry speed (mm/s)
        pipettes.append((pip, air_gap, disposal, tip_ul))

    def pipette_for(vol):
        """Same routing as the OT-2: small pipette below 20 uL, large from 20 uL."""
        return pipettes[0][0] if vol < OT2_ROUTE_UP_UL else pipettes[1][0]

    liquids, wells = validate(load_rows(protocol), pipettes[0][0].min_volume, plates[0], len(plates))

    # Define + load liquids (for the deck map in the app)
    colors = ["#e2d9e2", "#a6bfca", "#6d90c0", "#5f58b0", "#531e7c", "#64194b", "#9f3c50", "#c0755e"]
    for i, name in enumerate(liquids):
        need = len(plates) * sum(v[name] for *_, v in wells)
        if need == 0:
            continue
        liquid = protocol.define_liquid(name, display_color=colors[i % len(colors)])
        reservoir.load_liquid(wells=SOLVENT_TROUGHS[name], liquid=liquid, volume=TROUGH_FILL_UL)
        protocol.comment(f"{name}: {need / 1000:.2f} mL needed from {SOLVENT_TROUGHS[name]}")

    # PROTOCOL STEPS

    # Step 1: fill all plates in one pass - same well on every plate back to back
    if params.start_step == "fill":
        protocol.pause(
            f"Check: {len(plates)} readout plate(s) with solids in slot(s) {', '.join(plate_slots[: len(plates)])}, "
            f"solvent troughs filled ({TROUGH_FILL_UL / 1000:.0f} mL each). Resume to start."
        )
        heater_shaker.close_labware_latch()
        protocol.comment("TIMER: fill start")
        for name in liquids:
            trough = Trough(reservoir, SOLVENT_TROUGHS[name])
            for pip, air_gap, disposal, tip_ul in pipettes:
                targets = [
                    (plate[well], v[name]) for well, _, _, v in wells for plate in plates
                    if v[name] > 0 and pipette_for(v[name]) is pip
                ]
                if not targets:
                    continue
                protocol.comment(f"{name} with {pip.name}: {len(targets)} dispenses")
                pip.pick_up_tip()
                # pre-wet: saturates the tip headspace with solvent vapour
                pip.mix(2, 0.8 * (tip_ul - air_gap), trough.wells[0].bottom(z=1))
                distribute(protocol, pip, trough, targets, air_gap, disposal, tip_ul)
                pip.drop_tip()

        protocol.comment("TIMER: fill end")
        protocol.pause("Seal every readout plate now (solvent-resistant seal), then resume.")

    # Step 2: shake each plate in turn (manual moves, like the OT-2 - gripper deliberately unused)
    for i, (plate, home) in enumerate(zip(plates, plate_slots)):
        if i + 1 < first_shake:
            continue
        heater_shaker.open_labware_latch()
        protocol.move_labware(plate, hs_adapter, use_gripper=False)
        heater_shaker.close_labware_latch()
        protocol.comment(f"TIMER: shake start {plate.name}")
        if params.temperature_c:
            heater_shaker.set_and_wait_for_temperature(params.temperature_c)
        if params.shake_minutes:
            heater_shaker.set_and_wait_for_shake_speed(params.shake_rpm)
            protocol.delay(minutes=params.shake_minutes, msg=f"Dissolution / incubation: {plate.name}")
            heater_shaker.deactivate_shaker()
        protocol.comment(f"TIMER: shake end {plate.name}")
        heater_shaker.open_labware_latch()
        protocol.move_labware(plate, home, use_gripper=False)
        protocol.comment(f"{plate.name} done - it can go to the UV-Vis reader now.")
    heater_shaker.close_labware_latch()
    heater_shaker.deactivate_heater()

    protocol.comment(
        f"Done: {len(plates)} plate(s), {len(wells)} wells each. Read each plate, then: "
        "python bo_bridge.py merge --reader plate1.csv plate2.csv plate3.csv ..."
    )

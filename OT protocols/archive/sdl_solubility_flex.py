from opentrons import protocol_api
from opentrons.protocol_api import SINGLE, RuntimeParameterRequiredError

requirements = {"robotType": "Flex", "apiLevel": "2.27"}

metadata = {
    "protocolName": "SDL Solubility: green-solvent mixtures (one BO round)",
    "author": "SwissSigma",
    "description": (
        "Reads one round of well-by-well solvent mixtures (CSV from bo_bridge.py layout) and "
        "builds them directly in up to 3 identical UV-Vis readout plates (solids pre-loaded). "
        "Each plate is covered and shaken on the heater-shaker right after it is filled."
    ),
}

# The CSV is well-level: every row is one well with its own mixture, so the plate layout
# (which solute sits where, how many DMF controls, how many replicate wells, how many
# conditions per solute) is decided entirely by bo_bridge.py - this script never assumes it.
# Every listed well gets the same mixture in each of the n_plates identical plates.
#
# Per-well volumes differ, so the 96-channel works in SINGLE-nozzle mode (A12 nozzle).
# Each tip only touches its own solvent: it aspirates enough for several wells and
# dispenses each from above the well (multi-dispense with an air gap between shots).
#
# Run order per plate: dispense every solvent -> cover -> heater-shaker -> shake -> back.
# Each plate gets the same history (filled, then immediately shaken for the same time).
#
# Deck (Flex, waste chute D3, staging A4-D4 gripper-only). With the A12 nozzle the pipette
# head overhangs to the LEFT and FRONT of the tip, and it can only reach rows A-C plus B3.
# Everything that gets pipetted (tip racks, reservoir, plates) therefore needs nothing tall
# on its left, front or front-left; checked in the simulator for this layout:
#   A1 50 uL tips       A2 -                 A3 200 uL tips
#   B1 readout plate 1  B2 readout plate 2   B3 readout plate 3
#   C1 -                C2 solvent reservoir C3 -
#   D1 heater-shaker    D2 -                 D3 waste chute
#   A4 lid stack (one lid per plate)


# ---------------------------------------------------------------------------
# Deck / hardware configuration - keep solvent names in sync with bo_bridge.py
# ---------------------------------------------------------------------------

# Solvent name -> trough(s) on the 8-trough reservoir (wells A1..H1). Names must match the
# CSV columns "vol_<name>_ul". List more than one trough to give a solvent more volume.
SOLVENT_TROUGHS = {
    "DMF": ["A1"],
    "2MeTHF": ["B1"],
    "EtOAc": ["C1"],
    "DMC": ["D1"],
    "CPME": ["E1"],
    "MeCN": ["F1"],
    "iPrOAc": ["G1"],
    # H1 spare (add as a second trough above if a solvent needs > ~24 mL)
}
TROUGH_FILL_UL = 25000  # volume loaded into every used trough before the run
TROUGH_DEAD_UL = 1000   # single tip: ~1 mm of liquid left in the trough

# Custom labware (labware/ folder, import into the Opentrons app)
READOUT_PLATE = "sarstedt_96_wellplate_390ul_flat"   # file ..._flatbottom.json
SOLVENT_RESERVOIR = "axygen_8_reservoir_30000ul"
# Opentrons library
HS_ADAPTER = "opentrons_universal_flat_adapter"      # custom JSONs declare this stacking offset
# SBS lid the gripper puts on each plate before shaking (limits solvent evaporation).
# Not a hermetic seal - check it sits flat on the readout plate and stays on while shaking.
LID = "opentrons_tough_universal_lid"

PLATE_SLOTS = ["B1", "B2", "B3"]   # up to 3 identical plates, filled in this order
RESERVOIR_SLOT = "C2"
HS_SLOT = "D1"
LID_SLOT = "A4"
NOZZLE = "A12"

# Each dispense uses the first tip class whose max_ul fits it; larger dispenses are split
# over several shots of the last class.
#   (name, tip rack, slot, max_ul, air_gap_ul, disposal_ul, (aspirate, dispense) uL/s)
TIP_CLASSES = [
    ("small", "opentrons_flex_96_tiprack_50ul", "A1", 40, 5, 5, (10, 25)),
    ("large", "opentrons_flex_96_tiprack_200ul", "A3", float("inf"), 10, 10, (50, 100)),
]

WELL_MAX_UL = 300  # readout plate well (390 uL) minus headspace for shaking

# ---------------------------------------------------------------------------
# CSV import
# ---------------------------------------------------------------------------

FIXED_HEADER = ["well", "solute", "condition_id"]

# Used only when no CSV is selected (e.g. local simulation).
# Note: real CSV data arrives as strings, so the test data does too.
TEST_CSV = [
    FIXED_HEADER + ["vol_DMF_ul", "vol_2MeTHF_ul", "vol_EtOAc_ul", "vol_DMC_ul"],
    ["A1", "S1", "R1_DMFref", "200", "0", "0", "0"],
    ["A2", "S1", "R1_C01", "0", "200", "0", "0"],
    ["A3", "S1", "R1_C02", "0", "100", "100", "0"],
    ["A4", "S1", "R1_C03", "0", "67", "67", "66"],
    ["C1", "S2", "R1_DMFref", "200", "0", "0", "0"],
    ["C2", "S2", "R1_C01", "0", "200", "0", "0"],
    ["C3", "S2", "R1_C02", "0", "100", "100", "0"],
    ["C4", "S2", "R1_C04", "0", "0", "15", "185"],
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
        description="Replicate readout plates, all filled from the same CSV (slots B1, B2, B3)",
        default=3,
        minimum=1,
        maximum=3,
    )
    parameters.add_int(
        variable_name="start_plate",
        display_name="Start at plate",
        description="Resume an interrupted run: earlier plates are skipped",
        default=1,
        minimum=1,
        maximum=3,
    )
    parameters.add_str(
        variable_name="cover_mode",
        display_name="Cover while shaking",
        description="Gripper lid from A4 (hands-free), manual seal (pause), or open (evaporation!)",
        choices=[
            {"display_name": "Gripper lid", "value": "lid"},
            {"display_name": "Manual seal", "value": "seal"},
            {"display_name": "Open", "value": "none"},
        ],
        default="lid",
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
        default=60,
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


def validate(rows, pipette, plate, n_plates):
    """Returns (solvent_names, [(well, solute, condition_id, {solvent: vol_ul})])."""
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
            elif 0 < vol < pipette.min_volume:
                errors.append(
                    f"line {line_no}: {name} {vol} uL below pipette minimum "
                    f"{pipette.min_volume} uL (bo_bridge.py snaps these)"
                )
            vols[name] = vol
        total = sum(vols.values())
        if total <= 0:
            errors.append(f"line {line_no}: well {well} receives no solvent")
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
                f"only supply {have / 1000:.1f} mL - add the spare trough to SOLVENT_TROUGHS"
            )
    if errors:
        raise ValueError("Invalid CSV:\n" + "\n".join(errors))
    return solvents, parsed


def tip_class_for(vol):
    """Smallest tip class whose max_ul fits this dispense."""
    return next(c for c in TIP_CLASSES if vol <= c[3])[0]


class Trough:
    """Tracks remaining volume of one solvent across its troughs."""

    def __init__(self, reservoir, wells):
        self.wells = [reservoir[w] for w in wells]
        self.remaining = [TROUGH_FILL_UL] * len(wells)

    def take(self, vol):
        for i, left in enumerate(self.remaining):
            if left - vol >= TROUGH_DEAD_UL:
                self.remaining[i] -= vol
                return self.wells[i]
        raise RuntimeError("Solvent troughs exhausted")  # prevented by validate()


def distribute(protocol, pipette, trough, targets, tip_ul, air_gap, disposal):
    """Multi-dispense: aspirate several wells' worth plus a disposal volume, then dispense
    each well from above with an air gap in between. Leftover goes back to the trough."""
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
    if params.start_plate > params.n_plates:
        raise ValueError(f"start_plate {params.start_plate} > n_plates {params.n_plates}")
    if params.temperature_c and params.temperature_c < 37:
        raise ValueError("Heater-shaker can't hold below 37 C - use 0 for ambient")

    # Load trash + modules:
    protocol.load_waste_chute()
    heater_shaker = protocol.load_module("heaterShakerModuleV1", HS_SLOT)
    hs_adapter = heater_shaker.load_adapter(HS_ADAPTER)

    # Load Labware:
    tip_racks = {name: protocol.load_labware(rack, slot) for name, rack, slot, *_ in TIP_CLASSES}
    reservoir = protocol.load_labware(SOLVENT_RESERVOIR, RESERVOIR_SLOT, "Solvent reservoir")
    plates = [
        protocol.load_labware(READOUT_PLATE, slot, f"Readout plate {i + 1}")
        for i, slot in enumerate(PLATE_SLOTS[: params.n_plates])
    ]
    todo = plates[params.start_plate - 1:]
    lid_stack = (
        protocol.load_lid_stack(LID, LID_SLOT, quantity=len(todo))
        if params.cover_mode == "lid" else None
    )

    # Load Pipettes:
    pipette = protocol.load_instrument("flex_96channel_1000", "left")

    solvents, wells = validate(load_rows(protocol), pipette, plates[0], len(todo))

    # Define + load liquids (for the deck map in the app)
    colors = ["#25c5ff", "#ff6b00", "#7bd148", "#9a7cff", "#ff4f9a", "#00b3a4", "#c9a227", "#888888"]
    for i, name in enumerate(solvents):
        need = len(todo) * sum(v[name] for *_, v in wells)
        if need == 0:
            continue
        liquid = protocol.define_liquid(name, display_color=colors[i % len(colors)])
        reservoir.load_liquid(wells=SOLVENT_TROUGHS[name], liquid=liquid, volume=TROUGH_FILL_UL)
        protocol.comment(f"{name}: {need / 1000:.2f} mL needed from {SOLVENT_TROUGHS[name]}")

    troughs = {name: Trough(reservoir, SOLVENT_TROUGHS[name]) for name in solvents}

    # PROTOCOL STEPS
    protocol.pause(
        f"Check: {len(todo)} readout plate(s) with solids in "
        f"{', '.join(PLATE_SLOTS[params.start_plate - 1: params.n_plates])}, "
        f"solvent troughs filled ({TROUGH_FILL_UL / 1000:.0f} mL each), tip racks without lids"
        + (f", {len(todo)} plate lid(s) stacked in {LID_SLOT}" if lid_stack else "")
        + ". Resume to start."
    )
    heater_shaker.close_labware_latch()

    for plate, home in zip(todo, PLATE_SLOTS[params.start_plate - 1:]):
        # Step 1: build every well's mixture, one solvent (and tip size) at a time
        for name in solvents:
            for cls, _, _, _, air_gap, disposal, flow in TIP_CLASSES:
                targets = [
                    (plate[well], v[name]) for well, _, _, v in wells
                    if v[name] > 0 and tip_class_for(v[name]) == cls
                ]
                if not targets:
                    continue
                rack = tip_racks[cls]
                tip_ul = rack.wells()[0].max_volume
                protocol.comment(f"{plate.name}: {name} ({cls} tips) into {len(targets)} wells")
                pipette.configure_nozzle_layout(style=SINGLE, start=NOZZLE, tip_racks=[rack])
                pipette.flow_rate.aspirate, pipette.flow_rate.dispense = flow
                pipette.pick_up_tip()
                # pre-wet: saturates the tip headspace with solvent vapour
                pipette.mix(2, 0.8 * (tip_ul - air_gap), troughs[name].wells[0].bottom(z=1))
                distribute(protocol, pipette, troughs[name], targets, tip_ul, air_gap, disposal)
                pipette.drop_tip()

        # Step 2: cover and shake this plate straight away
        if params.cover_mode == "lid":
            protocol.move_lid(lid_stack, plate, use_gripper=True)
        elif params.cover_mode == "seal":
            protocol.pause(f"Seal {plate.name} in {home} (solvent-resistant seal), then resume.")
        heater_shaker.open_labware_latch()
        protocol.move_labware(plate, hs_adapter, use_gripper=True)
        heater_shaker.close_labware_latch()
        if params.temperature_c:
            heater_shaker.set_and_wait_for_temperature(params.temperature_c)
        if params.shake_minutes:
            heater_shaker.set_and_wait_for_shake_speed(params.shake_rpm)
            protocol.delay(minutes=params.shake_minutes, msg=f"Dissolution / incubation: {plate.name}")
            heater_shaker.deactivate_shaker()
        heater_shaker.open_labware_latch()
        protocol.move_labware(plate, home, use_gripper=True)
        heater_shaker.close_labware_latch()

    heater_shaker.deactivate_heater()
    protocol.comment(
        f"Done: {len(todo)} plate(s), {len(wells)} wells each. Remove lids/seals and read each "
        "plate on the UV-Vis reader, then: python bo_bridge.py merge --reader p1.csv p2.csv p3.csv ..."
    )

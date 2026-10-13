from opentrons import protocol_api
from opentrons.protocol_api import RuntimeParameterRequiredError

requirements = {"robotType": "OT-2", "apiLevel": "2.27"}

metadata = {
    "protocolName": "Demo: CSV driven transfers",
    "author": "JS",
    "description": "Transfers source_well -> dest_well with volume_ul, as given in the CSV.",
}


# Code for loading csv
# add_parameters(), load_rows() and validate() are functions related to the CSV import,
# which is not possible to implement in the protocol designer directly. 
# add_parameters() and load_rows() are the essential core of the import functionality.
# Copy&Paste&Change according to your needs

EXPECTED_HEADER = ["source_well", "dest_well", "volume_ul"]

# Used only when no CSV is selected (e.g. local simulation).
# Note: real CSV data arrives as strings, so the test data does too.
TEST_CSV = [
    EXPECTED_HEADER,
    ["A1", "A1", "220"],
    ["A1", "B1", "335"],
]

def add_parameters(parameters: protocol_api.ParameterContext):
    parameters.add_csv_file(
        variable_name="input_csv",
        display_name="Input parameters (CSV)",
        description="Columns: source_well, dest_well, volume_ul",
    )


def load_rows(protocol):
    try:
        rows = protocol.params.input_csv.parse_as_csv()
    except RuntimeParameterRequiredError:
        protocol.comment("No CSV selected - using built-in test data")
        rows = TEST_CSV
    return rows


def validate(rows, pipette, source, dest):
    header = [c.strip() for c in rows[0]]
    if header != EXPECTED_HEADER:
        raise ValueError(f"Unexpected header {header}, expected {EXPECTED_HEADER}")
    errors, parsed = [], []
    for line_no, row in enumerate(rows[1:], start=2):
        row = [c.strip() for c in row]
        if len(row) != 3:
            errors.append(f"line {line_no}: expected 3 columns, got {len(row)}")
            continue
        src, dst, vol_str = row
        if src not in source.wells_by_name():
            errors.append(f"line {line_no}: unknown source well '{src}'")
        if dst not in dest.wells_by_name():
            errors.append(f"line {line_no}: unknown destination well '{dst}'")
        try:
            vol = float(vol_str)
        except ValueError:
            errors.append(f"line {line_no}: volume '{vol_str}' is not a number")
            continue
        if not pipette.min_volume <= vol <= pipette.max_volume:
            errors.append(
                f"line {line_no}: {vol} uL outside pipette range "
                f"{pipette.min_volume}-{pipette.max_volume} uL"
            )
        parsed.append((src, dst, vol))
    if errors:
        raise ValueError("Invalid CSV:\n" + "\n".join(errors))
    return parsed

# run() function contains all information the robot needs to run, 
# regardless if it's statically written or dynamic via variables

def run(protocol: protocol_api.ProtocolContext):
    tips = protocol.load_labware(
        "opentrons_96_tiprack_1000ul",
        location="9",
        version=1,
    )
    source = protocol.load_labware("corning_96_wellplate_360ul_flat", "2", "Source")
    dest = protocol.load_labware("corning_96_wellplate_360ul_flat", "3", "Destination")
    pipette = protocol.load_instrument(
            "p1000_single_gen2", mount="left", tip_racks=[tips]
        )

    transfers = validate(load_rows(protocol), pipette, source, dest)

    for src, dst, vol in transfers:
        pipette.flow_rate.aspirate = 100
        pipette.flow_rate.dispense = 100
        pipette.transfer(
            vol, 
            source[src].bottom(z=2), # z-height: 2 mm from the bottom 
            dest[dst].top(z=-2), # z-height: dispense 2 mm below the rim of the well 
            new_tip="always",
            blow_out=True,
            touch_tip=True,
            air_gap=10,
            )

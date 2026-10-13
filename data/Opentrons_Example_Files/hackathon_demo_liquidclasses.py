import json
from opentrons import protocol_api, types
from opentrons.protocol_api import RuntimeParameterRequiredError

metadata = {
    "protocolName": "Hackathon Demo: CSV Import ",
    "author": "JS",
    "description": "Colour mixing in a row of a 96WP",
    "created": "2026-10-05T08:54:35.665Z",
    "internalAppBuildDate": "Thu, 13 Aug 2026 17:57:06 GMT",
    "lastModified": "2026-10-05T09:00:36.508Z",
    "protocolDesigner": "26.6.0",
    "source": "Protocol Designer",
}

requirements = {"robotType": "OT-2", "apiLevel": "2.27"}



# Code for loading csv
# add_parameters(), load_rows() and validate() are functions related to the CSV import,
# which is not possible to implement in the protocol designer directly. 
# add_parameters() and load_rows() are the essential core of the import functionality.
# Copy&Paste&Change according to your needs

EXPECTED_HEADER = ["dest_well", "volume_solvent_ul", "volume_red_ul", "volume_yellow_ul"]

# Used only when no CSV is selected (e.g. local simulation).
# Note: real CSV data arrives as strings, so the test data does too.
TEST_CSV = [
    EXPECTED_HEADER,
    ["A1", "100", "120", "110"],
    ["A2", "110", "132", "120"],
    ["A3", "120", "112", "130"]
]

def add_parameters(parameters: protocol_api.ParameterContext):
    parameters.add_csv_file(
        variable_name="input_csv",
        display_name="Input parameters (CSV)",
        description="Columns: dest_well, volume_solvent_ul, volume_red_ul, volume_yellow_ul",
    )


def load_rows(protocol):
    try:
        rows = protocol.params.input_csv.parse_as_csv()
    except RuntimeParameterRequiredError:
        protocol.comment("No CSV selected - using built-in test data")
        rows = TEST_CSV
    return rows


def validate(rows, pipette, dest):
    header = [c.strip() for c in rows[0]]
    if header != EXPECTED_HEADER:
        raise ValueError(f"Unexpected header {header}, expected {EXPECTED_HEADER}")
    errors, parsed = [], []
    for line_no, row in enumerate(rows[1:], start=2):
        row = [c.strip() for c in row]
        if len(row) != 4:
            errors.append(f"line {line_no}: expected 4 columns, got {len(row)}")
            continue
        dst, vol_solv_str, vol_red_str, vol_yel_str = row
        if dst not in dest.wells_by_name():
            errors.append(f"line {line_no}: unknown destination well '{dst}'")
        try:
            vol_solv = float(vol_solv_str)
            vol_red = float(vol_red_str)
            vol_yel = float(vol_yel_str)

        # Check if valid input for volumes - e.g. for solvent:
        except ValueError:
            errors.append(f"line {line_no}: volume '{vol_solv_str}' is not a number")
            continue
        if not pipette.min_volume <= vol_solv <= pipette.max_volume:
            errors.append(
                f"line {line_no}: {vol_solv} uL outside pipette range "
                f"{pipette.min_volume}-{pipette.max_volume} uL"
            )
        parsed.append((dst, vol_solv, vol_red, vol_yel))
    if errors:
        raise ValueError("Invalid CSV:\n" + "\n".join(errors))
    return parsed


# run() function contains all information the robot needs to run, 
# regardless if it's statically written or dynamic via variables

def run(protocol: protocol_api.ProtocolContext) -> None:
    # Load Modules:
    heater_shaker_module_1 = protocol.load_module("heaterShakerModuleV1", "10")

    # Load Labware:
    tip_rack_1 = protocol.load_labware(
        "opentrons_96_tiprack_1000ul",
        location="8",
        namespace="opentrons",
        version=1,
    )
    tip_rack_2 = protocol.load_labware(
        "opentrons_96_tiprack_300ul",
        location="7",
        namespace="opentrons",
        version=1,
    )
    tube_rack_1 = protocol.load_labware(
        "opentrons_10_tuberack_falcon_4x50ml_6x15ml_conical",
        location="5",
        namespace="opentrons",
        version=3,
    )
    well_plate_1 = protocol.load_labware(
        "corning_96_wellplate_360ul_flat",
        location="6",
        namespace="opentrons",
        version=5,
    )

    # Load Pipettes:
    pipette_left = protocol.load_instrument("p1000_single_gen2", "left")
    pipette_right = protocol.load_instrument("p300_multi_gen2", "right")

    # Define Liquids:
    liquid_1 = protocol.define_liquid(
        "solvent",
        display_color="#25c5ffff",
    )
    liquid_2 = protocol.define_liquid(
        "red dye",
        display_color="#ff0000ff",
    )
    liquid_3 = protocol.define_liquid(
        "yellow dye",
        display_color="#ffd600ff",
    )

    # Load Liquids:
    tube_rack_1.load_liquid(
        wells=["A3"],
        liquid=liquid_1,
        volume=20000,
    )
    tube_rack_1.load_liquid(
        wells=["A4"],
        liquid=liquid_2,
        volume=20000,
    )
    tube_rack_1.load_liquid(
        wells=["B3"],
        liquid=liquid_3,
        volume=20000,
    )

    # PROTOCOL STEPS

    # Validate and import data from CSV

    transfers = validate(load_rows(protocol), pipette_left, well_plate_1)

    # Step 1: transfer solvent
    for dst, vol_solv, vol_red, vol_yel in transfers:
        pipette_left.distribute_with_liquid_class(
            volume=vol_solv,
            source=[tube_rack_1["A3"]],
            dest=[well_plate_1[dst]],
            new_tip="once",
            trash_location=protocol.fixed_trash,
            keep_last_tip=True,
            tip_racks=[tip_rack_1],
            liquid_class=protocol.define_liquid_class(
                name="distribute_step_1",
                properties={"p1000_single_gen2": {"opentrons/opentrons_96_tiprack_1000ul/1": {
                    "aspirate": {
                        "aspirate_position": {
                            "offset": {"x": 0, "y": 0, "z": 20},
                            "position_reference": "well-bottom",
                        },
                        "flow_rate_by_volume": [(0, 274.7)],
                        "pre_wet": False,
                        "correction_by_volume": [(0, 0)],
                        "delay": {"enabled": False},
                        "mix": {"enabled": False},
                        "submerge": {
                            "delay": {"enabled": False},
                            "speed": 125,
                            "start_position": {
                                "offset": {"x": 0, "y": 0, "z": 2},
                                "position_reference": "well-top",
                            },
                        },
                        "retract": {
                            "air_gap_by_volume": [(0, 0)],
                            "delay": {"enabled": False},
                            "end_position": {
                                "offset": {"x": 0, "y": 0, "z": 2},
                                "position_reference": "well-top",
                            },
                            "speed": 125,
                            "touch_tip": {"enabled": False},
                        },
                    },
                    "dispense": {
                        "dispense_position": {
                            "offset": {"x": 0, "y": 0, "z": 1},
                            "position_reference": "well-bottom",
                        },
                        "flow_rate_by_volume": [(0, 274.7)],
                        "delay": {"enabled": False},
                        "submerge": {
                            "delay": {"enabled": False},
                            "speed": 125,
                            "start_position": {
                                "offset": {"x": 0, "y": 0, "z": 2},
                                "position_reference": "well-top",
                            },
                        },
                        "retract": {
                            "air_gap_by_volume": [(0, 0)],
                            "delay": {"enabled": False},
                            "end_position": {
                                "offset": {"x": 0, "y": 0, "z": 2},
                                "position_reference": "well-top",
                            },
                            "speed": 125,
                            "touch_tip": {"enabled": False},
                            "blowout": {
                                "enabled": True,
                                "location": "source",
                                "flow_rate": 274.7,
                                "blowout_position": {
                                    "offset": {"x": 0, "y": 0, "z": 1},
                                    "position_reference": "well-top",
                                },
                            },
                        },
                        "correction_by_volume": [(0, 0)],
                        "push_out_by_volume": [(0, 0)],
                        "mix": {"enabled": False},
                    },
                    "multi_dispense": {
                        "dispense_position": {
                            "offset": {"x": 0, "y": 0, "z": 1},
                            "position_reference": "well-bottom",
                        },
                        "flow_rate_by_volume": [(0, 274.7)],
                        "delay": {"enabled": False},
                        "submerge": {
                            "delay": {"enabled": False},
                            "speed": 125,
                            "start_position": {
                                "offset": {"x": 0, "y": 0, "z": 2},
                                "position_reference": "well-top",
                            },
                        },
                        "retract": {
                            "air_gap_by_volume": [(0, 0)],
                            "delay": {"enabled": False},
                            "end_position": {
                                "offset": {"x": 0, "y": 0, "z": 2},
                                "position_reference": "well-top",
                            },
                            "speed": 125,
                            "touch_tip": {"enabled": False},
                            "blowout": {
                                "enabled": True,
                                "location": "source",
                                "flow_rate": 274.7,
                                "blowout_position": {
                                    "offset": {"x": 0, "y": 0, "z": 1},
                                    "position_reference": "well-top",
                                },
                            },
                        },
                        "correction_by_volume": [(0, 0)],
                        "conditioning_by_volume": [(0, 0)],
                        "disposal_by_volume": [(0, 100)],
                    },
                }}},
            ),
        )
        pipette_left.drop_tip()

    # Step 2: transfer red dye
    for dst, vol_solv, vol_red, vol_yel in transfers:
        pipette_left.transfer_with_liquid_class(
        volume=vol_red,
        source=[tube_rack_1["A4"]],
        dest=[well_plate_1[dst]],
        new_tip="always",
        trash_location=protocol.fixed_trash,
        keep_last_tip=True,
        tip_racks=[tip_rack_1],
        liquid_class=protocol.define_liquid_class(
            name="transfer_step_2",
            properties={"p1000_single_gen2": {"opentrons/opentrons_96_tiprack_1000ul/1": {
                "aspirate": {
                    "aspirate_position": {
                        "offset": {"x": 0, "y": 0, "z": 20},
                        "position_reference": "well-bottom",
                    },
                    "flow_rate_by_volume": [(0, 274.7)],
                    "pre_wet": False,
                    "correction_by_volume": [(0, 0)],
                    "delay": {"enabled": False},
                    "mix": {"enabled": False},
                    "submerge": {
                        "delay": {"enabled": False},
                        "speed": 125,
                        "start_position": {
                            "offset": {"x": 0, "y": 0, "z": 2},
                            "position_reference": "well-top",
                        },
                    },
                    "retract": {
                        "air_gap_by_volume": [(0, 0)],
                        "delay": {"enabled": False},
                        "end_position": {
                            "offset": {"x": 0, "y": 0, "z": 2},
                            "position_reference": "well-top",
                        },
                        "speed": 125,
                        "touch_tip": {"enabled": False},
                    },
                },
                "dispense": {
                    "dispense_position": {
                        "offset": {"x": 0, "y": 0, "z": 1},
                        "position_reference": "well-bottom",
                    },
                    "flow_rate_by_volume": [(0, 274.7)],
                    "delay": {"enabled": False},
                    "submerge": {
                        "delay": {"enabled": False},
                        "speed": 125,
                        "start_position": {
                            "offset": {"x": 0, "y": 0, "z": 2},
                            "position_reference": "well-top",
                        },
                    },
                    "retract": {
                        "air_gap_by_volume": [(0, 0)],
                        "delay": {"enabled": False},
                        "end_position": {
                            "offset": {"x": 0, "y": 0, "z": 2},
                            "position_reference": "well-top",
                        },
                        "speed": 125,
                        "touch_tip": {"enabled": False},
                        "blowout": {"enabled": False},
                    },
                    "correction_by_volume": [(0, 0)],
                    "push_out_by_volume": [(0, 0)],
                    "mix": {"enabled": False},
                },
            }}},
        ),
    )
        pipette_left.drop_tip()

    # Step 3: transfer yellow dye
    for dst, vol_solv, vol_red, vol_yel in transfers:
        pipette_left.transfer_with_liquid_class(
        volume=vol_yel,
        source=[tube_rack_1["B3"]],
        dest=[well_plate_1[dst]],
        new_tip="always",
        trash_location=protocol.fixed_trash,
        keep_last_tip=True,
        tip_racks=[tip_rack_1],
        liquid_class=protocol.define_liquid_class(
            name="transfer_step_3",
            properties={"p1000_single_gen2": {"opentrons/opentrons_96_tiprack_1000ul/1": {
                "aspirate": {
                    "aspirate_position": {
                        "offset": {"x": 0, "y": 0, "z": 20},
                        "position_reference": "well-bottom",
                    },
                    "flow_rate_by_volume": [(0, 274.7)],
                    "pre_wet": False,
                    "correction_by_volume": [(0, 0)],
                    "delay": {"enabled": False},
                    "mix": {"enabled": False},
                    "submerge": {
                        "delay": {"enabled": False},
                        "speed": 125,
                        "start_position": {
                            "offset": {"x": 0, "y": 0, "z": 2},
                            "position_reference": "well-top",
                        },
                    },
                    "retract": {
                        "air_gap_by_volume": [(0, 0)],
                        "delay": {"enabled": False},
                        "end_position": {
                            "offset": {"x": 0, "y": 0, "z": 2},
                            "position_reference": "well-top",
                        },
                        "speed": 125,
                        "touch_tip": {"enabled": False},
                    },
                },
                "dispense": {
                    "dispense_position": {
                        "offset": {"x": 0, "y": 0, "z": 1},
                        "position_reference": "well-bottom",
                    },
                    "flow_rate_by_volume": [(0, 274.7)],
                    "delay": {"enabled": False},
                    "submerge": {
                        "delay": {"enabled": False},
                        "speed": 125,
                        "start_position": {
                            "offset": {"x": 0, "y": 0, "z": 2},
                            "position_reference": "well-top",
                        },
                    },
                    "retract": {
                        "air_gap_by_volume": [(0, 0)],
                        "delay": {"enabled": False},
                        "end_position": {
                            "offset": {"x": 0, "y": 0, "z": 2},
                            "position_reference": "well-top",
                        },
                        "speed": 125,
                        "touch_tip": {"enabled": False},
                        "blowout": {"enabled": False},
                    },
                    "correction_by_volume": [(0, 0)],
                    "push_out_by_volume": [(0, 0)],
                    "mix": {"enabled": False},
                },
            }}},
        ),
    )
        pipette_left.drop_tip()

DESIGNER_APPLICATION = """{"robot":{"model":"OT-2 Standard"},"designerApplication":{"name":"opentrons/protocol-designer","version":"2606.0.0","data":{"pipetteTiprackAssignments":{"b97c546a-f3f9-434b-9df6-b574e145fa31":["opentrons/opentrons_96_tiprack_1000ul/1"],"9edc7c08-d05a-4ed4-84e9-5e09ef789181":["opentrons/opentrons_96_tiprack_300ul/1"]},"dismissedWarnings":{"form":[],"timeline":[]},"ingredients":{"0":{"displayName":"solvent","displayColor":"#25c5ffff","description":null,"liquidGroupId":"0"},"1":{"displayName":"red dye","displayColor":"#ff0000ff","description":null,"liquidGroupId":"1"},"2":{"displayName":"yellow dye","displayColor":"#ffd600ff","description":null,"liquidGroupId":"2"}},"ingredLocations":{"b03e8b52-2c1b-4192-a3b8-52dbef0f335e:opentrons/opentrons_10_tuberack_falcon_4x50ml_6x15ml_conical/3":{"A3":{"0":{"volume":20000}},"A4":{"1":{"volume":20000}},"B3":{"2":{"volume":20000}}}},"savedStepForms":{"__INITIAL_DECK_SETUP_STEP__":{"stepType":"manualIntervention","id":"__INITIAL_DECK_SETUP_STEP__","labwareLocationUpdate":{"a865b740-1a0d-43de-9e8a-811965071376:opentrons/opentrons_96_tiprack_1000ul/1":"8","e4ff6ac7-c65f-4c1f-90aa-5fc624b4b0e6:opentrons/opentrons_96_tiprack_300ul/1":"7","b03e8b52-2c1b-4192-a3b8-52dbef0f335e:opentrons/opentrons_10_tuberack_falcon_4x50ml_6x15ml_conical/3":"5","1941cbb2-232a-44c0-a935-a6a8c1e278bc:opentrons/corning_96_wellplate_360ul_flat/5":"6"},"pipetteLocationUpdate":{"b97c546a-f3f9-434b-9df6-b574e145fa31":"left","9edc7c08-d05a-4ed4-84e9-5e09ef789181":"right"},"moduleLocationUpdate":{"6b4fbab6-ff7d-4b28-9a9b-50d197f2dcbf:heaterShakerModuleType":"10"},"moduleStateUpdate":{},"trashBinLocationUpdate":{"bb101ae0-e2ba-4920-a0ec-40fae9f0ba72:trashBin":"cutout12"},"wasteChuteLocationUpdate":{},"stagingAreaLocationUpdate":{},"gripperLocationUpdate":{}},"a9c2a94c-fc59-4811-855d-77caa4db1e84":{"id":"a9c2a94c-fc59-4811-855d-77caa4db1e84","stepType":"moveLiquid","stepName":"transfer","stepDetails":"","stepNumber":0,"aspirate_airGap_checkbox":false,"aspirate_airGap_volume":"","aspirate_delay_checkbox":false,"aspirate_delay_seconds":"1","aspirate_flowRate":"274.7","aspirate_labware":"b03e8b52-2c1b-4192-a3b8-52dbef0f335e:opentrons/opentrons_10_tuberack_falcon_4x50ml_6x15ml_conical/3","aspirate_mix_checkbox":false,"aspirate_mix_times":"","aspirate_mix_volume":null,"aspirate_mmFromBottom":20,"aspirate_position_reference":"well-bottom","aspirate_retract_delay_seconds":"0","aspirate_retract_mmFromBottom":2,"aspirate_retract_speed":"125","aspirate_retract_x_position":0,"aspirate_retract_y_position":0,"aspirate_retract_position_reference":"well-top","aspirate_submerge_delay_seconds":"0","aspirate_submerge_speed":"125","aspirate_submerge_mmFromBottom":2,"aspirate_submerge_x_position":0,"aspirate_submerge_y_position":0,"aspirate_submerge_position_reference":"well-top","aspirate_touchTip_checkbox":false,"aspirate_touchTip_mmFromTop":null,"aspirate_touchTip_speed":60,"aspirate_touchTip_mmFromEdge":0,"aspirate_wellOrder_first":"t2b","aspirate_wellOrder_second":"l2r","aspirate_wells_grouped":false,"aspirate_wells":["A3"],"aspirate_x_position":0,"aspirate_y_position":0,"blowout_checkbox":false,"blowout_flowRate":"274.7","blowout_location":"source_well","blowout_mmFromBottom":null,"blowout_x_position":null,"blowout_y_position":null,"blowout_position_reference":"well-top","changeTip":"always","conditioning_checkbox":false,"conditioning_volume":null,"dispense_airGap_checkbox":false,"dispense_airGap_volume":"","dispense_delay_checkbox":false,"dispense_delay_seconds":"1","dispense_flowRate":"274.7","dispense_labware":"1941cbb2-232a-44c0-a935-a6a8c1e278bc:opentrons/corning_96_wellplate_360ul_flat/5","dispense_mix_checkbox":false,"dispense_mix_times":"","dispense_mix_volume":null,"dispense_mmFromBottom":null,"dispense_position_reference":"well-bottom","dispense_retract_delay_seconds":"0","dispense_retract_mmFromBottom":2,"dispense_retract_speed":"125","dispense_retract_x_position":0,"dispense_retract_y_position":0,"dispense_retract_position_reference":"well-top","dispense_submerge_delay_seconds":"0","dispense_submerge_speed":"125","dispense_submerge_mmFromBottom":2,"dispense_submerge_x_position":0,"dispense_submerge_y_position":0,"dispense_submerge_position_reference":"well-top","dispense_touchTip_checkbox":false,"dispense_touchTip_mmFromTop":null,"dispense_touchTip_speed":60,"dispense_touchTip_mmFromEdge":0,"dispense_wellOrder_first":"t2b","dispense_wellOrder_second":"l2r","dispense_wells":["A1","A2","A3"],"dispense_x_position":0,"dispense_y_position":0,"disposalVolume_checkbox":true,"disposalVolume_volume":"100","dropTip_location":"bb101ae0-e2ba-4920-a0ec-40fae9f0ba72:trashBin","liquidClassesSupported":true,"liquidClass":"none","nozzles":"ALL","path":"multiDispense","pipette":"b97c546a-f3f9-434b-9df6-b574e145fa31","preWetTip":false,"primaryNozzle":"A1","pushOut_checkbox":false,"pushOut_volume":"0","tipRack":"opentrons/opentrons_96_tiprack_1000ul/1","tip_tracking":"automatic","tiprack_selected":null,"tips_selected":[],"volume":"100"},"ee655c6b-57a5-426b-9995-235befadb60f":{"id":"ee655c6b-57a5-426b-9995-235befadb60f","stepType":"moveLiquid","stepName":"transfer","stepDetails":"","stepNumber":0,"aspirate_airGap_checkbox":false,"aspirate_airGap_volume":"","aspirate_delay_checkbox":false,"aspirate_delay_seconds":"1","aspirate_flowRate":"274.7","aspirate_labware":"b03e8b52-2c1b-4192-a3b8-52dbef0f335e:opentrons/opentrons_10_tuberack_falcon_4x50ml_6x15ml_conical/3","aspirate_mix_checkbox":false,"aspirate_mix_times":"","aspirate_mix_volume":null,"aspirate_mmFromBottom":20,"aspirate_position_reference":"well-bottom","aspirate_retract_delay_seconds":"0","aspirate_retract_mmFromBottom":2,"aspirate_retract_speed":"125","aspirate_retract_x_position":0,"aspirate_retract_y_position":0,"aspirate_retract_position_reference":"well-top","aspirate_submerge_delay_seconds":"0","aspirate_submerge_speed":"125","aspirate_submerge_mmFromBottom":2,"aspirate_submerge_x_position":0,"aspirate_submerge_y_position":0,"aspirate_submerge_position_reference":"well-top","aspirate_touchTip_checkbox":false,"aspirate_touchTip_mmFromTop":null,"aspirate_touchTip_speed":60,"aspirate_touchTip_mmFromEdge":0,"aspirate_wellOrder_first":"t2b","aspirate_wellOrder_second":"l2r","aspirate_wells_grouped":false,"aspirate_wells":["A4"],"aspirate_x_position":0,"aspirate_y_position":0,"blowout_checkbox":false,"blowout_flowRate":"274.7","blowout_location":null,"blowout_mmFromBottom":null,"blowout_x_position":null,"blowout_y_position":null,"blowout_position_reference":"well-top","changeTip":"always","conditioning_checkbox":false,"conditioning_volume":null,"dispense_airGap_checkbox":false,"dispense_airGap_volume":"","dispense_delay_checkbox":false,"dispense_delay_seconds":"1","dispense_flowRate":"274.7","dispense_labware":"1941cbb2-232a-44c0-a935-a6a8c1e278bc:opentrons/corning_96_wellplate_360ul_flat/5","dispense_mix_checkbox":false,"dispense_mix_times":"","dispense_mix_volume":null,"dispense_mmFromBottom":null,"dispense_position_reference":"well-bottom","dispense_retract_delay_seconds":"0","dispense_retract_mmFromBottom":2,"dispense_retract_speed":"125","dispense_retract_x_position":0,"dispense_retract_y_position":0,"dispense_retract_position_reference":"well-top","dispense_submerge_delay_seconds":"0","dispense_submerge_speed":"125","dispense_submerge_mmFromBottom":2,"dispense_submerge_x_position":0,"dispense_submerge_y_position":0,"dispense_submerge_position_reference":"well-top","dispense_touchTip_checkbox":false,"dispense_touchTip_mmFromTop":null,"dispense_touchTip_speed":60,"dispense_touchTip_mmFromEdge":0,"dispense_wellOrder_first":"t2b","dispense_wellOrder_second":"l2r","dispense_wells":["A1","A2","A3"],"dispense_x_position":0,"dispense_y_position":0,"disposalVolume_checkbox":true,"disposalVolume_volume":null,"dropTip_location":"bb101ae0-e2ba-4920-a0ec-40fae9f0ba72:trashBin","liquidClassesSupported":true,"liquidClass":"none","nozzles":"ALL","path":"single","pipette":"b97c546a-f3f9-434b-9df6-b574e145fa31","preWetTip":false,"primaryNozzle":"A1","pushOut_checkbox":false,"pushOut_volume":"0","tipRack":"opentrons/opentrons_96_tiprack_1000ul/1","tip_tracking":"automatic","tiprack_selected":null,"tips_selected":[],"volume":"100"},"c16c21ae-4ee1-459b-81c8-8e790134340b":{"id":"c16c21ae-4ee1-459b-81c8-8e790134340b","stepType":"moveLiquid","stepName":"transfer","stepDetails":"","stepNumber":0,"aspirate_airGap_checkbox":false,"aspirate_airGap_volume":"","aspirate_delay_checkbox":false,"aspirate_delay_seconds":"1","aspirate_flowRate":"274.7","aspirate_labware":"b03e8b52-2c1b-4192-a3b8-52dbef0f335e:opentrons/opentrons_10_tuberack_falcon_4x50ml_6x15ml_conical/3","aspirate_mix_checkbox":false,"aspirate_mix_times":"","aspirate_mix_volume":null,"aspirate_mmFromBottom":20,"aspirate_position_reference":"well-bottom","aspirate_retract_delay_seconds":"0","aspirate_retract_mmFromBottom":2,"aspirate_retract_speed":"125","aspirate_retract_x_position":0,"aspirate_retract_y_position":0,"aspirate_retract_position_reference":"well-top","aspirate_submerge_delay_seconds":"0","aspirate_submerge_speed":"125","aspirate_submerge_mmFromBottom":2,"aspirate_submerge_x_position":0,"aspirate_submerge_y_position":0,"aspirate_submerge_position_reference":"well-top","aspirate_touchTip_checkbox":false,"aspirate_touchTip_mmFromTop":null,"aspirate_touchTip_speed":60,"aspirate_touchTip_mmFromEdge":0,"aspirate_wellOrder_first":"t2b","aspirate_wellOrder_second":"l2r","aspirate_wells_grouped":false,"aspirate_wells":["B3"],"aspirate_x_position":0,"aspirate_y_position":0,"blowout_checkbox":false,"blowout_flowRate":"274.7","blowout_location":null,"blowout_mmFromBottom":null,"blowout_x_position":null,"blowout_y_position":null,"blowout_position_reference":"well-top","changeTip":"always","conditioning_checkbox":false,"conditioning_volume":null,"dispense_airGap_checkbox":false,"dispense_airGap_volume":"","dispense_delay_checkbox":false,"dispense_delay_seconds":"1","dispense_flowRate":"274.7","dispense_labware":"1941cbb2-232a-44c0-a935-a6a8c1e278bc:opentrons/corning_96_wellplate_360ul_flat/5","dispense_mix_checkbox":false,"dispense_mix_times":"","dispense_mix_volume":null,"dispense_mmFromBottom":null,"dispense_position_reference":"well-bottom","dispense_retract_delay_seconds":"0","dispense_retract_mmFromBottom":2,"dispense_retract_speed":"125","dispense_retract_x_position":0,"dispense_retract_y_position":0,"dispense_retract_position_reference":"well-top","dispense_submerge_delay_seconds":"0","dispense_submerge_speed":"125","dispense_submerge_mmFromBottom":2,"dispense_submerge_x_position":0,"dispense_submerge_y_position":0,"dispense_submerge_position_reference":"well-top","dispense_touchTip_checkbox":false,"dispense_touchTip_mmFromTop":null,"dispense_touchTip_speed":60,"dispense_touchTip_mmFromEdge":0,"dispense_wellOrder_first":"t2b","dispense_wellOrder_second":"l2r","dispense_wells":["A1","A2","A3"],"dispense_x_position":0,"dispense_y_position":0,"disposalVolume_checkbox":true,"disposalVolume_volume":null,"dropTip_location":"bb101ae0-e2ba-4920-a0ec-40fae9f0ba72:trashBin","liquidClassesSupported":true,"liquidClass":"none","nozzles":"ALL","path":"single","pipette":"b97c546a-f3f9-434b-9df6-b574e145fa31","preWetTip":false,"primaryNozzle":"A1","pushOut_checkbox":false,"pushOut_volume":"0","tipRack":"opentrons/opentrons_96_tiprack_1000ul/1","tip_tracking":"automatic","tiprack_selected":null,"tips_selected":[],"volume":"110"}},"orderedStepIds":["a9c2a94c-fc59-4811-855d-77caa4db1e84","ee655c6b-57a5-426b-9995-235befadb60f","c16c21ae-4ee1-459b-81c8-8e790134340b"],"pipettes":{"b97c546a-f3f9-434b-9df6-b574e145fa31":{"pipetteName":"p1000_single_gen2"},"9edc7c08-d05a-4ed4-84e9-5e09ef789181":{"pipetteName":"p300_multi_gen2"}},"modules":{"6b4fbab6-ff7d-4b28-9a9b-50d197f2dcbf:heaterShakerModuleType":{"model":"heaterShakerModuleV1"}},"labware":{"a865b740-1a0d-43de-9e8a-811965071376:opentrons/opentrons_96_tiprack_1000ul/1":{"displayName":"Opentrons OT-2 96 Tip Rack 1000 µL","labwareDefURI":"opentrons/opentrons_96_tiprack_1000ul/1"},"e4ff6ac7-c65f-4c1f-90aa-5fc624b4b0e6:opentrons/opentrons_96_tiprack_300ul/1":{"displayName":"Opentrons OT-2 96 Tip Rack 300 µL","labwareDefURI":"opentrons/opentrons_96_tiprack_300ul/1"},"b03e8b52-2c1b-4192-a3b8-52dbef0f335e:opentrons/opentrons_10_tuberack_falcon_4x50ml_6x15ml_conical/3":{"displayName":"Opentrons 10 Tube Rack with Falcon 4x50 mL, 6x15 mL Conical","labwareDefURI":"opentrons/opentrons_10_tuberack_falcon_4x50ml_6x15ml_conical/3"},"1941cbb2-232a-44c0-a935-a6a8c1e278bc:opentrons/corning_96_wellplate_360ul_flat/5":{"displayName":"Corning 96 Well Plate 360 µL Flat","labwareDefURI":"opentrons/corning_96_wellplate_360ul_flat/5"}}}},"metadata":{"protocolName":"Hackathon Demo","author":"JS","description":"Colour mixing in a row of a 96WP","source":"Protocol Designer","created":1791190475665,"lastModified":1791190836508}}"""

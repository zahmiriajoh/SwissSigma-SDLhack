"""Write fake plate-reader spectra for round 1 of the OT protocols example: 3 identical plates, a solvent-only blank
plate, and a QC plate (blanks + calibration series) with its map, robot CSV and plate log."""
import sys
from pathlib import Path

import numpy as np

from fake_plate_reader import plate_log, qc_export, read_plate_map, spectra_export

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1]))
from analysis.qc_layout import write_qc_layout  # noqa: E402
from production.config import FIRST_PLATE, FIRST_ROUND, N_PLATES  # noqa: E402

R = FIRST_ROUND
PLATE_MAP = HERE / f"../../OT protocols/examples/plate_map_round{R}.csv"
PLATES = range(FIRST_PLATE, FIRST_PLATE + N_PLATES)

if __name__ == "__main__":
    rng = np.random.default_rng(0)
    plate_map = read_plate_map(PLATE_MAP)
    for i in PLATES:
        spectra_export(plate_map, rng).to_csv(HERE / f"reader_round{R}_plate{i}.csv", index=False)
    spectra_export(plate_map, rng, solids=False).to_csv(HERE / f"reader_round{R}_blank.csv", index=False)
    qc_map = write_qc_layout(plate_map, HERE)
    qc_export(qc_map, rng).to_csv(HERE / f"reader_round{R}_qc.csv", index=False)
    plate_log([*PLATES, "qc"], rng).to_csv(HERE / f"plate_log_round{R}.csv", index=False)
    print(f"wrote {N_PLATES} plates + blank + QC plate for {len(plate_map)} wells to {HERE}")

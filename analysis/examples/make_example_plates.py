"""Write fake plate-reader spectra for round 0 of the OT protocols example: 3 identical plates, the pure-solvent blank wells
(--solvent-blanks), a full solvent-only blank plate (the optional --blank route) and a plate log."""
import sys
from pathlib import Path

import numpy as np

from fake_plate_reader import plate_log, read_plate_map, solvent_blank_export, spectra_export, write_plate_reader_csv

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1]))
from production.config import FIRST_PLATE, FIRST_ROUND, N_PLATES  # noqa: E402

R = FIRST_ROUND
PLATE_MAP = HERE / f"../../OT protocols/examples/plate_map_round{R}.csv"
PLATES = range(FIRST_PLATE, FIRST_PLATE + N_PLATES)

if __name__ == "__main__":
    rng = np.random.default_rng(0)
    plate_map = read_plate_map(PLATE_MAP)
    for i in PLATES:
        write_plate_reader_csv(spectra_export(plate_map, rng), HERE / f"reader_round{R}_plate{i}.csv")
    write_plate_reader_csv(spectra_export(plate_map, rng, solids=False), HERE / f"reader_round{R}_blank.csv")
    write_plate_reader_csv(solvent_blank_export(rng), HERE / f"reader_round{R}_solvents.csv")
    plate_log(list(PLATES), rng).to_csv(HERE / f"plate_log_round{R}.csv", index=False)
    print(f"wrote {N_PLATES} plates + blank for {len(plate_map)} wells to {HERE}")

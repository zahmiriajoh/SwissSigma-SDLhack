#!/usr/bin/env bash
# Run the BO step for the production campaign and write the next round's robot files.
#
#   production/run_bo.sh CSV_DIR [--seed N] [--no-figures]
#
# CSV_DIR is the folder exchanged with the lab (production/README.md, "Folder structure"):
#   CSV_DIR/ratios/   robot inputs we write:  suggestions_roundN.csv, ot_input_roundN.csv, plate_map_roundN.csv,
#                                            qc_plate_map_roundN.csv, ot_input_roundN_qc.csv
#   CSV_DIR/uvvis/    results the lab uploads: reader_roundN_plate0.csv, reader_roundN_plate1.csv, reader_roundN_plate2.csv,
#                                            reader_roundN_qc.csv, plate_log_roundN.csv (optional)
#   CSV_DIR/          what the analysis derives: endpoint_roundN_*.csv, wavelengths_roundN.csv, results_roundN_wells.csv,
#                                            bo_dataset.csv, bo_dataset_shared.csv, figures/
#
# What happens depends on what is there:
#   nothing yet                      -> round 0 seed design (SDL_BO init) and its robot files into ratios/
#   ratios for round N, no uvvis     -> stops and lists the reader files it is waiting for
#   uvvis for round N present        -> analysis reduce -> bo_bridge merge -> SDL_BO suggest -> bo_bridge layout
#                                       -> analysis qc-layout for round N+1 into ratios/, then analysis qc + report into figures/
#   ratios for N+1 already written   -> nothing to do (re-run after the lab uploads round N+1)
# Every step refuses to overwrite a finished round, so the script can be re-run safely.
set -euo pipefail
trap 'echo "run_bo.sh: failed at line $LINENO (see the message above)" >&2' ERR

usage() { sed -n '2,20p' "$0"; exit "${1:-0}"; }
[[ $# -ge 1 ]] || usage 1
CSV_DIR=$(realpath "$1"); shift
SEED=0; FIGURES=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed) SEED="$2"; shift 2 ;;
    --no-figures) FIGURES=0; shift ;;
    -h|--help) usage ;;
    *) echo "unknown option $1"; usage 1 ;;
  esac
done

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
RATIOS="$CSV_DIR/ratios"; UVVIS="$CSV_DIR/uvvis"; FIG="$CSV_DIR/figures"
mkdir -p "$RATIOS" "$UVVIS"
cd "$REPO"

# The sdlhack environment: use it if it is not already active.
if ! python -c "import SDL_BO, analysis, production.config" 2>/dev/null; then
  if command -v mamba >/dev/null; then eval "$(mamba shell hook --shell bash 2>/dev/null || conda shell.bash hook)"; mamba activate sdlhack
  elif command -v conda >/dev/null; then eval "$(conda shell.bash hook)"; conda activate sdlhack
  fi
  python -c "import SDL_BO, analysis, production.config" || { echo "activate the sdlhack environment first (mamba env create -f environment.yml)"; exit 1; }
fi

BRIDGE="$REPO/OT protocols/bo_bridge.py"
read -r FIRST_ROUND N_PLATES FIRST_PLATE < <(python -c "from production.config import FIRST_ROUND, N_PLATES, FIRST_PLATE; print(FIRST_ROUND, N_PLATES, FIRST_PLATE)")

# ----- helpers -------------------------------------------------------------------------------------------------
latest_round() {  # highest N with ratios/plate_map_roundN.csv, or empty
  local best="" f n
  for f in "$RATIOS"/plate_map_round*.csv; do
    [[ -e "$f" ]] || continue
    n=${f##*plate_map_round}; n=${n%.csv}
    [[ -z "$best" || $n -gt $best ]] && best=$n
  done
  echo "$best"
}
reader_files() {  # the uvvis files round $1 needs
  local r=$1 p
  for ((p = FIRST_PLATE; p < FIRST_PLATE + N_PLATES; p++)); do echo "$UVVIS/reader_round${r}_plate${p}.csv"; done
  echo "$UVVIS/reader_round${r}_qc.csv"
}
layout_round() {  # suggestions -> robot CSV + plate map + QC plate for round $1
  local r=$1
  python "$BRIDGE" layout --round "$r" --suggestions "$RATIOS/suggestions_round${r}.csv" --outdir "$RATIOS"
  python -m analysis qc-layout --plate-map "$RATIOS/plate_map_round${r}.csv" --outdir "$RATIOS"
  echo
  echo "Round $r is ready for the lab. Upload to the Opentrons app:"
  echo "  $RATIOS/ot_input_round${r}.csv      (3 identical sample plates)"
  echo "  $RATIOS/ot_input_round${r}_qc.csv   (1 QC plate: solvent blanks + calibration series; weigh loading x nominal mass)"
  echo "Then ask the lab to save the plate-reader exports as:"
  reader_files "$r" | sed 's/^/  /'
  echo "  $UVVIS/plate_log_round${r}.csv      (optional: plate,read_delay_min for plates $FIRST_PLATE-$((FIRST_PLATE + N_PLATES - 1)) and qc)"
}

# ----- round 0: seed design ------------------------------------------------------------------------------------
N=$(latest_round)
if [[ -z "$N" ]]; then
  echo "No round laid out yet: writing the round $FIRST_ROUND seed design."
  python -m SDL_BO init --out "$RATIOS/suggestions_round${FIRST_ROUND}.csv"
  layout_round "$FIRST_ROUND"
  exit 0
fi

# ----- round N measured? ---------------------------------------------------------------------------------------
missing=()
while IFS= read -r f; do [[ -f "$f" ]] || missing+=("$f"); done < <(reader_files "$N")
if [[ ${#missing[@]} -gt 0 ]]; then
  echo "Round $N is laid out in $RATIOS but these plate-reader exports are not in $UVVIS yet:"
  printf '  %s\n' "${missing[@]}"
  echo "Nothing to do until the lab uploads them."
  exit 2
fi

NEXT=$((N + 1))
if [[ -f "$RATIOS/plate_map_round${NEXT}.csv" ]]; then
  echo "Round $NEXT is already laid out in $RATIOS; waiting for its uvvis exports. Nothing to do."
  exit 0
fi

# ----- analysis + merge for round N (skipped if already done) --------------------------------------------------
readers=(); for ((p = FIRST_PLATE; p < FIRST_PLATE + N_PLATES; p++)); do readers+=("$UVVIS/reader_round${N}_plate${p}.csv"); done
endpoints=(); for ((p = FIRST_PLATE; p < FIRST_PLATE + N_PLATES; p++)); do endpoints+=("$CSV_DIR/endpoint_round${N}_plate${p}.csv"); done
if [[ ! -f "$CSV_DIR/results_round${N}_wells.csv" ]]; then
  echo "== Round $N: spectra -> one absorbance per well (analysis reduce)"
  python -m analysis reduce --plate-map "$RATIOS/plate_map_round${N}.csv" --reader "${readers[@]}" \
    --qc-reader "$UVVIS/reader_round${N}_qc.csv" --qc-map "$RATIOS/qc_plate_map_round${N}.csv" --outdir "$CSV_DIR" --plots
  echo "== Round $N: merge into bo_dataset.csv (bo_bridge merge)"
  python "$BRIDGE" merge --plate-map "$RATIOS/plate_map_round${N}.csv" --reader "${endpoints[@]}" \
    --blank "$CSV_DIR/endpoint_round${N}_blank.csv" --dataset "$CSV_DIR/bo_dataset.csv" --wells-out "$CSV_DIR/results_round${N}_wells.csv"
else
  echo "== Round $N already merged (results_round${N}_wells.csv exists)"
fi

# ----- BO: next round ------------------------------------------------------------------------------------------
echo "== Round $NEXT: Bayesian optimisation (SDL_BO suggest)"
python -m SDL_BO suggest --dataset "$CSV_DIR/bo_dataset.csv" --out "$RATIOS/suggestions_round${NEXT}.csv" --seed "$SEED"
python -m SDL_BO report --dataset "$CSV_DIR/bo_dataset.csv"
layout_round "$NEXT"

# ----- figures so far --------------------------------------------------------------------------------------------
if [[ $FIGURES -eq 1 ]]; then
  echo
  echo "== QC and report figures for rounds $FIRST_ROUND-$N -> $FIG"
  python -m analysis qc --run "$CSV_DIR" --outdir "$FIG"
  python -m analysis report --run "$CSV_DIR" --outdir "$FIG"
fi

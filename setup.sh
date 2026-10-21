#!/usr/bin/env bash
# Set up this repository on a fresh computer:  bash setup.sh
#
# 1. works out the operating system (macOS, Linux, or Windows under Git Bash / WSL)
# 2. installs uv (https://docs.astral.sh/uv/), a Python package manager, if it is not there yet
# 3. creates the project's Python environment in .venv/ from pyproject.toml + uv.lock (uv downloads Python 3.12 itself)
# 4. checks that everything runs: imports, the analysis and BO command lines, and one fake round of the whole pipeline
#
# Afterwards every command in the READMEs is run as  uv run <command>, e.g.  uv run pytest tests/
# Options:  --full   also run the complete test suite at the end (about a minute)
set -euo pipefail

FULL=0
for arg in "$@"; do
  case "$arg" in
    --full) FULL=1 ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg (try --help)"; exit 1 ;;
  esac
done

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$REPO"

say()  { printf '\n==> %s\n' "$*"; }
ok()   { printf '    OK   %s\n' "$*"; }
fail() { printf '\n    FAIL %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------------------------------------------
say "1/4  Operating system"
case "$(uname -s)" in
  Darwin*)                 OS=macos ;;
  Linux*)                  OS=linux; grep -qi microsoft /proc/version 2>/dev/null && OS="linux (WSL)" ;;
  MINGW*|MSYS*|CYGWIN*)    OS=windows ;;
  *) fail "unrecognised operating system: $(uname -s). Use macOS, Linux, Windows Git Bash or WSL." ;;
esac
ok "$OS, $(uname -m)"

# ---------------------------------------------------------------------------------------------------------------
say "2/4  uv (Python package manager)"
UV_BIN="$HOME/.local/bin"
[[ "$OS" == windows ]] && UV_BIN="$(cygpath -u "${USERPROFILE:-$HOME}")/.local/bin"
export PATH="$UV_BIN:$PATH"
if command -v uv >/dev/null 2>&1; then
  ok "already installed: $(uv --version)"
else
  echo "    installing uv into $UV_BIN ..."
  if [[ "$OS" == windows ]]; then
    powershell.exe -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex" \
      || fail "could not install uv. Open PowerShell and run:  irm https://astral.sh/uv/install.ps1 | iex"
  else
    command -v curl >/dev/null 2>&1 || fail "curl is needed to download uv (install it with your package manager, e.g. 'sudo apt install curl')"
    curl -LsSf https://astral.sh/uv/install.sh | sh -s -- --quiet \
      || fail "could not install uv. See https://docs.astral.sh/uv/getting-started/installation/"
  fi
  hash -r
  command -v uv >/dev/null 2>&1 || fail "uv was installed but is not on the PATH yet. Close this terminal, open a new one and run  bash setup.sh  again."
  ok "installed $(uv --version)"
fi

# ---------------------------------------------------------------------------------------------------------------
say "3/4  Python environment (.venv/ from pyproject.toml and uv.lock)"
LOCK=(); [[ -f uv.lock ]] && LOCK=(--locked)  # identical versions for everyone once uv.lock is committed
uv sync "${LOCK[@]}" --quiet || fail "uv could not build the environment. Are you online? Re-run  bash setup.sh  to retry."
ok "$(uv run python --version) with $(uv run python -c 'import opentrons, numpy, pandas, sklearn; print(f"opentrons {opentrons.__version__}, numpy {numpy.__version__}, pandas {pandas.__version__}, scikit-learn {sklearn.__version__}")')"

# ---------------------------------------------------------------------------------------------------------------
say "4/4  Checks"
uv run python -c "import SDL_BO, analysis, production.config; from production.config import SOLUTES; print('    OK   imports; solutes:', ', '.join(SOLUTES))" \
  || fail "the repo's own packages do not import"
uv run python -m analysis --help >/dev/null && uv run python -m SDL_BO --help >/dev/null && uv run python "OT protocols/bo_bridge.py" --help >/dev/null \
  || fail "a command line does not start"
ok "command lines: analysis, SDL_BO, bo_bridge"

TMP=$(mktemp -d 2>/dev/null || mktemp -d -t sdlcheck)
trap 'rm -rf "$TMP"' EXIT
echo "    running one fake round of the whole pipeline (bo_bridge -> fake plate reader -> analysis -> merge) ..."
uv run python analysis/examples/make_toy_run.py --outdir "$TMP/toy" --rounds 1 >"$TMP/toy.log" 2>&1 \
  || { cat "$TMP/toy.log"; fail "the fake round did not run"; }
uv run python -m SDL_BO report --dataset "$TMP/toy/bo_dataset.csv" >"$TMP/report.log" 2>&1 \
  || { cat "$TMP/report.log"; fail "SDL_BO could not read the fake round"; }
[[ -f "$TMP/toy/wavelengths_round0.csv" && -f "$TMP/toy/bo_dataset.csv" ]] || fail "expected output files are missing"
ok "fake round: plate map, spectra, endpoints, bo_dataset.csv and the BO report"

if [[ $FULL -eq 1 ]]; then
  echo "    running the full test suite ..."
  uv run pytest tests/ -q || fail "tests failed"
  ok "test suite"
fi

# ---------------------------------------------------------------------------------------------------------------
cat <<EOF

All good. The repository is ready. Run commands through uv, from this folder:

    bash production/run_bo.sh production/csvs              # one BO round from the lab's csvs/ folder
    uv run python -m analysis --help            # plate-reader analysis
    uv run python -m SDL_BO --help              # Bayesian optimisation
    uv run pytest tests/                        # all tests

If 'uv' is not found in a new terminal, add it to your PATH (the installer printed how) or run  bash setup.sh  again.
EOF

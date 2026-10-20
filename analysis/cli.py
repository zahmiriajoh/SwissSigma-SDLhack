"""Command line interface:  python -m analysis <command> [options]

    reduce     reader exports + plate map -> one single-value export per plate for `bo_bridge.py merge`
    qc-layout  plate map -> QC plate (blanks + calibration series) map and robot CSV
    qc         campaign folder -> experiment-quality figures and qc_summary.md
    report     campaign folder -> study-aim figures and report_summary.md
"""
import argparse
from pathlib import Path

from production.config import FIRST_PLATE

from .qc_layout import LOADINGS
from .spectra import (ABS_MAX_DEFAULT, BLANK_MAX_DEFAULT, DEFAULT_NM_RANGE, MIN_SIGNAL_SIGMAS, SpectraError, pure_blanks,
                      read_plate_map, read_spectra, reduce_round, synthetic_blank)


def _parse_overrides(items):
    """['S1=275', 'S2=320'] -> {'S1': 275.0, 'S2': 320.0}."""
    out = {}
    for item in items or []:
        try:
            solute, nm = item.split("=")
            out[solute.strip()] = float(nm)
        except ValueError:
            raise SpectraError(f"--wavelength expects SOLUTE=NM, got '{item}'") from None
    return out


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="analysis", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    reduce = commands.add_parser("reduce", help="spectra -> per-plate endpoint CSVs")
    reduce.add_argument("--plate-map", required=True, help="plate_map_roundN.csv from bo_bridge.py layout")
    reduce.add_argument("--reader", required=True, nargs="+", help="one full-spectrum export per plate, in plate order")
    reduce.add_argument("--blank", help="reader export of a solvent-only copy of the sample plate (same layout, no solids)")
    reduce.add_argument("--qc-reader", help="reader export of the QC plate (qc-layout); its pure-solvent blanks replace --blank")
    reduce.add_argument("--qc-map", help="qc_plate_map_roundN.csv matching --qc-reader")
    reduce.add_argument("--outdir", help="where to write (default: next to the plate map)")
    reduce.add_argument("--wavelength", nargs="*", metavar="SOLUTE=NM",
                        help="fix a solute's wavelength instead of picking it from its DMF control")
    reduce.add_argument("--nm-range", nargs=2, type=float, default=DEFAULT_NM_RANGE, metavar=("MIN", "MAX"),
                        help="search peaks only in this range (default %(default)s)")
    reduce.add_argument("--bandwidth", type=float, default=0.0,
                        help="average absorbance over +/- this many nm around the wavelength (default 0)")
    reduce.add_argument("--blank-max", type=float, default=BLANK_MAX_DEFAULT,
                        help="read only where every solvent blank is below this absorbance (default %(default)s)")
    reduce.add_argument("--abs-max", type=float, default=ABS_MAX_DEFAULT, help="flag wells whose raw absorbance exceeds this")
    reduce.add_argument("--plots", action="store_true", help="also write QC figures (spectra, plate heat maps)")

    layout = commands.add_parser("qc-layout", help="QC plate map + robot CSV for a round (blanks and calibration series)")
    layout.add_argument("--plate-map", required=True, help="plate_map_roundN.csv of the round (gives solutes, solvents, volume)")
    layout.add_argument("--outdir", help="default: next to the plate map")
    layout.add_argument("--loadings", nargs="+", type=float, default=list(LOADINGS), help="calibration loadings as fractions of the nominal mass")

    qc = commands.add_parser("qc", help="experiment-quality figures and qc_summary.md for a campaign folder")
    qc.add_argument("--run", required=True, help="folder with plate_map_roundN.csv, results_roundN_wells.csv, bo_dataset.csv, ...")
    qc.add_argument("--outdir", help="where figures and qc_summary.md go (default <run>/figures)")
    qc.add_argument("--abs-max", type=float, default=ABS_MAX_DEFAULT, help="reader linear range: flag raw absorbance above this")

    report = commands.add_parser("report", help="study-aim figures and report_summary.md for a campaign folder")
    report.add_argument("--run", required=True, help="campaign folder (see qc)")
    report.add_argument("--outdir", help="default <run>/figures")
    report.add_argument("--no-gp", action="store_true", help="skip the SDL_BO Gaussian-process posterior plots")
    report.add_argument("--seed", type=int, default=0, help="seed for the GP fits")
    return parser


def _run_report(args) -> None:
    from .report import run_report
    from .run import Run
    run = Run(args.run)
    path = run_report(run, Path(args.outdir or Path(args.run) / "figures"), not args.no_gp, args.seed)
    print(f"wrote {path} and figures to {path.parent}")


def _run_qc_layout(args) -> None:
    from .qc_layout import write_qc_layout
    outdir = Path(args.outdir or Path(args.plate_map).parent)
    qc = write_qc_layout(read_plate_map(args.plate_map), outdir, tuple(args.loadings))
    r = int(qc["round"].iloc[0])
    counts = qc["role"].value_counts()
    print(f"wrote qc_plate_map_round{r}.csv, ot_input_round{r}_qc.csv -> {outdir}: "
          f"{counts.get('calibration', 0)} calibration + {counts.get('blank', 0)} blank wells")


def _run_qc(args) -> None:
    from .qc import run_qc  # pandas/matplotlib only when asked for
    from .run import Run
    run = Run(args.run)
    path = run_qc(run, Path(args.outdir or Path(args.run) / "figures"), args.abs_max)
    print(f"wrote {path} and figures to {path.parent}")


def _run_reduce(args) -> None:
    plate_map = read_plate_map(args.plate_map)
    plates = [read_spectra(p) for p in args.reader]
    blank = read_spectra(args.blank) if args.blank else None
    pure = None
    if args.qc_reader:
        if not args.qc_map:
            raise SpectraError("--qc-reader needs --qc-map")
        import pandas as pd
        qc_spectra, qc_map = read_spectra(args.qc_reader), pd.read_csv(args.qc_map, index_col="well")
        blank, pure = synthetic_blank(qc_spectra, qc_map, plate_map), pure_blanks(qc_spectra, qc_map)
    wavelengths, endpoints, corrected, report = reduce_round(
        plate_map, plates, blank, _parse_overrides(args.wavelength), tuple(args.nm_range), args.bandwidth,
        args.blank_max, args.abs_max, pure)

    round_ = plate_map["round"].iloc[0]
    outdir = Path(args.outdir or Path(args.plate_map).parent)
    outdir.mkdir(parents=True, exist_ok=True)
    plate_numbers = range(FIRST_PLATE, FIRST_PLATE + len(plates))
    names = [f"endpoint_round{round_}_plate{i}.csv" for i in plate_numbers]
    if blank is not None:
        names.append(f"endpoint_round{round_}_blank.csv")
    for name, ep in zip(names, endpoints):
        ep.to_csv(outdir / name, index=False)
    report.round(3).to_csv(outdir / f"wavelengths_round{round_}.csv")

    print("Wavelength per solute:")
    for solute, r in report.iterrows():
        where = "band maximum" if r["at_band_max"] else f"shoulder, band maximum at {r['band_max_nm']:.0f} nm, {r['signal_fraction']:.0%} of its signal left"
        verdict = "" if r["measurable"] else f" -> NOT MEASURABLE: control signal {r['control_signal']:.3f} is below {MIN_SIGNAL_SIGMAS:g} x noise {r['noise']:.3f}"
        print(f"  {solute:<20} {r['wavelength_nm']:.0f} nm ({where}; usable window {r['window_min_nm']:.0f}-{r['window_max_nm']:.0f} nm){verdict}")
    flagged = sum((ep["flag"] != "").sum() for ep in endpoints[:len(plates)])
    if flagged:
        print(f"  {flagged} sample well reading(s) flagged saturated/opaque (see the flag column of the endpoint files)")
    if blank is None:
        print("  note: no --blank or --qc-reader, so peaks were picked on raw spectra (solvent baseline included)")
    elif args.qc_reader:
        print("  blank per sample well = volume-weighted pure-solvent blanks from the QC plate")
    print("wrote " + ", ".join(names) + f", wavelengths_round{round_}.csv -> {outdir}")
    if args.plots:
        from .plots import plot_plates, plot_spectra  # matplotlib only when asked for
        plot_spectra(corrected, plate_map, wavelengths, outdir / f"spectra_round{round_}.png", tuple(args.nm_range))
        labels = [f"Plate {i}" for i in plate_numbers] + (["Blank"] if blank is not None else [])
        plot_plates(endpoints, plate_map, outdir / f"plates_round{round_}.png", labels)
        print(f"wrote spectra_round{round_}.png, plates_round{round_}.png -> {outdir}")
    print(f"\nNext: python \"OT protocols/bo_bridge.py\" merge --plate-map {args.plate_map} "
          f"--reader {' '.join(str(outdir / n) for n in names[:len(plates)])}"
          + (f" --blank {outdir / names[-1]}" if blank is not None else "") + " --dataset bo_dataset.csv")


COMMANDS = {"reduce": _run_reduce, "qc-layout": _run_qc_layout, "qc": _run_qc, "report": _run_report}


def main(argv=None) -> None:
    args = _build_parser().parse_args(argv)
    try:
        COMMANDS[args.command](args)
    except (SpectraError, FileNotFoundError) as error:
        raise SystemExit(f"error: {error}") from None  # a one-line message, not a traceback

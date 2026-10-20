"""Tiny markdown writer for the qc / report summaries (no tabulate dependency)."""
import pandas as pd


def md_table(df: pd.DataFrame, floatfmt=".3f") -> str:
    """A DataFrame as a GitHub markdown table; floats formatted, index dropped."""
    def cell(v):
        if isinstance(v, float):
            return "" if pd.isna(v) else format(v, floatfmt)
        return str(v)
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


class Summary:
    """Collects sections (title, lines, tables) and writes one markdown file."""

    def __init__(self, title):
        self.parts = [f"# {title}\n"]

    def section(self, title, notes=(), table=None, figures=()):
        self.parts.append(f"## {title}\n")
        self.parts += [f"- {n}" for n in notes]
        if table is not None and len(table):
            self.parts.append("\n" + md_table(table) + "\n")
        self.parts += [f"Figure: `{f.name}`" for f in figures]
        self.parts.append("")

    def write(self, path):
        path.write_text("\n".join(self.parts))
        return path

#!/usr/bin/env python3
import argparse
import re
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

ENV_LINE_RE = re.compile(r"^(export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def load_env(path):
    entries = OrderedDict()
    for line in Path(path).read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = ENV_LINE_RE.match(line)
        if not match:
            continue
        key, value = match.group(2), match.group(3).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        entries[key] = value
    return entries


def md_cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def main():
    parser = argparse.ArgumentParser(
        description="Compara dos archivos .env key a key y genera un reporte Markdown"
    )
    parser.add_argument("--github", default="github.env")
    parser.add_argument("--gitlab", default="gitlab.env")
    parser.add_argument("--output", default="comparacion-env.md")
    args = parser.parse_args()

    github = load_env(args.github)
    gitlab = load_env(args.gitlab)

    iguales, diferentes, solo_github, solo_gitlab = [], [], [], []
    for key, value in github.items():
        if key not in gitlab:
            solo_github.append((key, value))
        elif gitlab[key] == value:
            iguales.append((key, value))
        else:
            diferentes.append((key, value, gitlab[key]))
    for key, value in gitlab.items():
        if key not in github:
            solo_gitlab.append((key, value))

    vacias = [(key, "github.env") for key, v in github.items() if v == ""]
    vacias += [(key, "gitlab.env") for key, v in gitlab.items() if v == ""]

    lines = [
        "# Comparación de variables de ambiente",
        "",
        f"Directorio: `{Path.cwd()}`  ",
        f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Resumen",
        "",
        "| Categoría | Cantidad |",
        "|---|---|",
        f"| Iguales | {len(iguales)} |",
        f"| Diferentes | {len(diferentes)} |",
        f"| Solo en github.env | {len(solo_github)} |",
        f"| Solo en gitlab.env | {len(solo_gitlab)} |",
        f"| Con valor vacío | {len(vacias)} |",
    ]

    if diferentes:
        lines += ["", "## Diferentes", "", "| Variable | github.env | gitlab.env |", "|---|---|---|"]
        lines += [f"| `{k}` | {md_cell(g)} | {md_cell(l)} |" for k, g, l in diferentes]

    if solo_github:
        lines += ["", "## Solo en github.env", "", "| Variable | Valor |", "|---|---|"]
        lines += [f"| `{k}` | {md_cell(v)} |" for k, v in solo_github]

    if solo_gitlab:
        lines += ["", "## Solo en gitlab.env", "", "| Variable | Valor |", "|---|---|"]
        lines += [f"| `{k}` | {md_cell(v)} |" for k, v in solo_gitlab]

    if vacias:
        lines += ["", "## Con valor vacío", "", "| Variable | Archivo |", "|---|---|"]
        lines += [f"| `{k}` | {src} |" for k, src in vacias]

    lines += ["", "## Iguales", "", "| Variable | Valor |", "|---|---|"]
    lines += [f"| `{k}` | {md_cell(v)} |" for k, v in iguales]

    Path(args.output).write_text("\n".join(lines) + "\n")
    print(
        f"Generado {Path(args.output).resolve()}: "
        f"{len(iguales)} iguales, {len(diferentes)} diferentes, "
        f"{len(solo_github)} solo github, {len(solo_gitlab)} solo gitlab"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

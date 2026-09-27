#!/usr/bin/env python3
import argparse
import sys
from collections import OrderedDict
from pathlib import Path

import yaml


def collect(entries, into):
    if not isinstance(entries, list):
        return
    for entry in entries:
        if not isinstance(entry, dict) or "name" not in entry:
            continue
        name = str(entry["name"]).strip()
        value = entry.get("value", "")
        into[name] = "" if value is None else str(value)


def main():
    parser = argparse.ArgumentParser(
        description="Convierte un YAML de variables (name/value) a formato .env"
    )
    parser.add_argument("yaml_file", help="Archivo YAML de entrada")
    parser.add_argument(
        "-e",
        "--env",
        help="Ambiente dentro de variables.custom a incluir (ej: tope-qa). "
        "Si hay un solo ambiente se usa automáticamente; si hay varios, "
        "es obligatorio indicar cuál",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=".env",
        help="Archivo de salida (default: .env en el directorio actual)",
    )
    args = parser.parse_args()

    data = yaml.safe_load(Path(args.yaml_file).read_text()) or {}
    variables = data.get("variables", {})
    if not isinstance(variables, dict):
        raise ValueError("El YAML debe tener una sección 'variables'")

    entries = OrderedDict()
    collect(variables.get("globales"), entries)

    custom = variables.get("custom", {}) or {}
    env_name = args.env
    if env_name is None and len(custom) == 1:
        env_name = next(iter(custom))
    if env_name is not None:
        if env_name not in custom:
            available = ", ".join(sorted(custom)) or "(ninguno)"
            raise ValueError(
                f"Ambiente '{env_name}' no existe en variables.custom. "
                f"Disponibles: {available}"
            )
        collect(custom[env_name], entries)
    elif len(custom) > 1:
        available = ", ".join(sorted(custom))
        raise ValueError(
            f"El YAML tiene varios ambientes en variables.custom ({available}). "
            "Indica uno con --env"
        )

    output_path = Path(args.output)
    lines = [f"{name}={value}" for name, value in entries.items()]
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""))
    print(f"Generado {output_path.resolve()} con {len(entries)} variables")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

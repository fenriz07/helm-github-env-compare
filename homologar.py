#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path

UTILS = Path(__file__).resolve().parent
REQUIRED = ["deployment.yaml", "values.yaml", "github.deploy.vars.yaml"]


def run(cmd, cwd):
    print("+", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def main():
    parser = argparse.ArgumentParser(
        description="Genera gitlab.env y github.env en un directorio de servicio "
        "y compara ambos archivos generando comparacion-env.md"
    )
    parser.add_argument(
        "--dir",
        default=".",
        help="Directorio del servicio (default: directorio actual)",
    )
    parser.add_argument(
        "-e",
        "--env",
        default="prod-tope123",
        help="Ambiente de variables.custom a incluir en github.env "
        "(default: prod-tope123)",
    )
    args = parser.parse_args()

    workdir = Path(args.dir).resolve()
    missing = [name for name in REQUIRED if not (workdir / name).is_file()]
    if missing:
        raise FileNotFoundError(
            f"Faltan archivos en {workdir}: {', '.join(missing)}"
        )

    run(
        [
            sys.executable,
            UTILS / "generate_env_from_helm.py",
            "--deployment",
            "deployment.yaml",
            "-f",
            "values.yaml",
            "--output",
            "gitlab.env",
        ],
        workdir,
    )

    github_cmd = [
        sys.executable,
        UTILS / "yaml_vars_to_env.py",
        "github.deploy.vars.yaml",
        "-o",
        "github.env",
    ]
    if args.env:
        github_cmd += ["--env", args.env]
    run(github_cmd, workdir)

    run(
        [
            sys.executable,
            UTILS / "compare_env.py",
            "--github",
            "github.env",
            "--gitlab",
            "gitlab.env",
            "--output",
            "comparacion-env.md",
        ],
        workdir,
    )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"error: falló el paso {' '.join(str(c) for c in exc.cmd)}", file=sys.stderr)
        sys.exit(exc.returncode or 1)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

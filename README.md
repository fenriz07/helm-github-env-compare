# helm-github-env-compare

CLI tools to extract environment variables from Helm Kubernetes deployments and GitHub Actions variable YAMLs, then compare them to generate `.env` files and Markdown reports.

## What it does

This repo contains small Python utilities that help reconcile environment variables between two sources:

1. **Helm Kubernetes deployments** (`deployment.yaml` + `values.yaml`)  
   Renders the `env:` block of a deployment template into a flat `gitlab.env` file.

2. **GitHub Actions variable files** (`github.deploy.vars.yaml`)  
   Converts a YAML file with `variables.globales` and per-environment `variables.custom` into a flat `github.env` file.

3. **Comparison report**  
   Compares both `.env` files key-by-key and writes a Markdown report (`comparacion-env.md`) showing equal, different, missing, and empty values.

## Files

| File | Purpose |
|------|---------|
| `generate_env_from_helm.py` | Renders a Helm `deployment.yaml` template and extracts its `env:` block into a `.env` file. |
| `yaml_vars_to_env.py` | Converts GitHub Actions variable YAML (`name`/`value` pairs) into a `.env` file. |
| `compare_env.py` | Compares two `.env` files and outputs a Markdown diff report. |
| `homologar.py` | Runs the full pipeline: `gitlab.env` → `github.env` → `comparacion-env.md`. |
| `Makefile` | Convenience targets for each step. |

## Requirements

- Python 3.8+
- PyYAML

Install the dependency:

```bash
pip install pyyaml
```

## Usage

### 1. Generate `gitlab.env` from a Helm deployment

```bash
python generate_env_from_helm.py \
  --deployment deployment.yaml \
  -f values.yaml \
  --output gitlab.env
```

You can pass multiple values files:

```bash
python generate_env_from_helm.py \
  --deployment deployment.yaml \
  -f values/common.yaml \
  -f values/prod.yaml \
  --output gitlab.env
```

Options:

- `--deployment`: path to the Helm deployment template (default: `deployment.yaml`)
- `-f / --values`: one or more `values.yaml` files (later files override earlier ones)
- `--output`: output `.env` file (default: `gitlab.env.generated`)
- `--release-name`: value for `.Release.Name` (default: `store`)
- `--chart-name`: value for `.Chart.Name` (default: `store-service`)
- `--env-template`: existing `.env` file to update instead of creating a new one
- `--keep-missing`: keep values from the template file when the deployment does not define them

### 2. Generate `github.env` from a GitHub Actions variable YAML

```bash
python yaml_vars_to_env.py github.deploy.vars.yaml -o github.env --env prod-tope123
```

The input YAML is expected to look like:

```yaml
variables:
  globales:
    - name: LOG_LEVEL
      value: info
  custom:
    prod-tope123:
      - name: DATABASE_URL
        value: postgres://prod
```

Options:

- `yaml_file`: input YAML path
- `-e / --env`: environment inside `variables.custom` to include (required if more than one exists)
- `-o / --output`: output `.env` file (default: `.env`)

### 3. Compare two `.env` files

```bash
python compare_env.py \
  --github github.env \
  --gitlab gitlab.env \
  --output comparacion-env.md
```

The report contains:

- Summary counts
- Variables with different values
- Variables present only in `github.env`
- Variables present only in `gitlab.env`
- Variables with empty values
- Variables with equal values

### 4. Run the full pipeline with `homologar.py`

From a service directory that contains `deployment.yaml`, `values.yaml`, and `github.deploy.vars.yaml`:

```bash
python /path/to/utils/homologar.py --dir . --env prod-tope123
```

This will create `gitlab.env`, `github.env`, and `comparacion-env.md` in the current directory.

## Makefile targets

```bash
# Generate gitlab.env from Helm
make env VALUES=values.yaml

# Generate github.env from a GitHub Actions variable YAML
make yaml-env FILE=github.deploy.vars.yaml ENV=prod-tope123

# Run the full homologation pipeline
make homologar ENV=prod-tope123
```

## Supported Helm syntax

`generate_env_from_helm.py` supports a subset of Helm/Go template syntax:

- Values lookup: `.Values.foo.bar`
- Release/Chart lookup: `.Release.Name`, `.Chart.Name`
- Conditionals: `{{ if ... }}`, `{{ else }}`, `{{ end }}`
- Ranges: `{{ range ... }} ... {{ end }}`
- Locals: `$var`
- Common filters: `default`, `upper`, `lower`, `trim`, `nospace`, `quote`, `toYaml`, `toJson`
- Boolean operators: `not`, `and`, `or`, `eq`, `ne`

It is intentionally lightweight and does not require the Helm binary.

## Notes

- Values from `github.deploy.vars.yaml` are not quoted; they are written as-is.
- Empty values in the comparison report mean the variable exists but has an empty string value.
- The comparison is case-sensitive and treats the variable names as exact matches.

#!/usr/bin/env python3
import argparse
import re
import sys
from collections import OrderedDict
from pathlib import Path

import yaml


MISSING = object()
CONTROL_RE = re.compile(r"{{-?\s*(.*?)\s*-?}}")
ENV_NAME_RE = re.compile(r"^\s*-\s*name\s*:\s*(.*?)\s*$")
ENV_VALUE_RE = re.compile(r"^\s*value\s*:\s*(.*?)\s*$")
ENV_VALUE_FROM_RE = re.compile(r"^\s*valueFrom\s*:")
ENV_KEY_RE = re.compile(r"^(export\s+)?([A-Za-z_][A-Za-z0-9_]*)=")


def deep_merge(base, override):
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            merged[key] = deep_merge(merged[key], value) if key in merged else value
        return merged
    return override


def load_values(paths):
    values = {}
    for path in paths:
        data = yaml.safe_load(Path(path).read_text()) or {}
        if not isinstance(data, dict):
            raise ValueError(f"{path} debe contener un objeto YAML en la raíz")
        values = deep_merge(values, data)
    return values


def lookup_path(context, path):
    path = path.strip()
    if path == ".":
        return context.get(".", MISSING)

    if path.startswith(".Values."):
        current = context["values"]
        parts = path[len(".Values.") :].split(".")
    elif path.startswith(".Chart."):
        current = context["chart"]
        parts = path[len(".Chart.") :].split(".")
    elif path.startswith(".Release."):
        current = context["release"]
        parts = path[len(".Release.") :].split(".")
    elif path.startswith("."):
        current = context.get(".", MISSING)
        parts = path[1:].split(".")
    else:
        return MISSING

    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return MISSING
        current = current[part]
    return current


def split_pipeline(expr):
    parts = []
    current = []
    quote = None
    depth = 0
    for char in expr:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in "'\"":
            quote = char
            current.append(char)
        elif char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth -= 1
            current.append(char)
        elif char == "|" and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    parts.append("".join(current).strip())
    return parts


def split_args(expr):
    args = []
    current = []
    quote = None
    depth = 0
    for char in expr.strip():
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in "'\"":
            quote = char
            current.append(char)
        elif char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth -= 1
            current.append(char)
        elif char.isspace() and depth == 0:
            if current:
                args.append("".join(current))
                current = []
        else:
            current.append(char)
    if current:
        args.append("".join(current))
    return args


def is_empty(value):
    return value is MISSING or value is None or value is False or value == "" or value == [] or value == {}


def helm_string(value):
    if value is MISSING or value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return yaml.safe_dump(value, default_flow_style=True, allow_unicode=True).strip()
    return str(value)


def eval_expr(expr, context):
    expr = expr.strip()
    if not expr:
        return ""

    parts = split_pipeline(expr)
    value = eval_atom(parts[0], context)

    for filter_expr in parts[1:]:
        args = split_args(filter_expr)
        name = args[0] if args else ""
        if name in {"quote", "squoute", "toString", "tostring", "trim", "nospace"}:
            if name in {"trim", "nospace"}:
                value = helm_string(value).strip().replace(" ", "")
            continue
        if name == "default" and len(args) >= 2:
            if is_empty(value):
                value = eval_expr(" ".join(args[1:]), context)
            continue
        if name == "upper":
            value = helm_string(value).upper()
            continue
        if name == "lower":
            value = helm_string(value).lower()
            continue
        if name in {"toYaml", "toJson"}:
            value = helm_string(value)
            continue

    return value


def eval_atom(expr, context):
    expr = expr.strip()
    if not expr:
        return ""
    if expr.startswith("(") and expr.endswith(")"):
        return eval_condition(expr[1:-1], context)
    if expr.startswith("$"):
        return context["locals"].get(expr, MISSING)
    if expr.startswith('template "'):
        return context["release"].get("Name", "")
    if expr.startswith(".") or expr == ".":
        return lookup_path(context, expr)
    if expr.startswith("'") or expr.startswith('"'):
        try:
            return yaml.safe_load(expr)
        except yaml.YAMLError:
            return expr.strip("'\"")
    try:
        return yaml.safe_load(expr)
    except yaml.YAMLError:
        return expr


def eval_condition(expr, context):
    expr = expr.strip()
    if expr.startswith("if "):
        expr = expr[3:].strip()
    while expr.startswith("(") and expr.endswith(")") and balanced_outer(expr):
        expr = expr[1:-1].strip()

    args = split_args(expr)
    if not args:
        return False
    if args[0] == "not" and len(args) == 2:
        return not truthy(eval_condition(args[1], context))
    if args[0] == "and":
        return all(truthy(eval_condition(arg, context)) for arg in args[1:])
    if args[0] == "or":
        return any(truthy(eval_condition(arg, context)) for arg in args[1:])
    if args[0] == "eq" and len(args) >= 3:
        return eval_expr(args[1], context) == eval_expr(args[2], context)
    if args[0] == "ne" and len(args) >= 3:
        return eval_expr(args[1], context) != eval_expr(args[2], context)
    return truthy(eval_expr(expr, context))


def truthy(value):
    return not is_empty(value)


def balanced_outer(expr):
    depth = 0
    quote = None
    for index, char in enumerate(expr):
        if quote:
            if char == quote:
                quote = None
            continue
        if char in "'\"":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0 and index != len(expr) - 1:
                return False
    return depth == 0


def line_controls(line):
    return [match.group(1).strip() for match in CONTROL_RE.finditer(line)]


def is_control(expr):
    return expr == "end" or expr == "else" or expr.startswith(("if ", "range ", "with "))


def find_block_end(lines, start):
    depth = 0
    else_index = None
    for index in range(start + 1, len(lines)):
        controls = line_controls(lines[index])
        for expr in controls:
            if expr.startswith(("if ", "range ", "with ")):
                depth += 1
            elif expr == "else" and depth == 0:
                else_index = index
            elif expr == "end":
                if depth == 0:
                    return index, else_index
                depth -= 1
    raise ValueError(f"Bloque Helm sin end en la línea {start + 1}")


def render_lines(lines, context):
    rendered = []
    index = 0
    while index < len(lines):
        line = lines[index]
        controls = line_controls(line)
        if len(controls) == 1 and is_control(controls[0]):
            expr = controls[0]
            if expr.startswith("if "):
                end, else_index = find_block_end(lines, index)
                if eval_condition(expr, context):
                    body_end = else_index if else_index is not None else end
                    rendered.extend(render_lines(lines[index + 1 : body_end], context))
                elif else_index is not None:
                    rendered.extend(render_lines(lines[else_index + 1 : end], context))
                index = end + 1
                continue
            if expr.startswith("range "):
                end, _ = find_block_end(lines, index)
                rendered.extend(render_range(expr, lines[index + 1 : end], context))
                index = end + 1
                continue
            if expr.startswith("with "):
                end, _ = find_block_end(lines, index)
                value = eval_expr(expr[5:], context)
                if truthy(value):
                    nested = dict(context)
                    nested["locals"] = dict(context["locals"])
                    nested["."] = value
                    rendered.extend(render_lines(lines[index + 1 : end], nested))
                index = end + 1
                continue
            index += 1
            continue

        rendered.append(render_inline(line, context))
        index += 1
    return rendered


def render_range(expr, body, context):
    match = re.match(r"range\s+(?:(\$[\w]+)\s*,\s*(\$[\w]+)\s*:=\s*)?(.+)$", expr)
    if not match:
        return []
    key_var, value_var, target_expr = match.groups()
    target = eval_expr(target_expr, context)
    if is_empty(target):
        return []

    if isinstance(target, dict):
        items = sorted(target.items(), key=lambda item: str(item[0]))
    elif isinstance(target, list):
        items = enumerate(target)
    else:
        return []

    output = []
    for key, value in items:
        nested = dict(context)
        nested["locals"] = dict(context["locals"])
        if key_var:
            nested["locals"][key_var] = key
        if value_var:
            nested["locals"][value_var] = value
        else:
            nested["."] = value
        output.extend(render_lines(body, nested))
    return output


def render_inline(line, context):
    def replace(match):
        expr = match.group(1).strip()
        if is_control(expr):
            return ""
        return helm_string(eval_expr(expr, context))

    return CONTROL_RE.sub(replace, line)


def is_pure_control_line(line):
    controls = line_controls(line)
    return (
        len(controls) == 1
        and is_control(controls[0])
        and CONTROL_RE.sub("", line).strip() == ""
    )


def env_block_lines(template_path):
    lines = Path(template_path).read_text().splitlines()
    start = None
    for index, line in enumerate(lines):
        if re.match(r"^\s*env:\s*$", line):
            start = index
            break
    if start is None:
        raise ValueError("No encontré un bloque env: en el deployment")

    def line_indent(index):
        return len(lines[index]) - len(lines[index].lstrip())

    env_indent = line_indent(start)
    end = len(lines)
    index = start + 1
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if is_pure_control_line(line):
            expr = line_controls(line)[0]
            if expr.startswith(("if ", "range ", "with ")) and line_indent(index) <= env_indent:
                lookahead = index + 1
                while lookahead < len(lines) and (
                    not lines[lookahead].strip() or is_pure_control_line(lines[lookahead])
                ):
                    lookahead += 1
                if lookahead >= len(lines) or line_indent(lookahead) <= env_indent:
                    end = index
                    break
            index += 1
            continue
        if line_indent(index) <= env_indent:
            end = index
            break
        index += 1
    return lines[start + 1 : end]


def unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def extract_env(template_path, context):
    rendered = render_lines(env_block_lines(template_path), context)
    entries = OrderedDict()
    current_name = None
    current_has_value = False

    for line in rendered:
        name_match = ENV_NAME_RE.match(line)
        if name_match:
            current_name = unquote(name_match.group(1))
            entries[current_name] = ""
            current_has_value = False
            continue

        if current_name is None:
            continue
        if ENV_VALUE_FROM_RE.match(line):
            entries[current_name] = ""
            current_has_value = True
            continue
        value_match = ENV_VALUE_RE.match(line)
        if value_match and not current_has_value:
            entries[current_name] = unquote(value_match.group(1))
            current_has_value = True

    return entries


def update_env_file(template_path, output_path, entries, keep_missing):
    output = []
    seen = set()
    template_lines = []
    if template_path:
        template = Path(template_path)
        if template.exists():
            template_lines = template.read_text().splitlines()
    for line in template_lines:
        match = ENV_KEY_RE.match(line)
        if not match:
            output.append(line)
            continue
        key = match.group(2)
        seen.add(key)
        if key in entries:
            value = entries[key]
        elif keep_missing:
            output.append(line)
            continue
        else:
            value = ""
        prefix = match.group(1) or ""
        output.append(f"{prefix}{key}={value}")

    missing = [key for key in entries if key not in seen]
    if missing:
        if output:
            if output[-1] != "":
                output.append("")
            output.append("# Variables generadas que no estaban en el archivo original")
        output.extend(f"{key}={entries[key]}" for key in missing)

    Path(output_path).write_text("\n".join(output) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Genera un .env desde un deployment Helm y archivos values.yaml"
    )
    parser.add_argument("--deployment", default="deployment.yaml")
    parser.add_argument("--env-template", default=None)
    parser.add_argument("--output", default="gitlab.env.generated")
    parser.add_argument("-f", "--values", action="append", required=True)
    parser.add_argument("--release-name", default="store")
    parser.add_argument("--chart-name", default="store-service")
    parser.add_argument("--app-version", default="")
    parser.add_argument("--keep-missing", action="store_true")
    args = parser.parse_args()

    context = {
        "values": load_values(args.values),
        "locals": {},
        "chart": {"Name": args.chart_name, "AppVersion": args.app_version},
        "release": {"Name": args.release_name},
        ".": {},
    }
    entries = extract_env(args.deployment, context)
    update_env_file(args.env_template, args.output, entries, args.keep_missing)
    print(f"Generado {args.output} con {len(entries)} variables")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

PYTHON ?= python3
DEPLOYMENT ?= deployment.yaml
ENV_TEMPLATE ?=
OUTPUT ?= $(or $(PWD),$(CURDIR))/gitlab.env
ENV ?= prod-tope123

.PHONY: help env env-write clean-env yaml-env homologar

help:
	@echo "Uso:"
	@echo "  make env VALUES=values.yaml       # genera gitlab.env en tu directorio actual"
	@echo "  make env VALUES=\"values/common.yaml values/prod.yaml\""
	@echo "  make env-write VALUES=values.yaml # sobrescribe el archivo ENV_TEMPLATE"
	@echo "  make clean-env"
	@echo "  make yaml-env FILE=vars.yaml ENV=tope-qa [OUT=archivo.env]"
	@echo "      # convierte YAML de variables a .env; por defecto lo nombra como el"
	@echo "      # archivo de entrada (github.deploy.vars.yaml -> github.env) y lo"
	@echo "      # guarda en el directorio desde donde invocaste make"
	@echo "  make homologar [ENV=otro-ambiente]"
	@echo "      # ejecutado desde el dir del servicio: genera gitlab.env + github.env"
	@echo "      # (requiere deployment.yaml, values.yaml, github.deploy.vars.yaml)"
	@echo "      # y compara ambos en comparacion-env.md."
	@echo "      # github.env incluye globales + custom.$(ENV) (default prod-tope123)"

env:
ifndef VALUES
	$(error Debes indicar VALUES. Ejemplo: make env VALUES=values-prod.yaml)
endif
	$(PYTHON) generate_env_from_helm.py \
		--deployment "$(DEPLOYMENT)" \
		$(if $(ENV_TEMPLATE),--env-template "$(ENV_TEMPLATE)",) \
		$(foreach file,$(VALUES),-f "$(file)") \
		--output "$(OUTPUT)"

env-write: OUTPUT = $(or $(ENV_TEMPLATE),$(error env-write requiere ENV_TEMPLATE: es el archivo que se sobrescribe))
env-write: env

clean-env:
	rm -f gitlab.env.generated

yaml-env:
ifndef FILE
	$(error Debes indicar FILE. Ejemplo: make yaml-env FILE=vars.yaml ENV=tope-qa)
endif
	$(PYTHON) yaml_vars_to_env.py "$(FILE)" \
		$(if $(ENV),--env "$(ENV)",) \
		-o "$(or $(OUT),$(or $(PWD),$(CURDIR))/$(firstword $(subst ., ,$(notdir $(FILE)))).env)"

homologar:
	$(PYTHON) homologar.py --dir "$(or $(PWD),$(CURDIR))" --env "$(ENV)"

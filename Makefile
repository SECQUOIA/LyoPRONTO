############ Minimal Benchmark Makefile ############
# Deprecated legacy targets removed. Use grid_cli.py for generation.
# Override variables on invocation: e.g.
#   make bench VARY='product.A1=16,18,20 ht.KC=2.75e-4,3.3e-4,4.0e-4'

.PHONY: help bench analyze

# Defaults
TASK ?= Tsh
SCENARIO ?= baseline
VARY ?= product.A1=16,18,20 ht.KC=2.75e-4,3.3e-4,4.0e-4
METHODS ?= scipy,fd,colloc
N_ELEMENTS ?= 24
N_COLLOCATION ?= 3
OUT ?= benchmarks/results/grid_$(TASK)_$(SCENARIO).jsonl
METRIC ?= ratio.pyomo_over_scipy

help:
	@echo "Targets:"; \
	echo "  bench   Generate grid JSONL via benchmarks/grid_cli.py"; \
	echo "  analyze Execute analysis notebook (headless) against OUT"; \
	echo "Variables:"; \
	echo "  TASK=$(TASK) SCENARIO=$(SCENARIO)"; \
	echo "  VARY='$(VARY)'"; \
	echo "  METHODS=$(METHODS) N_ELEMENTS=$(N_ELEMENTS) N_COLLOCATION=$(N_COLLOCATION)"; \
	echo "  OUT=$(OUT) METRIC=$(METRIC)"; \
	echo "Examples:"; \
	echo "  make bench VARY='product.A1=16,18,20 ht.KC=2.75e-4,3.3e-4,4.0e-4'"; \
	echo "  make analyze METRIC=pyomo.objective_time_hr"

bench:
	@echo "[bench] Generating $(OUT)";
	@python benchmarks/grid_cli.py generate \
	  --task $(TASK) --scenario $(SCENARIO) \
	  $(foreach spec,$(VARY),--vary $(spec)) \
	  --methods $(METHODS) \
	  --n-elements $(N_ELEMENTS) --n-collocation $(N_COLLOCATION) \
	  --out $(OUT)

analyze:
	@echo "[analyze] Executing analysis notebook for $(OUT) (METRIC=$(METRIC))";
	@JSONL_PATH=$(OUT) METRIC=$(METRIC) python -m nbconvert --to notebook --execute benchmarks/grid_analysis.ipynb --output benchmarks/results/analysis_executed.ipynb || \
		echo "Notebook execution failed or nbconvert missing; open benchmarks/grid_analysis.ipynb manually with JSONL_PATH=$(OUT) METRIC=$(METRIC)"


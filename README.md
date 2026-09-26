# Anonymous CAD benchmark review artifact

This artifact provides 106 CAD design tasks, reference geometry, model-name driven generation, and the five evaluation checks used in the manuscript: code, geometry, structure, interface, and function. It includes the geometric interface recognition algorithms and their evidence outputs, rather than asking a language model to infer structural scores.

## Included data

The benchmark dataset is **included in this repository as `data/benchmark_dataset.zip`** (approximately 22 MB). It contains the downloaded dataset snapshot: task descriptions, design-specific evaluation rubrics, reference drawing/render images, and a metadata manifest for all 106 tasks. No external dataset account or download is needed. Identifying repository metadata and image metadata were removed for anonymous review. The original data license is retained inside the archive.

`data/reference_assets.zip` (approximately 76 MB) supplies 106 reference STEP models and frozen component/graph annotations needed by the evaluator; these STEP assets supplement the dataset download. STEP author/path headers were anonymized without changing geometry. `data/SHA256SUMS` provides archive checksums. Expanded data occupies roughly 0.5 GB.

The manuscript-era annotation snapshot contains 104 available task references. The entries for `cnc_shoe_rack_narrow_three_tier` and `cnc_tv_stand_three_bay_console` are explicitly marked unavailable. They remain in the 106-task denominator; the package does not substitute later repaired annotations. See [protocol details](docs/PROTOCOL.md).

## Installation

Use Python 3.11–3.13 on a machine supported by CadQuery. The artifact was exercised with Python 3.13 and CadQuery 2.7.0. From this repository directory:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
cad-review setup-data
```

Use an **editable installation** as shown: evaluation loads the bundled `methods/`, `vendor/`, and `prompts/` directories directly. PNG rendering additionally requires `rsvg-convert`: install `librsvg` with Homebrew on macOS, or `librsvg2-bin` with apt on Ubuntu. STEP-based geometry and interface checks do not require PNG rendering; the vision judge does.

## Quick smoke test (no API calls)

```bash
python -m pytest -q
PYTHONPATH=methods/v6 python -m pytest methods/v6 -q
cad-review evaluate --runs examples/smoke --output evaluation/smoke --tasks chair
```

The synthetic two-component fixture exercises code execution, geometry, interface detection, clearance measurement, drawing, and aggregation. It deliberately does **not** solve the chair task and is not a benchmark result. Function scores are unavailable without a judge model. Even a one-task smoke run uses the fixed 106-task denominator; inspect per-sample JSON for diagnostics.

## Run a model

Supply your own model name and credentials. No model name, private endpoint, or credential is embedded. The client accepts a Chat Completions compatible endpoint; the function judge must support image inputs and return the requested JSON schema.

```bash
export MODEL_API_KEY='YOUR_OWN_KEY'
export MODEL_BASE_URL='https://api.openai.com/v1'

cad-review generate --model YOUR_MODEL_NAME --samples 1 --output runs/model
cad-review evaluate --runs runs/model --judge-model YOUR_VISION_MODEL_NAME --output evaluation/model
```

Use `--base-url` to override the endpoint and `--key-env` to select a different credential environment variable. `.env.example` is a template; the CLI does not automatically load `.env`. Credentials are only sent to the endpoint you configure and are not saved in run configurations. Neither command is needed for the offline tests.

`--samples N` generates N independent completions per task. `--tasks chair ...` restricts a development run. `--temperature` is optional (omitted from API requests by default). Generation uses the task specification and the bundled generation prompt; it does not expose the evaluation rubric to the model. Existing code files are skipped unless `--overwrite` is passed.

Evaluate your own generated code with this layout:

```text
runs/model/<task_id>/sample_1/code.py
runs/model/<task_id>/sample_2/code.py
```

Each script must assign a nonempty CadQuery Shape, Workplane, or Assembly to `result`. A `model.step` can be supplied instead, but then executable-code success is unverified and code-dependent scores are zero. Use the code route for benchmark reporting.

Generated Python is executed with timeouts in a separate process. This is **not a security sandbox**: run untrusted model output in a disposable container or isolated machine without personal files or credentials. Model credential environment variables are stripped from workers, but that alone does not isolate filesystem or network access.

## Results and interpretation

Each sample produces execution/geometry/SIE JSON, raw interface evidence, drawings when available, and `evaluation.json`. With a vision judge it also produces `judge.json`. `summary.json` includes task coverage and all per-task values, as well as rates and conditional clearance/GED statistics.

```bash
cad-review aggregate --runs evaluation/model --output evaluation/model/summary.json
```

Node, Edge, and Type are averaged **over all 106 tasks**, with missing/undefined scores zero-filled. Multiple samples are averaged within each task first. Geometry failure does not suppress a computable structure/interface score. Missing vision evaluation is recorded as `not_evaluated` and contributes zero to function/joint rates: such a run is incomplete, not evidence of function failure.

This release supports rerunning the documented protocol with a supplied model. It does not contain historical private model predictions, model-specific launchers, or a claim that new API completions will reproduce every manuscript table entry. [PROTOCOL.md](docs/PROTOCOL.md) records the implementation details and known manuscript/implementation differences; [VALIDATION.md](docs/VALIDATION.md) records the checks performed on this artifact.

## Layout

- `src/review_benchmark/`: portable CLI, aggregation, component correspondence, graph and clearance scoring.
- `methods/`: geometric interface detection and connection-type recognition implementation.
- `vendor/`: bundled CAD drawing and geometry validation helpers.
- `prompts/`: generation and design-specific rubric judge prompts.
- `data/`: dataset and reference asset ZIPs.
- `tests/`, `methods/v6/test_*.py`, `examples/smoke/`: offline validation and demonstration.

Dataset license: CC BY 4.0, retained in the dataset archive. This is an anonymous review distribution of the accompanying research code and assets; no new code license is asserted here. Dependency licenses remain those of their respective projects.

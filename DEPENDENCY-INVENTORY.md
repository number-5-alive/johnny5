# Dependency license inventory

First built 2026-11-04 with the licensing update release, applying
SAINT decision record 036s1, ratified by the maintainer the same
day. Licenses verified against each package's own PyPI metadata
(license expression or classifier). The package set is the project's
`uv.lock` at the time of the check: every declared dependency and
every transitive dependency behind it, 81 third-party packages.

## Findings

- **No copyleft reaches the project.** Nothing in the tree is GPL,
  LGPL, or AGPL. The project's own licensing choices are its own.
- **Two packages are weak, file-level copyleft:** `certifi` and
  `tqdm` carry MPL-2.0 terms for their own files. The MPL does not
  extend to the project, is compatible with AGPL distribution, and
  does not block commercial terms for the project's own code.
- **One proprietary cluster:** the `nvidia-*` CUDA libraries, pulled
  in transitively by `torch` for GPU support, are NVIDIA proprietary
  software (several declare no license in their PyPI metadata at
  all). They are runtime binaries under NVIDIA's terms, not part of
  this project, and no license of this project's can or does cover
  them. They are flagged here because the 036s1 position requires
  non-relicensable dependencies to be visible, not because they
  block anything: commercial terms, if ever offered, would cover
  Johnny 5's own code only.
- Everything else is permissive: MIT, BSD variants, Apache-2.0,
  ISC, PSF, Zlib, or CC0, including composite permissive bundles
  such as `torch` and `numpy`.

## Declared dependencies (from pyproject.toml)

| Package | Where used | License |
|---|---|---|
| httpx | core | BSD-3-Clause |
| pyarrow | core | Apache-2.0 |
| laya | optional: shelf library | Apache-2.0 |
| fastapi | optional: service | MIT |
| uvicorn | optional: service | BSD-3-Clause |
| opentelemetry-sdk | optional: service | Apache-2.0 |
| opentelemetry-exporter-otlp-proto-grpc | optional: service | Apache-2.0 |
| openinference-semantic-conventions | optional: service | Apache-2.0 |
| selectolax | optional: corpus building | MIT |
| hatchling | build backend only | MIT |

## Full locked set (uv.lock, transitive included)

| Package | Locked version | License (PyPI metadata) |
|---|---|---|
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| certifi | 2026.7.22 | Mozilla Public License 2.0 (MPL 2.0) |
| click | 8.5.0 | BSD-3-Clause |
| colorama | 0.4.6 | BSD License |
| cuda-bindings | 13.4.4 | Apache-2.0 |
| cuda-pathfinder | 1.8.3 | Apache-2.0 |
| cuda-toolkit | 13.0.3.0 | NOT DECLARED |
| fastapi | 0.143.2 | MIT |
| filelock | 4.2.0 | MIT |
| fsspec | 2026.9.0 | BSD-3-Clause |
| googleapis-common-protos | 1.75.5 | Apache-2.0 |
| grpcio | 1.84.0 | Apache-2.0 |
| h11 | 0.16.0 | MIT License |
| hf-xet | 1.7.0 | Apache-2.0 |
| httpcore | 1.0.9 | BSD-3-Clause |
| httpcore2 | 2.13.1 | BSD-3-Clause |
| httpx | 0.28.1 | BSD License |
| httpx2 | 2.13.1 | BSD-3-Clause |
| httpx2-jsfetch | 1.0 | BSD-3-Clause |
| huggingface-hub | 2.2.0 | Apache Software License |
| idna | 3.20 | BSD-3-Clause |
| jinja2 | 3.1.6 | BSD License |
| laya | 0.4.8 | Apache Software License |
| markdown-it-py | 4.2.0 | MIT License |
| markupsafe | 3.0.4 | BSD-3-Clause |
| mdurl | 0.1.2 | MIT License |
| mpmath | 1.3.0 | BSD-3-Clause |
| networkx | 3.6.1 | BSD-3-Clause |
| networkx | 3.7 | BSD-3-Clause |
| numpy | 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| nvidia-cublas | 13.1.1.3 | LicenseRef-NVIDIA-Proprietary |
| nvidia-cuda-cupti | 13.0.85 | LicenseRef-NVIDIA-Proprietary |
| nvidia-cuda-nvrtc | 13.0.88 | LicenseRef-NVIDIA-Proprietary |
| nvidia-cuda-runtime | 13.0.96 | LicenseRef-NVIDIA-Proprietary |
| nvidia-cudnn-cu13 | 9.24.0.43 | NOT DECLARED |
| nvidia-cufft | 12.0.0.61 | LicenseRef-NVIDIA-Proprietary |
| nvidia-cufile | 1.15.1.6 | LicenseRef-NVIDIA-Proprietary |
| nvidia-curand | 10.4.0.35 | LicenseRef-NVIDIA-Proprietary |
| nvidia-cusolver | 12.0.4.66 | LicenseRef-NVIDIA-Proprietary |
| nvidia-cusparse | 12.6.3.3 | LicenseRef-NVIDIA-Proprietary |
| nvidia-cusparselt-cu13 | 0.8.1 | NVIDIA Proprietary Software |
| nvidia-nccl-cu13 | 2.30.7 | NOT DECLARED |
| nvidia-nvjitlink | 13.4.92 | LicenseRef-NVIDIA-Proprietary |
| nvidia-nvshmem-cu13 | 3.4.5 | NOT DECLARED |
| nvidia-nvtx | 13.0.85 | LicenseRef-NVIDIA-Proprietary |
| openinference-semantic-conventions | 0.1.41 | Apache-2.0 |
| opentelemetry-api | 1.45.1 | Apache-2.0 |
| opentelemetry-exporter-otlp-common | 0.66b1 | Apache-2.0 |
| opentelemetry-exporter-otlp-proto-common | 1.45.1 | Apache-2.0 |
| opentelemetry-exporter-otlp-proto-grpc | 1.45.1 | Apache-2.0 |
| opentelemetry-proto | 1.45.1 | Apache-2.0 |
| opentelemetry-sdk | 1.45.1 | Apache-2.0 |
| opentelemetry-semantic-conventions | 0.66b1 | Apache-2.0 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| protobuf | 7.36.2 | 3-Clause BSD License |
| pyarrow | 26.0.0 | Apache-2.0 |
| pydantic | 2.14.1 | MIT |
| pydantic-core | 2.50.1 | MIT |
| pygments | 2.21.0 | BSD-2-Clause |
| pyyaml | 6.0.3 | MIT License |
| regex | 2026.9.29 | Apache-2.0 AND CNRI-Python |
| rich | 15.0.0 | MIT License |
| safetensors | 0.8.0 | Apache Software License |
| selectolax | 1.0.0 | MIT |
| setuptools | 84.0.0 | MIT |
| shellingham | 1.5.4 | ISC License (ISCL) |
| starlette | 1.8.0 | BSD-3-Clause |
| sympy | 1.14.0 | BSD License |
| tokenizers | 0.23.3 | Apache Software License |
| torch | 2.14.1 | Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND ISC AND MIT AND Zlib |
| tqdm | 4.70.1 | MPL-2.0 AND MIT |
| transformers | 5.20.0 | Apache 2.0 License |
| triton | 3.8.0 | MIT |
| truststore | 0.10.5 | MIT |
| typer | 0.27.3 | MIT |
| typing-extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.4 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |

## Data and runtime the system uses (not code dependencies)

| Source | Used by | Terms |
|---|---|---|
| Wikipedia dumps | Wikipedia shelf | CC BY-SA |
| Stack Overflow data dump | code shelf | CC BY-SA |
| OpenStreetMap data (via Photon and Valhalla) | maps shelf | ODbL |
| GeoNames | maps shelf (alternate names) | CC BY |
| Ollama and Qwen model weights | all lanes (runtime, called not incorporated) | their own licenses |

## Refresh rule

Regenerate and re-verify this inventory at every release, and
whenever a dependency is added. A new dependency whose license is
copyleft, source-available, or otherwise incompatible with the
project's licensing is a blocker to be resolved before release, per
the 036s1 position.

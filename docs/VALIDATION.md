# Artifact validation

Validation used Python 3.13, CadQuery 2.7.0, NumPy 2.4.3, SciPy 1.17.1, Requests 2.32.4, and the system `rsvg-convert` on macOS. Editable installation and the installed CLI were exercised in a separate virtual environment using existing dependencies. A fresh network dependency installation and other operating systems were not tested.

- 23 offline tests passed: aggregation over all 106 tasks, zero handling, conservative correspondence, exact/bounded GED, code execution failures, stale-artifact removal, overlap detection, rectangular clearance, user-selected API model forwarding, and positive/negative geometric connection controls.
- The synthetic smoke fixture completed code export, geometry validation, structure/interface scoring, rectangular gap extraction, SVG/PNG rendering and summary generation. It produced two solids, no detected geometry errors, one measured rectangular interface, and intentionally zero structural correspondence to the chair reference.
- All 106 task records, 106 reference STEP files and 106 graph records were present. Two graph records explicitly indicate missing manuscript-era annotations.
- The downloaded public snapshot contained 429 files. Downloaded bytes were verified against repository Git-blob or large-file SHA hashes before anonymization. The released task data has 212 PNG images with metadata stripped. Archive hashes are included in `data/SHA256SUMS`.
- No live model API calls or full 106-task model generations were performed during validation. The vision judge request/response path still depends on a compatible model and endpoint supplied by the reviewer.

The release excludes environment files containing credentials, private launch scripts, original Git history, manuscript author files and historical model outputs. Automated scans check known identifying strings, local home paths and common credential patterns in source text and archived text/STEP assets. These checks do not imply that a publicly available dataset cannot be recognized from its content.

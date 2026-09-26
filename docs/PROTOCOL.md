# Frozen evaluation protocol

## Aggregation

The selected manuscript protocol has 106 tasks. Code/geometry and node/edge/type/function rates use within-task sample means followed by an unweighted mean over **106** tasks. Missing tasks, failed generations and unavailable graph scores are zero-filled. An empty/empty edge comparison is not awarded F1=1. Type F1 averages the defined connection classes within a task before the task mean. Coverage is reported separately. The later alternative that averages Edge/Type over only tasks with annotated connections is not used.

Clearance MAE pools only eligible paired dimensional observations, reporting `N_delta`; unavailable observations are not treated as zero error. GED averages available exact observations, with coverage. For large graphs where exhaustive search is skipped, only an upper bound is available and is excluded from exact GED aggregation.

Joint success requires executable nonempty CAD, geometry validity, Node/Edge/Type F1 all equal to one, and Functional/Robust both equal to one. Geometric invalidity does not itself prevent separately reporting structure/interface correspondence when extraction succeeds.

## Code and geometry

The worker executes Python and exports `result` to nonempty STEP. It accepts CadQuery Shape, Workplane and Assembly values. Execution and evaluation have configurable timeouts (180 and 600 seconds by default). It does not implement OS-level sandboxing.

Geometry checks use the bundled OCCT-based validator for watertightness, non-manifold edges and a self-intersection/shape-validity proxy, plus pairwise solid intersection volume for overlap (tolerance 1e-6 mm³). The self-intersection flag is the legacy validator's shape-validity proxy, not a complete mathematical self-intersection oracle. Check exceptions are unavailable/failed rather than successes. Geometry rate is gated on successful code execution.

## Structure and interface

Reference STEP geometry is used to match generated solids to semantic reference parts via one-to-one Hungarian assignment with dummy unmatched slots. Ambiguous, duplicate-name, or generic-name correspondences are rejected. Thresholds are in `matching.py`: maximum cost 0.32 and minimum row/column runner-up margin 0.035.

**Implementation/manuscript difference:** the preserved matching implementation combines normalized center, bounding-box dimensions and volume-to-box fill ratio with weights 0.55/0.35/0.10. The manuscript wording mentions face count; this release preserves the actual executable descriptor rather than silently replacing it with a different method.

Frozen semantic graph snapshots accompany the reference geometry. Unresolved text-to-part graph endpoints are handled conservatively; unavailable references are reported rather than inferred as perfect empty graphs. Two task snapshots are missing from the manuscript-era reference manifest and explicitly remain unavailable. A newer repaired graph set is deliberately not substituted.

Interface detection uses geometric contact/insertion evidence from STEP faces, followed by connection policies for Interlocking, Snap-fit, Nailing and Bonding. Dowel and mortise-and-tenon evidence map to Interlocking. Nailing requires connector geometry and external entry evidence; Bonding is a contact-based hypothesis, not detection of an invisible adhesive material. See the included positive and negative geometric tests.

Clearance compares paired parallel faces for rectangular insertion candidates. It measures total receiving width minus inserted width along each of two cross-section axes; it is not a signed per-side gap. A generated interface is compared only when both components map, the reference interface is unique, and axes correspond within one degree. The metric is deviation from reference STEP clearance, not manufacturing tolerance certification. Nonrectangular or ambiguous interfaces are excluded and counted in diagnostic reasons.

## Function check and experiment scope

The bundled judge prompt scores six rubric categories. The reported two function criteria use `Functional Adaptation` → Functional and `Usage Stability` → Robust. It receives the task description, design-specific rubric, reference drawing, and generated drawing. Binary scores are validated; unavailable judging is explicitly recorded and zero-filled for aggregate reporting.

The portable generation entry point performs independent single-pass completions using the original system/task prompt pattern and a user-supplied model name. It does not implement private model launch infrastructure or every historical retry/refinement setting used by previous experiments. Endpoint/model/temperature/sample-count choices should be recorded alongside any reported rerun. No paid model calls were used to validate this package.

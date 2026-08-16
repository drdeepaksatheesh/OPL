# Open 4D Cardiac Anatomy integration in OpenPhysiologyLab

This OPL research integration vendors a copy of the bundled-model components from
Open 4D Cardiac Anatomy for the Cardiac Anatomy tab.

The standalone Open 4D Cardiac Anatomy application remains an independent project.
OPL deliberately does not expose cine MRI/CT, mask-loading, or correction workflows.

## Bundled anatomy/motion scientific contract

- Detailed anatomy: Z-Anatomy / BodyParts3D-derived cardiovascular model.
- Motion: FAU/CONRAD 3D+t statistical heart model.
- The combined heart is a registered composite teaching model, not one patient.
- The source motion represents one normalized population-mean cardiac cycle.
- OPL fixed-rate presets time-warp that source cycle.
- OPL Current ECG Study mode uses the recorded R-R durations to time repeated model cycles.
- ECG-driven timing does not make the mechanical deformation subject-specific.

See the copied LICENSE, THIRD_PARTY_NOTICES.md, DATA_SOURCES.md,
docs/ASSET_PROVENANCE.md and CITATION.cff in this directory.

# OPL Public Release Policy

## Principle

**Develop privately; release deliberately; archive permanently.**

OpenPhysiologyLab is intended to be open and reproducible, but openness does not require unfinished development branches, unpublished experiments, abandoned algorithms, or laboratory notebooks to be public in real time.

## Release gate

A module is eligible for public release when it is:

1. **Functional** — the intended workflow completes end to end.
2. **Bounded** — the module clearly states what it does not do.
3. **Tested** — core calculations or interactions have repeatable tests.
4. **Documented** — a new user can start without reading source code.
5. **Versioned** — the interface displays a release identifier.
6. **Reproducible** — example inputs and expected outputs are available where appropriate.
7. **Validated at the claimed level** — teaching tools require content validation; measurement tools require technical validation proportionate to their claims.
8. **Safe in wording** — educational/research prototypes do not imply diagnostic-device status.

## Status labels

Use only these public maturity labels:

- **Demo** — concept demonstration; not validated for measurement.
- **Beta** — usable workflow; validation incomplete.
- **Validated** — specified claims tested against a documented reference.
- **Paper release** — frozen version corresponding to a publication.

## Source policy

The private development repository may contain unreleased work.

For any public scientific claim, the source code necessary to reproduce the corresponding released module must be published as a frozen snapshot.

## Data policy

Public example datasets must contain no personally identifiable information. Human research data require appropriate ethics/consent and a separate data-release decision.

## Versioning

Use semantic versioning where practical.

Paper-linked releases should additionally receive an immutable tag, for example:

`visual-hrv-v1.0.0-paper`

and should be archived with a DOI when possible.

## Change control

A released module may continue to evolve, but later changes must not silently alter the software version used in a published analysis.

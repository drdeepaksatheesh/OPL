# OPL public site

This directory is the prototype public-facing surface for OpenPhysiologyLab.

The goal is not to expose the entire development application. The goal is to give learners, teachers and researchers direct access to small released instruments.

## Deployment target

GitHub Pages.

## Rule

Do not add unfinished research logic to the public site merely because it exists in the development codebase. A module appears here when it satisfies `RELEASE_POLICY.md`.

## Current state

The landing page is a non-destructive prototype. It lists the intended modular structure but does not claim unreleased modules are validated or ready for use.

## Next implementation target

The first functional browser module should be chosen based on the shortest path to:

1. real use by another physiology laboratory;
2. a clean abstract;
3. a measurable validation experiment.

Current leading candidate: **OPL Calibration Bench / Recorder**, because acquisition accuracy and calibration create the foundation for later ECG/HRV validation.

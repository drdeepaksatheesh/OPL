# OPL public site

This directory is the prototype public-facing surface for OpenPhysiologyLab.

The goal is not to expose the entire development application. The goal is to give learners, teachers and researchers direct access to small released instruments.

## Deployment target

GitHub Pages.

## Rule

Do not add unfinished research logic to the public site merely because it exists in the development codebase. A module appears here when it satisfies `RELEASE_POLICY.md`.

## Current state

The first active public instrument is **OPL ECG Reference Lab**. It is reference-first and hardware-independent.

The Paper 1 release path is deliberately separate from the later Classroom Mode and acquisition work.

## Current implementation target

Build one excellent ECG Reference Lab around trusted open datasets and demonstrate:

1. faithful preservation of source waveform/time/unit metadata;
2. transparent raw-versus-processed visualization;
3. reproducible baseline-relative and temporal measurement;
4. quantitative counter-verification against appropriate reference annotations/metadata;
5. visible provenance and exact versioning;
6. downloadable/offline use on phone and computer.

Classroom pre/post evaluation and hardware acquisition are later OPL layers and are not part of the Paper 1 validation claim.

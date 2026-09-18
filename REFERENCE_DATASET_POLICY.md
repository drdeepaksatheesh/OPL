# OPL Reference Dataset Policy

OpenPhysiologyLab uses public reference datasets as scientific inputs, not as decorative examples.

A dataset is eligible for an OPL Reference Lab only when its provenance, reuse terms and scientific role can be made explicit.

## Required fields

Every dataset entry must document:

- dataset title;
- authoritative repository/institution;
- version;
- DOI or persistent identifier where available;
- licence/reuse terms;
- original investigators/contributors;
- acquisition modality and important acquisition metadata;
- known preprocessing;
- annotations and how they were produced;
- exact records/subset used by OPL;
- transformations performed by OPL;
- supported validation/teaching role;
- limitations and unsupported claims.

## Reliability is role-specific

A dataset may be excellent for one purpose and unsuitable as a reference for another.

Examples:

- a dataset with automated beat markers may be useful for demonstrating annotations but should not automatically be treated as cardiologist gold-standard delineation;
- a dataset with physical-unit metadata can verify unit-preserving software paths;
- a rhythm database with adjudicated beat labels may be appropriate for R-peak/beat-detection benchmarking;
- a teaching example does not become a diagnostic validation dataset merely because it is widely cited.

OPL should therefore state:

> **Trusted for what?**

rather than simply:

> **Trusted dataset.**

## Open-source/open-data rule

OPL software releases remain open-source.

For external datasets:

- preserve the original licence and attribution;
- do not imply OPL owns the data;
- do not redistribute data when the source terms do not permit redistribution;
- where redistribution is allowed, retain provenance alongside the bundled data;
- prefer retrieval from the authoritative source when feasible;
- freeze exact source versions/records for paper-linked releases.

## Machine-readable registry

The public Reference Lab should expose a machine-readable dataset registry so validation claims can be traced programmatically.

The registry is not a popularity list or quality ranking. It records the role each source plays in OPL.

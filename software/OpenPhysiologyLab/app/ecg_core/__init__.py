"""
Shared ECG core helpers for OpenPhysiologyLab.

UI panels should be visual front-ends. Reusable ECG logic belongs here:

- io.py: raw.csv reading, time scaling, ECG channel selection
- filters.py: sampling-rate and ECG filters
- r_detection.py: shared R detection
- complexes.py: complete complex / RR-pair / triplet helpers
- intervals.py: RR/NN interval generation and time-domain HRV stats
"""

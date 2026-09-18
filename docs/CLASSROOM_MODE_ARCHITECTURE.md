# OPL Classroom Mode Architecture

## Purpose

OPL should work across two very different teaching surfaces without splitting into unrelated products:

- **Phone / tablet:** rapid teaching, guided physiology, polls, MCQs, short measurements, live classroom participation.
- **Laptop / desktop:** full Reference Labs, dense traces, multi-panel analysis, reproducibility, exports, computational work, later acquisition and research workflows.

The same scientific source, provenance rules, and calculation core should serve both.

## Principle

**The phone is a teaching surface. The laptop is a laboratory surface.**

A learner should be able to move between them without changing the meaning of the physiology.

## Layer 1 — Offline/self-study mode

Must work with no account and no server.

Capabilities:
- installable PWA;
- trusted reference data cached locally;
- guided lessons;
- touch-friendly measurements;
- MCQs and immediate explanations;
- local progress;
- exportable response/session package.

This layer is part of the normal static OPL build.

## Layer 2 — Live classroom mode

Optional network layer for synchronous teaching.

Example flow:

1. Teacher opens OPL on a laptop/tablet.
2. Teacher starts a classroom session.
3. OPL shows a short join code and QR code.
4. Students open the OPL phone page and join.
5. Teacher can push:
   - an ECG window;
   - a highlighted physiological feature;
   - an MCQ/poll;
   - a measurement task.
6. Students respond on their phones.
7. Teacher sees aggregate responses in real time.
8. The scientific Reference Lab continues to work if the room service disappears.

## Decentralization boundary

The live-session service is an **adapter**, not the OPL core.

It must not be required for:
- loading reference datasets;
- calculations;
- offline lessons;
- saved packages;
- published analysis;
- paper reproducibility.

A university should be able to self-host the room service.

## Minimal data carried by a room

Prefer transient classroom state:

- random room id;
- optional display nickname or anonymous participant id;
- current activity/question id;
- answer/measurement response;
- timestamps;
- aggregate counts.

Do not send full reference datasets when a record id and source version are sufficient.

Do not collect student email, phone number, advertising identifiers, precise location, or device fingerprint by default.

## Teacher evaluation

The initial goal is formative teaching, not high-stakes examination.

Useful outputs:
- response distribution;
- percentage correct;
- common distractor;
- response latency;
- pre/post question comparison;
- anonymous export for teaching analysis.

If OPL is later used for formal assessment, authentication, integrity, retention and institutional rules require a separate design.

## Open protocol

The room protocol should be documented so alternate implementations can exist.

Candidate message types:

- session_created
- join
- activity_opened
- question_opened
- response_submitted
- aggregate_updated
- activity_closed
- session_ended

The browser client should communicate through a small provider interface so a local/self-hosted server, university server, or future compatible provider can be swapped without rewriting the physiology tools.

## Publication boundary

Classroom Mode is infrastructure, not automatically a separate paper.

It becomes publishable only if there is a distinct educational question and evaluation, for example:

> Does synchronized phone-based interaction with reference ECG traces improve first-year learners' understanding of ECG signal processing and baseline-relative measurement compared with conventional demonstration?

That would require its own educational study rather than recycling technical validation of the ECG Reference Lab.

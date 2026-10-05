# OPL Classroom Protocol v0.1

## Teaching model

OpenPhysiologyLab should support a two-surface classroom:

- **Teacher surface — laptop/desktop:** full Reference Lab, lesson control, pre/post tests, live trace navigation, question launch, doubt timeline, participation summary and export.
- **Student surface — phone/tablet:** join room, complete pre-test, follow the currently taught physiological section, submit doubts at the current lesson time, answer live questions, complete post-test and review explanations where enabled.

The scientific Reference Lab remains independent of the classroom service.

## Classroom lifecycle

### 1. Session setup
Teacher creates a session from a lesson template.

Template contains:
- title;
- topic;
- reference dataset/module;
- optional class/batch label;
- pre-test questionnaire;
- teaching sections;
- live questions/polls;
- post-test questionnaire;
- consent/information text where required;
- anonymous vs identified participation mode;
- retention/export settings.

### 2. Join
Teacher displays:
- QR code;
- short join code;
- session title.

Student joins from phone.

Default should be anonymous or teacher-defined pseudonymous participation.

### 3. Pre-test
Before the lesson opens, students receive the configured pre-test.

Supported first-pass item types:
- single-best-answer MCQ;
- true/false;
- Likert item;
- confidence rating;
- short free-text.

Questionnaires must be author-editable rather than hard-coded into ECG.

### 4. Synchronized teaching
Teacher navigates the full laptop OPL Reference Lab.

The room broadcasts lightweight lesson state, for example:
- module id;
- record id;
- current section/activity;
- visible time window;
- selected teaching marker;
- question currently open.

Student phones receive a simplified synchronized representation rather than the full advanced workstation interface.

The phone may show:
- the same ECG time window;
- highlighted feature;
- short teaching note;
- one relevant action (observe, measure, answer, ask doubt).

### 5. Attention / engagement signals
OPL must **not claim to measure attention directly** from passive browser telemetry.

It may record transparent engagement proxies such as:
- page/session connected;
- foreground/visibility state;
- current OPL section;
- section transition timestamps;
- response to live questions;
- completion of teacher-pushed activities.

These should be labelled **engagement/activity signals**, not attention.

No device fingerprinting, camera surveillance, keystroke surveillance or hidden tracking.

### 6. Doubt timeline
At any point, a student can tap **Ask / Doubt**.

A doubt event records:
- anonymous/pseudonymous participant id;
- client timestamp;
- current lesson elapsed time;
- current OPL section/activity id;
- current signal window/record location where relevant;
- free-text doubt;
- optional "me too" aggregation later.

Teacher dashboard collates doubts chronologically and by section.

Example:
- 08:14 — ECG filtering — 4 doubts
- 15:32 — baseline selection — 11 doubts
- 24:10 — PR interval — 3 doubts

This allows the teacher to identify where conceptual difficulty clustered.

### 7. Post-test
When the teacher closes teaching mode, the configured post-test opens automatically on student phones.

Post-test can:
- repeat selected pre-test items for paired change;
- add transfer/application questions;
- collect confidence;
- collect session feedback.

### 8. Teacher summary
Teacher laptop should show:
- joined participants;
- pre-test completion;
- live response distributions;
- engagement/activity timeline;
- section dwell/activity summaries;
- doubt timeline and clusters;
- post-test completion;
- paired pre/post summaries where participant linkage is enabled;
- export controls.

## Questionnaire schema

Questionnaires should be data, not application code.

Suggested schema:

```json
{
  "id": "ecg-basics-pre-v1",
  "title": "ECG Basics Pre-test",
  "phase": "pre",
  "items": [
    {
      "id": "q1",
      "type": "single_choice",
      "prompt": "At 500 Hz, one sample represents:",
      "options": ["0.5 ms", "1 ms", "2 ms", "5 ms"],
      "correct": 2,
      "required": true
    }
  ]
}
```

Questionnaire files should be versioned and included in exported session provenance.

## Session event model

Append-only events are preferred.

Core event types:
- session_created
- participant_joined
- pretest_started
- response_submitted
- pretest_completed
- activity_changed
- page_visibility_changed
- section_entered
- doubt_submitted
- live_question_opened
- live_question_closed
- posttest_started
- posttest_completed
- session_closed

Each event should include:
- schema version;
- session id;
- participant id where applicable;
- server receipt time;
- client time;
- event type;
- activity/module context;
- payload.

## Data integrity

Teacher export should include:
- session manifest;
- exact OPL build/commit;
- lesson template version;
- questionnaire versions;
- module/dataset versions;
- append-only event log;
- derived summary tables.

Raw event logs should remain available so summary calculations can be reproduced.

## Privacy modes

### Anonymous classroom
Default for routine formative teaching.
- random participant id;
- no name/email required;
- paired pre/post possible within the same session through the random id.

### Pseudonymous classroom
Teacher may request a roll number or code if educational evaluation requires matching.
This should be explicitly disclosed before joining.

### Research mode
If classroom data are intended for a research publication, ethics/consent requirements are separate from normal teaching operation.

## Decentralization

The classroom transport must use a documented provider interface.

OPL should be capable of:
- public hosted room service;
- institution-hosted room service;
- local/self-hosted room service.

The analysis/Reference Lab must continue to work if the room service is unavailable.

## First implementation milestone

Build the smallest full loop:

1. Teacher creates ECG classroom room.
2. Student joins on phone.
3. Student completes a configurable 3-question pre-test.
4. Teacher advances through 3 teaching sections.
5. Student phone follows current section.
6. Student can submit timestamped doubts.
7. Teacher pushes one live MCQ.
8. Teacher closes lesson.
9. Student receives 3-question post-test.
10. Teacher sees pre/post response summary + chronological doubt stream.
11. Teacher downloads a session JSON/CSV export.

This is enough to validate the architecture before adding accounts, LMS integration or advanced analytics.

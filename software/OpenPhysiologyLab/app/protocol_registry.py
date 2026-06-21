"""
OpenPhysiologyLab protocol registry.

This module is the bridge between:

Setup tab  -> protocol choices and setup preview
Recorder   -> practical recorder UI settings

It should stay boring and stable.

It should not:
- talk to hardware
- filter data
- detect peaks
- analyse recordings
- write analysis reports

It only returns protocol dictionaries/configurations.
"""


# ------------------------------------------------------------
# Optional ECG module import
# ------------------------------------------------------------

try:
    from app.signals.ecg.ecg_protocols import (
        ECG_PROTOCOLS,
        build_ecg_recorder_config,
        build_ecg_electrode_pin_mapping,
    )
except Exception:
    ECG_PROTOCOLS = None
    build_ecg_recorder_config = None
    build_ecg_electrode_pin_mapping = None


# ------------------------------------------------------------
# Fallback ECG definitions
# Used if app/signals/ecg/ecg_protocols.py is not yet present.
# ------------------------------------------------------------

FALLBACK_ECG_PROTOCOLS = {
    "ECG_HEADROOM_60S": {
        "signal_type": "ECG",
        "protocol_name": "ECG_HEADROOM_60S",
        "display_name": "ECG Headroom Test - 60 s",
        "description": (
            "Short ECG acquisition for ADC headroom, clipping, baseline position, "
            "R-peak timing usability, and basic morphology usability."
        ),
        "duration_seconds": 60,
        "duration_text": "01:00:00",
        "sample_rate_hz": 500,
        "channels": 1,
        "electrode_placement": "RA–LL limb ECG / ECG headroom test",
        "lead_label": "Lead-II-like",
        "lead_config_key": "RA_LL_LIMB_AXIS_NPG_PRACTICAL",
        "measurement_axis": "Right wrist/right arm to left leg limb axis",
        "standard_status": (
            "Non-diagnostic NPG Lite practical polarity configuration. "
            "Useful for timing, teaching, and validation; not certified diagnostic Lead II."
        ),
        "filter": {
            "low_hz": 0.5,
            "high_hz": 40.0,
            "notch_50hz": True,
        },
        "evaluation_focus": [
            "ADC baseline",
            "low/high clipping",
            "lower/upper headroom",
            "R-peak timing usability",
        ],
        "protocol_notes": (
            "Use this first for NPG Lite ECG validation. Current local NPG Lite testing "
            "supports A0P→RA/right wrist, A0N→LL/left leg, REF→RL/right leg as the "
            "practical upright/non-clipping configuration. Textbook Lead II is LL−RA, "
            "so this should be documented as RA–LL limb ECG / Lead-II-like, not as a "
            "certified diagnostic Lead II."
        ),
    },

    "ECG_RESTING_5MIN": {
        "signal_type": "ECG",
        "protocol_name": "ECG_RESTING_5MIN",
        "display_name": "Resting ECG / HRV - 5 min",
        "description": (
            "Five-minute resting ECG for basic time-domain HRV after headroom check."
        ),
        "duration_seconds": 300,
        "duration_text": "05:00:00",
        "sample_rate_hz": 500,
        "channels": 1,
        "electrode_placement": "RA–LL limb ECG / resting ECG",
        "lead_label": "Lead-II-like",
        "lead_config_key": "RA_LL_LIMB_AXIS_NPG_PRACTICAL",
        "measurement_axis": "Right wrist/right arm to left leg limb axis",
        "standard_status": (
            "Non-diagnostic NPG Lite practical polarity configuration. "
            "Useful for timing, teaching, and validation; not certified diagnostic Lead II."
        ),
        "filter": {
            "low_hz": 0.5,
            "high_hz": 40.0,
            "notch_50hz": True,
        },
        "evaluation_focus": [
            "ADC baseline",
            "low/high clipping",
            "missing samples",
            "R-peak timing usability",
            "RR interval quality",
        ],
        "protocol_notes": (
            "Use only after ECG_HEADROOM_60S passes. HRV interpretation requires clean "
            "R-peak detection and visual verification."
        ),
    },
}


# ------------------------------------------------------------
# Non-ECG placeholder protocols
# These are intentionally conservative.
# They allow the app to remain future-proof without pretending that
# EMG/EOG/EEG pipelines are finished.
# ------------------------------------------------------------

NON_ECG_PROTOCOLS = {
    "EMG": {
        "EMG_GRADED_CONTRACTION": {
            "signal_type": "EMG",
            "protocol_name": "EMG_GRADED_CONTRACTION",
            "display_name": "Surface EMG - graded contraction",
            "description": "Basic surface EMG acquisition for rest versus contraction demonstration.",
            "duration_seconds": 60,
            "duration_text": "01:00:00",
            "sample_rate_hz": 1000,
            "channels": 1,
            "electrode_placement": "Surface EMG over muscle belly",
            "filter": {
                "low_hz": 20.0,
                "high_hz": 450.0,
                "notch_50hz": True,
            },
            "evaluation_focus": [
                "rest versus contraction separation",
                "clipping during strong contraction",
                "activation timing",
                "artifact/movement sensitivity",
            ],
            "protocol_notes": (
                "Experimental placeholder. EMG-specific analysis is not yet finalized."
            ),
        },
    },

    "EOG": {
        "EOG_BLINK_HORIZONTAL": {
            "signal_type": "EOG",
            "protocol_name": "EOG_BLINK_HORIZONTAL",
            "display_name": "EOG blink / horizontal eye movement",
            "description": "Basic EOG recording for blink and horizontal eye movement demonstration.",
            "duration_seconds": 60,
            "duration_text": "01:00:00",
            "sample_rate_hz": 500,
            "channels": 1,
            "electrode_placement": "Horizontal EOG canthus placement",
            "filter": {
                "low_hz": 0.1,
                "high_hz": 30.0,
                "notch_50hz": True,
            },
            "evaluation_focus": [
                "blink detection",
                "eye-movement polarity",
                "baseline drift",
                "saturation during large deflections",
            ],
            "protocol_notes": (
                "Experimental placeholder. EOG-specific analysis is not yet finalized."
            ),
        },

        "EOG_VERTICAL": {
            "signal_type": "EOG",
            "protocol_name": "EOG_VERTICAL",
            "display_name": "EOG vertical eye movement",
            "description": "Basic EOG recording for vertical eye movement demonstration.",
            "duration_seconds": 60,
            "duration_text": "01:00:00",
            "sample_rate_hz": 500,
            "channels": 1,
            "electrode_placement": "Vertical EOG supra/infra-orbital placement",
            "filter": {
                "low_hz": 0.1,
                "high_hz": 30.0,
                "notch_50hz": True,
            },
            "evaluation_focus": [
                "vertical eye-movement deflection",
                "blink artifact",
                "baseline drift",
                "saturation during large deflections",
            ],
            "protocol_notes": (
                "Experimental placeholder. EOG-specific analysis is not yet finalized."
            ),
        },
    },

    "EEG": {
        "EEG_EYES_OPEN_CLOSED": {
            "signal_type": "EEG",
            "protocol_name": "EEG_EYES_OPEN_CLOSED",
            "display_name": "EEG eyes open / eyes closed",
            "description": "Basic EEG alpha demonstration workflow.",
            "duration_seconds": 120,
            "duration_text": "02:00:00",
            "sample_rate_hz": 500,
            "channels": 1,
            "electrode_placement": "Occipital active, mastoid/ear reference, forehead ground",
            "filter": {
                "low_hz": 1.0,
                "high_hz": 40.0,
                "notch_50hz": True,
            },
            "evaluation_focus": [
                "noise floor",
                "movement artifact",
                "50 Hz interference",
                "eyes-open versus eyes-closed difference",
            ],
            "protocol_notes": (
                "Experimental placeholder. EEG requires stronger noise/artifact control and "
                "EEG-specific analysis is not yet finalized."
            ),
        },
    },

    "TEST": {
        "TEST_ADC_HEADROOM": {
            "signal_type": "TEST",
            "protocol_name": "TEST_ADC_HEADROOM",
            "display_name": "Generic ADC Headroom Test",
            "description": "Generic raw ADC headroom test.",
            "duration_seconds": 60,
            "duration_text": "01:00:00",
            "sample_rate_hz": 500,
            "channels": 1,
            "electrode_placement": "Test input / simulator",
            "filter": {
                "low_hz": 0.5,
                "high_hz": 40.0,
                "notch_50hz": True,
            },
            "evaluation_focus": [
                "ADC baseline",
                "low/high clipping",
                "headroom",
                "sample integrity",
            ],
            "protocol_notes": "Generic test protocol.",
        },
    },

    "CUSTOM": {
        "CUSTOM": {
            "signal_type": "CUSTOM",
            "protocol_name": "CUSTOM",
            "display_name": "Custom Recording",
            "description": "User-defined recording.",
            "duration_seconds": None,
            "duration_text": "--:--:--",
            "sample_rate_hz": 500,
            "channels": 1,
            "electrode_placement": "Custom placement",
            "filter": {
                "low_hz": 0.5,
                "high_hz": 40.0,
                "notch_50hz": True,
            },
            "evaluation_focus": [
                "ADC baseline",
                "clipping",
                "sample integrity",
            ],
            "protocol_notes": "Custom recording. Document details manually.",
        },
    },
}


# ------------------------------------------------------------
# Public API used by SetupPanel
# ------------------------------------------------------------

def get_signal_types():
    """
     Return signal types shown in Setup tab.

    v0.1-alpha exposes only ECG in the public UI.
    Other signal types are planned for later releases.
    """

    return ["ECG"]


def _get_ecg_protocols_dict():
    """
    Return ECG protocol dict from modular ECG file if available,
    otherwise use local fallback.
    """

    if isinstance(ECG_PROTOCOLS, dict) and ECG_PROTOCOLS:
        return ECG_PROTOCOLS

    return FALLBACK_ECG_PROTOCOLS


def get_protocols_for_signal(signal_type):
    """
    Return protocol summaries for the selected signal type.

    SetupPanel expects each item to contain:
    - protocol_name
    - display_name
    """

    signal = str(signal_type or "").upper()

    if signal == "ECG":
        protocols = _get_ecg_protocols_dict()
    else:
        protocols = NON_ECG_PROTOCOLS.get(signal, NON_ECG_PROTOCOLS["CUSTOM"])

    output = []

    for protocol_name, protocol in protocols.items():
        output.append({
            "signal_type": protocol.get("signal_type", signal),
            "protocol_name": protocol.get("protocol_name", protocol_name),
            "display_name": protocol.get(
                "display_name",
                protocol.get("protocol_display_name", protocol_name)
            ),
            "description": protocol.get("description", ""),
        })

    return output


def _fallback_ecg_recorder_config(protocol_name):
    """
    Build ECG recorder config from fallback definitions.
    """

    protocols = FALLBACK_ECG_PROTOCOLS
    protocol = protocols.get(str(protocol_name))

    if protocol is None:
        protocol = protocols["ECG_HEADROOM_60S"]

    return _normalise_protocol_for_recorder(protocol)


def _normalise_protocol_for_recorder(protocol):
    """
    Convert an internal protocol dictionary into the config shape expected by
    SetupPanel and RecorderPanel.
    """

    signal_type = str(protocol.get("signal_type", "CUSTOM")).upper()
    protocol_name = protocol.get("protocol_name", "CUSTOM")
    display_name = protocol.get("display_name", protocol_name)
    duration_seconds = protocol.get("duration_seconds")
    duration_text = protocol.get("duration_text", "--:--:--")

    return {
        # Identity
        "signal_type": signal_type,
        "protocol_name": protocol_name,
        "protocol_display_name": display_name,
        "display_name": display_name,
        "description": protocol.get("description", ""),

        # Recorder presets expected by RecorderPanel.apply_protocol_config()
        "recommended_channels": protocol.get("channels", 1),
        "recommended_sample_rate_hz": protocol.get("sample_rate_hz", 500),
        "recommended_duration_seconds": duration_seconds,
        "recommended_duration_text": duration_text,

        # Placement / lead / mapping metadata
        "electrode_placement": protocol.get("electrode_placement", ""),
        "lead_label": protocol.get("lead_label", ""),
        "lead_config_key": protocol.get("lead_config_key", ""),
        "measurement_axis": protocol.get("measurement_axis", ""),
        "standard_status": protocol.get("standard_status", ""),

        # Filter and machine focus
        "filter": protocol.get("filter", {}) or {},
        "evaluation_focus": protocol.get(
            "evaluation_focus",
            protocol.get("machine_evaluation_focus", [])
        ) or [],

        # Notes for setup logic panel
        "protocol_notes": protocol.get(
            "protocol_notes",
            protocol.get("recommended_use", "")
        ),
    }


def _normalise_ecg_module_config(module_config):
    """
    Convert app.signals.ecg.ecg_protocols.build_ecg_recorder_config()
    output into the config shape expected by SetupPanel and RecorderPanel.
    """

    if not isinstance(module_config, dict):
        return _fallback_ecg_recorder_config("ECG_HEADROOM_60S")

    filter_config = module_config.get("filter", {}) or {}
    lead_config = module_config.get("lead_configuration", {}) or {}
    electrode_mapping = module_config.get("electrode_pin_mapping", {}) or {}

    return {
        # Identity
        "signal_type": module_config.get("signal_type", "ECG"),
        "protocol_name": module_config.get("protocol_name", "ECG_HEADROOM_60S"),
        "protocol_display_name": module_config.get(
            "display_name",
            module_config.get("protocol_name", "ECG")
        ),
        "display_name": module_config.get(
            "display_name",
            module_config.get("protocol_name", "ECG")
        ),
        "description": module_config.get("description", ""),

        # Recorder presets
        "recommended_channels": module_config.get("channels", 1),
        "recommended_sample_rate_hz": module_config.get("sample_rate_hz", 500),
        "recommended_duration_seconds": module_config.get("duration_seconds"),
        "recommended_duration_text": module_config.get("duration_text", "--:--:--"),

        # Placement / lead / mapping metadata
        "electrode_placement": module_config.get("electrode_placement", ""),
        "lead_label": lead_config.get("lead_label", electrode_mapping.get("lead_label", "")),
        "lead_config_key": lead_config.get("lead_config_key", electrode_mapping.get("lead_config_key", "")),
        "measurement_axis": lead_config.get("measurement_axis", electrode_mapping.get("measurement_axis", "")),
        "standard_status": lead_config.get("standard_status", electrode_mapping.get("standard_status", "")),
        "electrode_pin_mapping": electrode_mapping,

        # Filter and machine focus
        "filter": filter_config,
        "evaluation_focus": module_config.get(
            "machine_evaluation_focus",
            module_config.get("evaluation_focus", [])
        ) or [],

        # Notes
        "protocol_notes": (
            module_config.get("recommended_use", "")
            + " "
            + module_config.get("interpretation_note", "")
        ).strip(),
    }


def build_recorder_config(signal_type, protocol_name):
    """
    Build a recorder configuration for the selected Setup protocol.

    This is the main bridge used by SetupPanel and then passed to RecorderPanel.
    """

    signal = str(signal_type or "CUSTOM").upper()
    protocol_name = str(protocol_name or "").strip()

    if signal == "ECG":
        if build_ecg_recorder_config is not None:
            try:
                module_config = build_ecg_recorder_config(protocol_name)
                return _normalise_ecg_module_config(module_config)
            except Exception:
                return _fallback_ecg_recorder_config(protocol_name)

        return _fallback_ecg_recorder_config(protocol_name)

    protocols = NON_ECG_PROTOCOLS.get(signal, NON_ECG_PROTOCOLS["CUSTOM"])

    protocol = protocols.get(protocol_name)

    if protocol is None:
        # fall back to first protocol in that signal group
        protocol = list(protocols.values())[0]

    return _normalise_protocol_for_recorder(protocol)


# ------------------------------------------------------------
# Convenience helpers for future use
# ------------------------------------------------------------

def get_protocol(signal_type, protocol_name):
    """
    Return the raw protocol dictionary when needed.
    """

    signal = str(signal_type or "CUSTOM").upper()
    protocol_name = str(protocol_name or "").strip()

    if signal == "ECG":
        protocols = _get_ecg_protocols_dict()
        return protocols.get(protocol_name)

    return NON_ECG_PROTOCOLS.get(signal, {}).get(protocol_name)


def list_all_protocols():
    """
    Return all protocols as a flat list.
    """

    all_items = []

    for signal in get_signal_types():
        all_items.extend(get_protocols_for_signal(signal))

    return all_items

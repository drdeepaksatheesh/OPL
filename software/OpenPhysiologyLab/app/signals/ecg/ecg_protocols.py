"""
OpenPhysiologyLab ECG protocol definitions.

This module stores static ECG protocol and lead-configuration definitions.

It should not:
- talk to hardware
- open GUI widgets
- filter data
- detect peaks
- write recording files

Purpose:
Keep ECG protocol naming, electrode-to-pin mapping, filter presets,
and lead-configuration documentation in one place.
"""


ECG_SIGNAL_TYPE = "ECG"


# ------------------------------------------------------------
# Lead / axis configurations
# ------------------------------------------------------------

ECG_LEAD_CONFIGURATIONS = {
    "RA_LL_LIMB_AXIS_NPG_PRACTICAL": {
        "lead_config_key": "RA_LL_LIMB_AXIS_NPG_PRACTICAL",
        "display_label": "RA–LL limb ECG / Lead-II-like",
        "measurement_axis": "Right arm/right wrist to left leg limb axis",
        "lead_label": "Lead-II-like",
        "standard_status": (
            "Non-diagnostic NPG Lite practical polarity configuration. "
            "Useful for timing, teaching, and validation. Not a certified diagnostic Lead II."
        ),
        "textbook_equivalent": (
            "Textbook Lead II is LL − RA: left leg positive, right arm negative, "
            "right leg reference/ground."
        ),
        "npg_lite_practical_mapping": {
            "A0P": "Right wrist / RA",
            "A0N": "Left leg / LL",
            "REF": "Right leg / RL",
        },
        "body_mapping": {
            "Right wrist / RA": "A0P / CH input P",
            "Left leg / LL": "A0N / CH input N",
            "Right leg / RL": "REF / GND",
        },
        "local_polarity_evidence": {
            "test_1": {
                "mapping": "A0P->RA/right wrist, A0N->LL/left leg, REF->RL/right leg",
                "display_polarity_without_app_inversion": "upright / positive R peaks",
                "machine_status": "PASS",
                "adc_result": "No low/high clipping in local test",
            },
            "test_2": {
                "mapping": "A0P->LL/left leg, A0N->RA/right wrist, REF->RL/right leg",
                "display_polarity_without_app_inversion": "inverted / negative R peaks",
                "machine_status": "CAUTION",
                "adc_result": "Low-rail clipping observed in local test",
            },
        },
        "documentation_note": (
            "This configuration uses RA–LL limb placement with RL reference. "
            "Because the NPG Lite/OpenPhysiologyLab chain showed upright non-clipping ECG "
            "with A0P on RA and A0N on LL, this is documented as a practical NPG Lite "
            "polarity configuration rather than strict textbook Lead II amplifier polarity."
        ),
    },

    "TEXTBOOK_LEAD_I_LA_MINUS_RA": {
        "lead_config_key": "TEXTBOOK_LEAD_I_LA_MINUS_RA",
        "display_label": "Textbook Lead I",
        "measurement_axis": "LA − RA",
        "lead_label": "Lead I",
        "standard_status": "Reference definition only; not yet validated in NPG Lite workflow.",
        "textbook_equivalent": "Lead I = LA − RA.",
        "npg_lite_practical_mapping": {
            "A0P": "Left arm / LA",
            "A0N": "Right arm / RA",
            "REF": "Right leg / RL",
        },
        "documentation_note": "Future configuration. Requires validation for polarity and ADC headroom.",
    },

    "TEXTBOOK_LEAD_II_LL_MINUS_RA": {
        "lead_config_key": "TEXTBOOK_LEAD_II_LL_MINUS_RA",
        "display_label": "Textbook Lead II",
        "measurement_axis": "LL − RA",
        "lead_label": "Lead II",
        "standard_status": "Reference definition only; NPG Lite polarity/headroom must be validated.",
        "textbook_equivalent": "Lead II = LL − RA.",
        "npg_lite_practical_mapping": {
            "A0P": "Left leg / LL",
            "A0N": "Right arm / RA",
            "REF": "Right leg / RL",
        },
        "documentation_note": (
            "In local NPG Lite polarity testing, this opposite mapping produced inverted ECG "
            "and low-rail clipping. Use cautiously and document results."
        ),
    },

    "TEXTBOOK_LEAD_III_LL_MINUS_LA": {
        "lead_config_key": "TEXTBOOK_LEAD_III_LL_MINUS_LA",
        "display_label": "Textbook Lead III",
        "measurement_axis": "LL − LA",
        "lead_label": "Lead III",
        "standard_status": "Reference definition only; not yet validated in NPG Lite workflow.",
        "textbook_equivalent": "Lead III = LL − LA.",
        "npg_lite_practical_mapping": {
            "A0P": "Left leg / LL",
            "A0N": "Left arm / LA",
            "REF": "Right leg / RL",
        },
        "documentation_note": "Future configuration. Requires validation for polarity and ADC headroom.",
    },
}


# ------------------------------------------------------------
# Filter presets
# ------------------------------------------------------------

ECG_FILTER_PRESETS = {
    "basic_ecg_0_5_40_notch": {
        "low_hz": 0.5,
        "high_hz": 40.0,
        "notch_50hz": True,
        "description": "Basic ECG review/analysis filter: 0.5–40 Hz with 50 Hz notch.",
    },
    "wide_ecg_0_05_100_notch": {
        "low_hz": 0.05,
        "high_hz": 100.0,
        "notch_50hz": True,
        "description": "Wider ECG morphology-oriented filter. Use cautiously with NPG Lite.",
    },
}


# ------------------------------------------------------------
# Protocol definitions
# ------------------------------------------------------------

ECG_PROTOCOLS = {
    "ECG_HEADROOM_60S": {
        "signal_type": "ECG",
        "protocol_name": "ECG_HEADROOM_60S",
        "display_name": "ECG Headroom Test - 60 s",
        "description": (
            "Short ECG acquisition intended to evaluate ADC headroom, clipping, "
            "baseline position, R-peak timing usability, and basic morphology usability."
        ),
        "duration_seconds": 60,
        "duration_text": "01:00:00",
        "sample_rate_hz": 500,
        "channels": 1,
        "lead_config_key": "RA_LL_LIMB_AXIS_NPG_PRACTICAL",
        "electrode_placement": "RA–LL limb ECG / ECG headroom test",
        "filter_preset_key": "basic_ecg_0_5_40_notch",
        "machine_evaluation_focus": [
            "ADC baseline",
            "low/high clipping",
            "lower/upper headroom",
            "R-peak timing usability",
        ],
        "recommended_use": (
            "Use this first for NPG Lite ECG validation before longer recordings."
        ),
        "interpretation_note": (
            "PASS/CAUTION/FAIL describes machine-session ADC behaviour. "
            "A CAUTION ECG may still be usable for RR timing if R peaks are correct, "
            "but clipped morphology or amplitude should not be trusted."
        ),
    },

    "ECG_RESTING_5MIN": {
        "signal_type": "ECG",
        "protocol_name": "ECG_RESTING_5MIN",
        "display_name": "Resting ECG / HRV - 5 min",
        "description": (
            "Five-minute resting ECG intended for basic time-domain HRV workflows "
            "after headroom has already been checked."
        ),
        "duration_seconds": 300,
        "duration_text": "05:00:00",
        "sample_rate_hz": 500,
        "channels": 1,
        "lead_config_key": "RA_LL_LIMB_AXIS_NPG_PRACTICAL",
        "electrode_placement": "RA–LL limb ECG / resting ECG",
        "filter_preset_key": "basic_ecg_0_5_40_notch",
        "machine_evaluation_focus": [
            "ADC baseline",
            "low/high clipping",
            "missing samples",
            "R-peak timing usability",
            "RR interval quality",
        ],
        "recommended_use": (
            "Use after ECG_HEADROOM_60S has passed. Intended for resting HR/RR/HRV analysis."
        ),
        "interpretation_note": (
            "HRV interpretation requires clean R-peak detection and visual verification. "
            "This app currently provides basic time-domain HRV only."
        ),
    },
}


RAW_SIGNAL_POLICY = {
    "raw_csv_contains": "Original ADC values from device stream",
    "raw_csv_modified_by_recorder_display_inversion": False,
    "raw_csv_modified_by_analysis_inversion": False,
    "raw_csv_modified_by_filtering": False,
    "filtering_location": "In-memory analysis signal generated from raw.csv",
    "peak_detection_source": "Filtered-from-raw analysis signal",
    "adc_headroom_source": "Original raw ADC values",
}


def get_ecg_protocol(protocol_name):
    return ECG_PROTOCOLS.get(str(protocol_name))


def list_ecg_protocols():
    return list(ECG_PROTOCOLS.values())


def get_ecg_filter_preset(preset_key):
    return ECG_FILTER_PRESETS.get(str(preset_key))


def get_ecg_lead_configuration(lead_config_key):
    return ECG_LEAD_CONFIGURATIONS.get(str(lead_config_key))


def get_default_ecg_lead_configuration():
    return ECG_LEAD_CONFIGURATIONS["RA_LL_LIMB_AXIS_NPG_PRACTICAL"]


def build_ecg_electrode_pin_mapping(protocol_name=None, user_entered_placement=None):
    """
    Build electrode_pin_mapping metadata for ECG.

    This returns documentation metadata only.
    It does not modify raw.csv, plotted signal, filtering, or machine evaluation.
    """

    protocol = get_ecg_protocol(protocol_name) if protocol_name else None

    if protocol is None:
        lead_config = get_default_ecg_lead_configuration()
        protocol_name = protocol_name or "UNKNOWN_ECG_PROTOCOL"
    else:
        lead_config = get_ecg_lead_configuration(
            protocol.get("lead_config_key", "RA_LL_LIMB_AXIS_NPG_PRACTICAL")
        ) or get_default_ecg_lead_configuration()

    return {
        "schema_version": "0.2",
        "signal_type": "ECG",
        "protocol_name": protocol_name,
        "lead_config_key": lead_config.get("lead_config_key"),
        "lead_label": lead_config.get("lead_label"),
        "display_label": lead_config.get("display_label"),
        "measurement_axis": lead_config.get("measurement_axis"),
        "configuration_label": lead_config.get("display_label"),
        "standard_status": lead_config.get("standard_status"),
        "device_family": "NPG Lite / compatible",
        "pin_mapping": dict(lead_config.get("npg_lite_practical_mapping", {})),
        "body_mapping": dict(lead_config.get("body_mapping", {})),
        "textbook_equivalent": lead_config.get("textbook_equivalent"),
        "textbook_lead_ii_note": lead_config.get("textbook_equivalent"),
        "documentation_note": lead_config.get("documentation_note"),
        "local_polarity_evidence": dict(lead_config.get("local_polarity_evidence", {})),
        "raw_signal_policy": (
            "raw.csv stores original ADC values. Display inversion and review filtering "
            "are display/analysis operations and must not overwrite raw.csv."
        ),
        "user_entered_placement": user_entered_placement or "",
    }


def build_ecg_recorder_config(protocol_name):
    """
    Build recorder config from an ECG protocol.
    """

    protocol = get_ecg_protocol(protocol_name)

    if protocol is None:
        raise ValueError(f"Unknown ECG protocol: {protocol_name}")

    filter_preset = get_ecg_filter_preset(protocol.get("filter_preset_key"))
    lead_config = get_ecg_lead_configuration(protocol.get("lead_config_key"))

    return {
        "signal_type": protocol.get("signal_type", "ECG"),
        "protocol_name": protocol.get("protocol_name"),
        "display_name": protocol.get("display_name"),
        "description": protocol.get("description"),
        "duration_seconds": protocol.get("duration_seconds"),
        "duration_text": protocol.get("duration_text"),
        "sample_rate_hz": protocol.get("sample_rate_hz"),
        "channels": protocol.get("channels"),
        "electrode_placement": protocol.get("electrode_placement"),
        "lead_configuration": lead_config,
        "electrode_pin_mapping": build_ecg_electrode_pin_mapping(
            protocol_name=protocol.get("protocol_name"),
            user_entered_placement=protocol.get("electrode_placement"),
        ),
        "filter": filter_preset,
        "machine_evaluation_focus": protocol.get("machine_evaluation_focus", []),
        "recommended_use": protocol.get("recommended_use", ""),
        "interpretation_note": protocol.get("interpretation_note", ""),
        "raw_signal_policy": RAW_SIGNAL_POLICY,
    }


def build_ecg_protocol_summary(protocol_name):
    protocol = get_ecg_protocol(protocol_name)

    if protocol is None:
        return f"Unknown ECG protocol: {protocol_name}"

    config = build_ecg_recorder_config(protocol_name)
    filt = config.get("filter", {}) or {}
    mapping = config.get("electrode_pin_mapping", {}).get("pin_mapping", {}) or {}
    lead_config = config.get("lead_configuration", {}) or {}

    lines = [
        f"Protocol: {config.get('protocol_name')}",
        f"Display name: {config.get('display_name')}",
        f"Signal type: {config.get('signal_type')}",
        f"Lead label: {lead_config.get('lead_label')}",
        f"Measurement axis: {lead_config.get('measurement_axis')}",
        f"Standard status: {lead_config.get('standard_status')}",
        f"Duration: {config.get('duration_seconds')} s",
        f"Sample rate: {config.get('sample_rate_hz')} Hz",
        f"Channels: {config.get('channels')}",
        "",
        "Filter:",
        f"Low Hz: {filt.get('low_hz')}",
        f"High Hz: {filt.get('high_hz')}",
        f"50 Hz notch: {filt.get('notch_50hz')}",
        "",
        "NPG Lite practical electrode pin mapping:",
        f"A0P: {mapping.get('A0P')}",
        f"A0N: {mapping.get('A0N')}",
        f"REF: {mapping.get('REF')}",
    ]

    return "\n".join(lines)

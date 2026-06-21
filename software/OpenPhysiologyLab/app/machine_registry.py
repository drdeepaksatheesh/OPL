from pathlib import Path
from datetime import datetime
import json
import hashlib
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MACHINE_PROFILES_DIR = PROJECT_ROOT / "machine_profiles"

ADC_DEFAULT_MIN = 0
ADC_DEFAULT_MAX = 4095


def ensure_machine_profiles_dir():
    MACHINE_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    return MACHINE_PROFILES_DIR


def make_json_safe(value):
    if isinstance(value, np.ndarray):
        return value.tolist()

    if isinstance(value, np.integer):
        return int(value)

    if isinstance(value, np.floating):
        return float(value)

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {str(k): make_json_safe(v) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [make_json_safe(v) for v in value]

    return value


def safe_text(value):
    if value is None:
        return "unknown"

    try:
        value = str(value).strip()
    except Exception:
        return "unknown"

    return value if value else "unknown"


def sanitize_name(name):
    name = safe_text(name)

    invalid = '<>:"/\\|?*'

    for ch in invalid:
        name = name.replace(ch, "_")

    name = name.replace(" ", "_")

    while "__" in name:
        name = name.replace("__", "_")

    name = name.strip("_")

    return name if name else "unknown"


def make_machine_uid(identity=None, device_id=None, port=None):
    """
    Local practical machine UID.

    Current limitation:
    NPG Lite firmware may not expose a true immutable hardware serial number yet.
    So this UID is based on user device label + firmware identity + port.
    Later firmware should expose a true unique device ID.
    """

    identity_text = safe_text(identity)
    device_text = safe_text(device_id)
    port_text = safe_text(port)

    base = f"device_id={device_text}|identity={identity_text}|port={port_text}"
    digest = hashlib.sha1(base.encode("utf-8", errors="ignore")).hexdigest()[:12]

    readable = sanitize_name(device_text)

    return f"{readable}_{digest}"


def get_profile_folder(machine_uid):
    ensure_machine_profiles_dir()
    folder = MACHINE_PROFILES_DIR / sanitize_name(machine_uid)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def profile_path(machine_uid):
    return get_profile_folder(machine_uid) / "machine_profile.json"


def load_machine_profile(machine_uid):
    path = profile_path(machine_uid)

    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_machine_profile(profile):
    machine_uid = profile.get("machine_uid")

    if not machine_uid:
        raise ValueError("machine_uid missing from machine profile.")

    path = profile_path(machine_uid)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(make_json_safe(profile), f, indent=4)

    return path


def get_or_create_machine_profile_snapshot(
    identity=None,
    status=None,
    device_id=None,
    port=None,
    baudrate=None,
    sample_rate_hz=None,
    channels=None,
    software_name="OpenPhysiologyLab"
):
    machine_uid = make_machine_uid(
        identity=identity,
        device_id=device_id,
        port=port
    )

    now = datetime.now().isoformat(timespec="seconds")

    profile = load_machine_profile(machine_uid)

    if profile is None:
        profile = {
            "machine_uid": machine_uid,
            "profile_schema_version": "0.1",
            "software": software_name,
            "created_datetime": now,
            "updated_datetime": now,
            "device_family": "NPG Lite / compatible",
            "device_id_user_label": safe_text(device_id),
            "identity_history": [],
            "connection_history": [],
            "latest_identity": None,
            "latest_status": None,
            "latest_connection": None,
            "latest_evaluation_report": None,
            "notes": (
                "This is a local OpenPhysiologyLab machine profile. "
                "Until firmware exposes a true unique hardware ID, the UID is derived from "
                "device_id, firmware identity text, and port. This may change if the same device "
                "is moved across ports or renamed."
            )
        }

    profile["updated_datetime"] = now
    profile["device_id_user_label"] = safe_text(device_id)
    profile["latest_identity"] = identity
    profile["latest_status"] = status

    latest_connection = {
        "datetime": now,
        "port": safe_text(port),
        "baudrate": baudrate,
        "sample_rate_hz": sample_rate_hz,
        "channels": channels
    }

    profile["latest_connection"] = latest_connection

    identity_history = profile.get("identity_history", [])
    identity_history.append({
        "datetime": now,
        "identity": identity
    })
    profile["identity_history"] = identity_history[-20:]

    connection_history = profile.get("connection_history", [])
    connection_history.append(latest_connection)
    profile["connection_history"] = connection_history[-20:]

    save_machine_profile(profile)

    return {
        "machine_uid": profile["machine_uid"],
        "profile_path": str(profile_path(profile["machine_uid"])),
        "device_family": profile.get("device_family"),
        "device_id_user_label": profile.get("device_id_user_label"),
        "latest_identity": profile.get("latest_identity"),
        "latest_status": profile.get("latest_status"),
        "latest_connection": profile.get("latest_connection"),
        "latest_evaluation_report": profile.get("latest_evaluation_report"),
        "profile_note": profile.get("notes")
    }


def list_machine_profiles():
    ensure_machine_profiles_dir()

    profiles = []

    for path in sorted(MACHINE_PROFILES_DIR.glob("*/machine_profile.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                profiles.append(json.load(f))
        except Exception:
            continue

    return profiles


def get_latest_machine_evaluation_snapshot(machine_uid):
    """
    Return latest useful machine evaluation.

    Priority:
    1. Latest session_machine_evaluation
    2. Latest manual/profile evaluation

    Reason:
    Manual profile evaluation only proves the profile exists.
    Session evaluation tells whether a real recording had acceptable ADC headroom.
    """

    if not machine_uid:
        return None

    folder = get_profile_folder(machine_uid)
    eval_dir = folder / "machine_evaluations"

    if not eval_dir.exists():
        return None

    files = sorted(
        eval_dir.glob("machine_evaluation_report_*.json"),
        key=lambda p: p.stat().st_mtime
    )

    if not files:
        return None

    loaded = []

    for file_path in files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                report = json.load(f)

            loaded.append((file_path, report))
        except Exception:
            continue

    if not loaded:
        return None

    session_reports = [
        item for item in loaded
        if item[1].get("evaluation_type") == "session_machine_evaluation"
    ]

    if session_reports:
        latest_path, latest_report = session_reports[-1]
    else:
        latest_path, latest_report = loaded[-1]

    return {
        "report_path": str(latest_path),
        "evaluation_datetime": latest_report.get("evaluation_datetime"),
        "evaluation_type": latest_report.get("evaluation_type"),
        "signal_type": latest_report.get("signal_type"),
        "protocol_name": latest_report.get("protocol_name"),
        "overall_status": latest_report.get("overall_status"),
        "summary": latest_report.get("summary"),
        "recommendations": latest_report.get("recommendations"),
        "channel_summary": latest_report.get("channel_summary"),
        "usability": latest_report.get("usability")
    }


def classify_channel_status(low_clip_pct, high_clip_pct, lower_headroom, upper_headroom):
    if low_clip_pct >= 1.0 or high_clip_pct >= 1.0:
        return "FAIL"

    if low_clip_pct > 0.0 or high_clip_pct > 0.0:
        return "CAUTION"

    if lower_headroom < 250 or upper_headroom < 250:
        return "CAUTION"

    return "PASS"


def build_session_machine_evaluation(
    rows,
    sample_rate_hz=500,
    channels=1,
    adc_min=ADC_DEFAULT_MIN,
    adc_max=ADC_DEFAULT_MAX,
    machine_uid=None,
    signal_type=None,
    protocol_name=None,
    source="recording_session"
):
    """
    Session-level machine evaluation from raw rows.

    This checks:
    - ADC baseline
    - low/high headroom
    - clipping
    - channel validity

    It does not modify data.
    """

    now = datetime.now().isoformat(timespec="seconds")

    rows = rows or []

    try:
        sample_rate_hz = float(sample_rate_hz)
    except Exception:
        sample_rate_hz = 500.0

    try:
        channels = int(channels)
    except Exception:
        channels = 1

    adc_midpoint = (float(adc_min) + float(adc_max)) / 2.0
    adc_span = float(adc_max) - float(adc_min)

    signal_type_text = safe_text(signal_type).upper()
    protocol_text = safe_text(protocol_name)

    report = {
        "machine_uid": machine_uid,
        "evaluation_schema_version": "0.1",
        "evaluation_datetime": now,
        "evaluation_type": "session_machine_evaluation",
        "signal_type": signal_type_text,
        "protocol_name": protocol_text,
        "source": source,
        "adc_range": {
            "adc_min": adc_min,
            "adc_max": adc_max,
            "adc_midpoint": adc_midpoint,
            "adc_span": adc_span
        },
        "recording_context": {
            "sample_rate_hz": sample_rate_hz,
            "channels": channels,
            "samples": len(rows)
        },
        "channel_summary": {},
        "overall_status": "UNKNOWN",
        "summary": "",
        "recommendations": [],
        "usability": {}
    }

    if len(rows) == 0:
        report["overall_status"] = "FAIL"
        report["summary"] = "No samples available for machine evaluation."
        report["recommendations"] = ["Check connection and repeat recording."]
        return report

    statuses = []
    recommendations = []

    for ch_index in range(1, channels + 1):
        ch_name = f"ch{ch_index}"
        values = []

        for row in rows:
            value = row.get(ch_name)

            if value is None:
                continue

            try:
                values.append(float(value))
            except Exception:
                continue

        y = np.asarray(values, dtype=float)
        y = y[np.isfinite(y)]

        if y.size == 0:
            ch_report = {
                "status": "FAIL",
                "samples": 0,
                "summary": "No valid samples."
            }
            report["channel_summary"][ch_name] = ch_report
            statuses.append("FAIL")
            continue

        low_clip_count = int(np.sum(y <= float(adc_min) + 1.0))
        high_clip_count = int(np.sum(y >= float(adc_max) - 1.0))
        samples = int(y.size)

        low_clip_pct = (low_clip_count / samples) * 100.0
        high_clip_pct = (high_clip_count / samples) * 100.0

        y_min = float(np.min(y))
        y_max = float(np.max(y))
        mean = float(np.mean(y))
        median = float(np.median(y))
        sd = float(np.std(y))
        ptp = float(np.ptp(y))

        lower_headroom = median - float(adc_min)
        upper_headroom = float(adc_max) - median
        midpoint_offset = median - adc_midpoint

        status = classify_channel_status(
            low_clip_pct=low_clip_pct,
            high_clip_pct=high_clip_pct,
            lower_headroom=lower_headroom,
            upper_headroom=upper_headroom
        )

        statuses.append(status)

        ch_recommendations = []

        if low_clip_count > 0 and high_clip_count == 0:
            ch_recommendations.append(
                "LOW-rail clipping detected with unused upper headroom. "
                "Try reversing the two measuring electrodes or improving analog baseline centering."
            )

        if high_clip_count > 0 and low_clip_count == 0:
            ch_recommendations.append(
                "HIGH-rail clipping detected. Check polarity, reduce amplitude, or improve baseline centering."
            )

        if low_clip_count > 0 and high_clip_count > 0:
            ch_recommendations.append(
                "Both LOW and HIGH clipping detected. Signal amplitude may be too large for the ADC range."
            )

        if lower_headroom < 250:
            ch_recommendations.append(
                "Low-side ADC headroom is poor. Baseline is too close to lower rail."
            )

        if upper_headroom < 250:
            ch_recommendations.append(
                "High-side ADC headroom is poor. Baseline is too close to upper rail."
            )

        if abs(midpoint_offset) > adc_span * 0.20:
            ch_recommendations.append(
                "Baseline is far from ADC midpoint. This is a machine/session headroom issue."
            )

        ch_report = {
            "status": status,
            "samples": samples,
            "min": y_min,
            "max": y_max,
            "mean": mean,
            "median_baseline": median,
            "std": sd,
            "peak_to_peak": ptp,
            "low_clip_count": low_clip_count,
            "high_clip_count": high_clip_count,
            "low_clip_percent": low_clip_pct,
            "high_clip_percent": high_clip_pct,
            "estimated_low_clipped_duration_s": low_clip_count / sample_rate_hz if sample_rate_hz > 0 else None,
            "estimated_high_clipped_duration_s": high_clip_count / sample_rate_hz if sample_rate_hz > 0 else None,
            "lower_headroom_adc": lower_headroom,
            "upper_headroom_adc": upper_headroom,
            "adc_midpoint_offset": midpoint_offset,
            "recommendations": ch_recommendations
        }

        report["channel_summary"][ch_name] = ch_report
        recommendations.extend([f"{ch_name}: {r}" for r in ch_recommendations])

    if "FAIL" in statuses:
        overall = "FAIL"
    elif "CAUTION" in statuses:
        overall = "CAUTION"
    elif "PASS" in statuses:
        overall = "PASS"
    else:
        overall = "UNKNOWN"

    report["overall_status"] = overall

    if overall == "PASS":
        report["summary"] = "Machine/session ADC headroom passed for recorded channels."
    elif overall == "CAUTION":
        report["summary"] = "Machine/session ADC headroom requires caution. Clipping or poor baseline centering was detected."
    elif overall == "FAIL":
        report["summary"] = "Machine/session evaluation failed. Severe clipping, missing samples, or invalid channel data detected."
    else:
        report["summary"] = "Machine/session evaluation status unknown."

    if not recommendations:
        recommendations = ["No major ADC headroom action required for this session."]

    report["recommendations"] = recommendations

    usability = {
        "timing": "UNKNOWN",
        "amplitude": "UNKNOWN",
        "morphology": "UNKNOWN",
        "teaching_demo": "UNKNOWN",
        "interpretation": ""
    }

    signal = signal_type_text

    if signal == "ECG":
        if overall == "PASS":
            usability.update({
                "timing": "PASS",
                "amplitude": "PASS",
                "morphology": "PASS",
                "teaching_demo": "PASS",
                "interpretation": "ECG ADC headroom acceptable for timing and basic morphology."
            })
        elif overall == "CAUTION":
            usability.update({
                "timing": "PASS",
                "amplitude": "CAUTION",
                "morphology": "CAUTION",
                "teaching_demo": "PASS",
                "interpretation": (
                    "ECG timing may remain usable, but clipped beats or poor headroom "
                    "make amplitude/morphology cautious."
                )
            })
        else:
            usability.update({
                "timing": "CAUTION",
                "amplitude": "FAIL",
                "morphology": "FAIL",
                "teaching_demo": "CAUTION",
                "interpretation": "ECG session has serious ADC/headroom problems."
            })

    elif signal == "EMG":
        if overall == "PASS":
            usability.update({
                "timing": "PASS",
                "amplitude": "PASS",
                "morphology": "NOT_APPLICABLE",
                "teaching_demo": "PASS",
                "interpretation": "EMG ADC headroom acceptable for activation and relative amplitude."
            })
        elif overall == "CAUTION":
            usability.update({
                "timing": "PASS",
                "amplitude": "CAUTION",
                "morphology": "NOT_APPLICABLE",
                "teaching_demo": "PASS",
                "interpretation": (
                    "EMG activation timing may be usable, but strong contractions may clip. "
                    "Use caution for amplitude quantification."
                )
            })
        else:
            usability.update({
                "timing": "CAUTION",
                "amplitude": "FAIL",
                "morphology": "NOT_APPLICABLE",
                "teaching_demo": "CAUTION",
                "interpretation": "EMG session has serious ADC/headroom problems."
            })

    elif signal == "EOG":
        if overall == "PASS":
            usability.update({
                "timing": "PASS",
                "amplitude": "PASS",
                "morphology": "NOT_APPLICABLE",
                "teaching_demo": "PASS",
                "interpretation": "EOG ADC headroom acceptable for blink/eye movement detection."
            })
        elif overall == "CAUTION":
            usability.update({
                "timing": "PASS",
                "amplitude": "CAUTION",
                "morphology": "NOT_APPLICABLE",
                "teaching_demo": "PASS",
                "interpretation": (
                    "EOG timing/direction may be usable, but amplitude is cautious due to clipping or baseline drift."
                )
            })
        else:
            usability.update({
                "timing": "CAUTION",
                "amplitude": "FAIL",
                "morphology": "NOT_APPLICABLE",
                "teaching_demo": "CAUTION",
                "interpretation": "EOG session has serious ADC/headroom problems."
            })

    elif signal == "EEG":
        if overall == "PASS":
            usability.update({
                "timing": "PASS",
                "amplitude": "CAUTION",
                "morphology": "NOT_APPLICABLE",
                "teaching_demo": "CAUTION",
                "interpretation": "ADC headroom passed, but EEG requires separate noise/band-power evaluation."
            })
        elif overall == "CAUTION":
            usability.update({
                "timing": "CAUTION",
                "amplitude": "CAUTION",
                "morphology": "NOT_APPLICABLE",
                "teaching_demo": "CAUTION",
                "interpretation": "EEG needs detailed noise and alpha/band-power evaluation. ADC headroom alone is insufficient."
            })
        else:
            usability.update({
                "timing": "CAUTION",
                "amplitude": "FAIL",
                "morphology": "NOT_APPLICABLE",
                "teaching_demo": "FAIL",
                "interpretation": "EEG session has serious ADC/headroom problems."
            })

    else:
        usability["interpretation"] = (
            "Signal-specific usability rules are not defined yet for this mode. "
            "Generic ADC headroom status is available."
        )

    report["usability"] = usability

    return make_json_safe(report)


def save_machine_evaluation_report(machine_uid, report):
    if not machine_uid:
        return None

    folder = get_profile_folder(machine_uid)
    eval_dir = folder / "machine_evaluations"
    eval_dir.mkdir(parents=True, exist_ok=True)

    dt = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = eval_dir / f"machine_evaluation_report_{dt}.json"

    report = make_json_safe(report)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=4)

    profile = load_machine_profile(machine_uid)

    if profile is not None:
        profile["latest_evaluation_report"] = {
            "report_path": str(path),
            "evaluation_datetime": report.get("evaluation_datetime"),
            "evaluation_type": report.get("evaluation_type"),
            "signal_type": report.get("signal_type"),
            "protocol_name": report.get("protocol_name"),
            "overall_status": report.get("overall_status"),
            "summary": report.get("summary")
        }
        profile["updated_datetime"] = datetime.now().isoformat(timespec="seconds")
        save_machine_profile(profile)

    return path


def build_manual_machine_evaluation(machine_uid=None):
    now = datetime.now().isoformat(timespec="seconds")

    return {
        "machine_uid": machine_uid,
        "evaluation_schema_version": "0.1",
        "evaluation_datetime": now,
        "evaluation_type": "manual_profile_evaluation",
        "signal_type": "PROFILE",
        "protocol_name": "MANUAL_MACHINE_PROFILE_CHECK",
        "overall_status": "BASELINE_ONLY",
        "summary": (
            "Machine profile exists. Full electronic self-test is not available yet. "
            "Session ADC headroom is evaluated automatically during recordings."
        ),
        "recommendations": [
            "Record a short calibration ECG/test signal and review session_machine_evaluation in metadata.json.",
            "Later firmware should expose unique hardware ID, LCD/device states, ADC baseline, battery, and status commands."
        ],
        "channel_summary": {},
        "usability": {
            "timing": "UNKNOWN",
            "amplitude": "UNKNOWN",
            "morphology": "UNKNOWN",
            "teaching_demo": "UNKNOWN",
            "interpretation": "Manual profile evaluation only. Use session recording for signal-specific evaluation."
        }
    }

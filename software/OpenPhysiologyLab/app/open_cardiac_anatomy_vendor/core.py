"""Data and processing primitives for Open 4D Cardiac Anatomy.

The internal array convention is ``(time, z, y, x)``.  Keeping the core free
of Qt makes it testable without a display and lets future segmentation models
plug into the same study object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional, Tuple, List

import numpy as np
from scipy import ndimage

try:
    import nibabel as nib
except Exception:  # Optional until the Cardiac MRI tab is used.
    nib = None

try:
    from skimage.measure import marching_cubes
    from skimage.registration import optical_flow_tvl1
    from skimage.transform import warp
except Exception:  # Optional until reconstruction/propagation is used.
    marching_cubes = None
    optical_flow_tvl1 = None
    warp = None


class MissingImagingDependency(RuntimeError):
    """Raised when an optional cardiac-imaging dependency is unavailable."""


@dataclass(frozen=True)
class ChamberDefinition:
    short_name: str
    display_name: str
    colour_rgb: Tuple[int, int, int]


CHAMBERS: Dict[int, ChamberDefinition] = {
    1: ChamberDefinition("LV", "Left ventricle", (255, 92, 92)),
    2: ChamberDefinition("RV", "Right ventricle", (37, 216, 255)),
    3: ChamberDefinition("LA", "Left atrium", (255, 63, 203)),
    4: ChamberDefinition("RA", "Right atrium", (80, 200, 120)),
}

# Labels 1-4 remain stable for backward compatibility.  Later labels extend the
# same source-faithful volume into an anatomy model.  A label is only anatomy;
# whether it was measured, propagated or registered is stored separately.
ANATOMY: Dict[int, ChamberDefinition] = {
    **CHAMBERS,
    5: ChamberDefinition("MYO", "Myocardium / epicardium", (184, 72, 72)),
    6: ChamberDefinition("AO", "Aorta", (244, 116, 96)),
    7: ChamberDefinition("PA", "Pulmonary trunk and arteries", (92, 155, 255)),
    8: ChamberDefinition("SVC", "Superior vena cava", (75, 130, 240)),
    9: ChamberDefinition("IVC", "Inferior vena cava", (75, 130, 240)),
    10: ChamberDefinition("PV", "Pulmonary veins", (225, 105, 130)),
    11: ChamberDefinition("CA", "Coronary arteries", (255, 205, 70)),
    12: ChamberDefinition("MV", "Mitral valve leaflets", (238, 225, 189)),
    13: ChamberDefinition("TV", "Tricuspid valve leaflets", (232, 218, 181)),
    14: ChamberDefinition("AV", "Aortic valve leaflets", (250, 230, 176)),
    15: ChamberDefinition("PVL", "Pulmonary valve leaflets", (222, 232, 216)),
    16: ChamberDefinition("PM", "Papillary muscles", (171, 91, 86)),
    17: ChamberDefinition("CV", "Cardiac veins", (82, 118, 174)),
}

EVIDENCE_LEVELS = (
    "measured", "statistical", "propagated", "registered", "synthetic", "unknown"
)

_CHAMBER_ALIASES = {
    "LV": 1,
    "LEFTVENTRICLE": 1,
    "RV": 2,
    "RIGHTVENTRICLE": 2,
    "LA": 3,
    "LEFTATRIUM": 3,
    "RA": 4,
    "RIGHTATRIUM": 4,
}
_ANATOMY_ALIASES = {
    **_CHAMBER_ALIASES,
    "MYO": 5, "MYOCARDIUM": 5, "EPICARDIUM": 5,
    "AO": 6, "AORTA": 6,
    "PA": 7, "PULMONARYARTERY": 7, "PULMONARYTRUNK": 7,
    "SVC": 8, "SUPERIORVENACAVA": 8,
    "IVC": 9, "INFERIORVENACAVA": 9,
    "PV": 10, "PULMONARYVEINS": 10,
    "CA": 11, "CORONARY": 11, "CORONARIES": 11, "CORONARYARTERIES": 11,
    "MV": 12, "MITRAL": 12, "MITRALVALVE": 12,
    "TV": 13, "TRICUSPID": 13, "TRICUSPIDVALVE": 13,
    "AV": 14, "AORTICVALVE": 14,
    "PVL": 15, "PULMONARYVALVE": 15,
    "PM": 16, "PAPILLARY": 16, "PAPILLARYMUSCLES": 16,
    "CV": 17, "CARDIACVEINS": 17,
}


def parse_label_mapping(text: str) -> Dict[int, int]:
    """Parse ``LV=1,RV=2,LA=3,RA=4`` into input-label -> internal-label."""

    mapping: Dict[int, int] = {}
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"Expected NAME=NUMBER, got: {part!r}")
        name, value = (item.strip() for item in part.split("=", 1))
        key = "".join(ch for ch in name.upper() if ch.isalnum())
        if key not in _CHAMBER_ALIASES:
            raise ValueError(f"Unknown chamber name: {name!r}")
        input_value = int(value)
        if input_value <= 0:
            raise ValueError("Label value 0 is reserved for background")
        if input_value in mapping:
            raise ValueError(f"Input label {input_value} was assigned more than once")
        mapping[input_value] = _CHAMBER_ALIASES[key]
    if not mapping:
        raise ValueError("No label mapping was supplied")
    return mapping


def parse_anatomy_mapping(text: str) -> Dict[int, int]:
    """Parse an explicit source-label mapping for chambers and external anatomy."""

    mapping: Dict[int, int] = {}
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"Expected NAME=NUMBER, got: {part!r}")
        name, value = (item.strip() for item in part.split("=", 1))
        key = "".join(ch for ch in name.upper() if ch.isalnum())
        if key not in _ANATOMY_ALIASES:
            raise ValueError(f"Unknown anatomy name: {name!r}")
        input_value = int(value)
        if input_value <= 0:
            raise ValueError("Label value 0 is reserved for background")
        if input_value in mapping:
            raise ValueError(f"Input label {input_value} was assigned more than once")
        mapping[input_value] = _ANATOMY_ALIASES[key]
    if not mapping:
        raise ValueError("No label mapping was supplied")
    return mapping


def _as_tzyx(array: np.ndarray) -> np.ndarray:
    """Convert NIfTI ``x,y,z[,t]`` data to internal ``t,z,y,x`` data."""

    array = np.asarray(array)
    if array.ndim == 3:
        return np.transpose(array, (2, 1, 0))[None, ...]
    if array.ndim == 4:
        return np.transpose(array, (3, 2, 1, 0))
    raise ValueError(
        f"Expected a 3D or 4D NIfTI image; received shape {array.shape}"
    )


def _normalise_frame(frame: np.ndarray) -> np.ndarray:
    frame = np.asarray(frame, dtype=np.float32)
    finite = frame[np.isfinite(frame)]
    if finite.size == 0:
        return np.zeros_like(frame, dtype=np.float32)
    low, high = np.percentile(finite, (1.0, 99.0))
    if high <= low:
        return np.zeros_like(frame, dtype=np.float32)
    return np.clip((frame - low) / (high - low), 0.0, 1.0).astype(np.float32)


@dataclass
class CardiacCineStudy:
    """A cine volume and its editable four-chamber label map."""

    cine: np.ndarray
    labels: np.ndarray
    spacing_zyx: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    affine: np.ndarray = field(default_factory=lambda: np.eye(4, dtype=float))
    source_path: Optional[Path] = None
    provenance: Dict[str, str] = field(default_factory=dict)
    evidence: Dict[int, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.cine = np.asarray(self.cine, dtype=np.float32)
        self.labels = np.asarray(self.labels, dtype=np.uint8)
        if self.cine.ndim != 4:
            raise ValueError("Cine data must use (time, z, y, x) order")
        if self.labels.shape != self.cine.shape:
            raise ValueError(
                f"Label shape {self.labels.shape} does not match cine shape "
                f"{self.cine.shape}"
            )
        if len(self.spacing_zyx) != 3 or any(v <= 0 for v in self.spacing_zyx):
            raise ValueError("Voxel spacing must contain three positive values")
        invalid = set(np.unique(self.labels).tolist()) - ({0} | set(ANATOMY))
        if invalid:
            raise ValueError(f"Unsupported cardiac anatomy labels: {sorted(invalid)}")
        self.provenance = {
            "dataset": self.provenance.get("dataset", "Unspecified dataset"),
            "source_url": self.provenance.get("source_url", ""),
            "license": self.provenance.get("license", "Verify at source"),
            "citation": self.provenance.get("citation", ""),
            "processing_note": self.provenance.get(
                "processing_note",
                "Chamber surfaces reconstructed from the supplied label map.",
            ),
        }
        self.evidence = {
            int(label): self.evidence.get(int(label), "unknown") for label in ANATOMY
        }
        bad_evidence = set(self.evidence.values()) - set(EVIDENCE_LEVELS)
        if bad_evidence:
            raise ValueError(f"Unsupported evidence levels: {sorted(bad_evidence)}")

    @property
    def n_frames(self) -> int:
        return int(self.cine.shape[0])

    @property
    def n_slices(self) -> int:
        return int(self.cine.shape[1])

    @property
    def spatial_shape(self) -> Tuple[int, int, int]:
        return tuple(int(v) for v in self.cine.shape[1:])

    @classmethod
    def from_nifti(cls, cine_path: Path) -> "CardiacCineStudy":
        if nib is None:
            raise MissingImagingDependency(
                "NIfTI loading requires nibabel. Install requirements.txt."
            )
        cine_path = Path(cine_path)
        image = nib.as_closest_canonical(nib.load(str(cine_path)))
        data = _as_tzyx(np.asanyarray(image.dataobj, dtype=np.float32))
        spacing_xyz = tuple(float(v) for v in image.header.get_zooms()[:3])
        return cls(
            cine=data,
            labels=np.zeros(data.shape, dtype=np.uint8),
            spacing_zyx=spacing_xyz[::-1],
            affine=np.asarray(image.affine, dtype=float),
            source_path=cine_path,
            provenance={
                "dataset": cine_path.stem.replace(".nii", ""),
                "source_url": "",
                "license": "Verify at source before redistribution",
                "citation": "",
                "processing_note": "Loaded from NIfTI; no labels were inferred.",
            },
            evidence={label: "unknown" for label in ANATOMY},
        )

    @classmethod
    def synthetic_demo(
        cls,
        n_frames: int = 20,
        shape_zyx: Tuple[int, int, int] = (44, 72, 72),
    ) -> "CardiacCineStudy":
        """Create an explicitly synthetic four-chamber beating demonstration."""

        if n_frames < 4:
            raise ValueError("The synthetic demo needs at least four frames")
        z_size, y_size, x_size = shape_zyx
        z, y, x = np.ogrid[:z_size, :y_size, :x_size]
        cine = np.empty((n_frames, z_size, y_size, x_size), dtype=np.float32)
        labels = np.zeros_like(cine, dtype=np.uint8)
        rng = np.random.default_rng(20260812)

        chamber_specs = {
            1: ((29.5, 36.0, 25.5), (14.0, 8.5, 9.0), 0.24, 0.0),
            2: ((28.5, 36.0, 47.0), (13.5, 8.0, 10.0), 0.19, 0.10),
            3: ((10.5, 36.0, 26.0), (7.5, 8.5, 9.5), 0.10, np.pi),
            4: ((10.0, 36.0, 47.0), (7.8, 8.8, 10.0), 0.09, np.pi),
        }

        for frame_index in range(n_frames):
            phase = 2.0 * np.pi * frame_index / n_frames
            frame_labels = np.zeros(shape_zyx, dtype=np.uint8)
            for label, (centre, radii, contraction, phase_shift) in chamber_specs.items():
                scale = 1.0 - contraction * (0.5 - 0.5 * np.cos(phase + phase_shift))
                rz, ry, rx = (max(2.0, value * scale) for value in radii)
                cz, cy, cx = centre
                ellipsoid = (
                    ((z - cz) / rz) ** 2
                    + ((y - cy) / ry) ** 2
                    + ((x - cx) / rx) ** 2
                    <= 1.0
                )
                frame_labels[(frame_labels == 0) & ellipsoid] = label

            labels[frame_index] = frame_labels
            cardiac_region = frame_labels > 0
            outer = ndimage.binary_dilation(cardiac_region, iterations=3)
            wall = outer & ~cardiac_region
            image = np.full(shape_zyx, 0.08, dtype=np.float32)
            image[wall] = 0.48
            image[cardiac_region] = 0.88
            image += rng.normal(0.0, 0.025, shape_zyx).astype(np.float32)
            cine[frame_index] = ndimage.gaussian_filter(image, sigma=0.65)

        # Add an explicitly synthetic myocardial shell.  It is useful for
        # testing the external/cutaway workflow but is not a claim about a
        # patient's anatomy.
        for frame_index in range(n_frames):
            cavities = labels[frame_index] > 0
            outer = ndimage.binary_dilation(cavities, iterations=4)
            labels[frame_index][outer & ~cavities] = 5

            # Coarse, labelled external structures make every viewing control
            # testable without distributing patient data.  They are deliberately
            # schematic and their evidence status remains ``synthetic``.
            phase = 2.0 * np.pi * frame_index / n_frames
            squeeze = 1.0 - 0.05 * (0.5 - 0.5 * np.cos(phase))
            def cylinder(label, cx, cy, z0, z1, radius):
                region = (
                    (z >= z0) & (z <= z1)
                    & ((x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2)
                )
                labels[frame_index][region] = label

            cylinder(6, 0.40 * x_size, 0.45 * y_size, 0, 0.38 * z_size, max(2.0, 0.055 * x_size))
            cylinder(7, 0.60 * x_size, 0.47 * y_size, 0.08 * z_size, 0.42 * z_size, max(2.0, 0.050 * x_size))
            cylinder(8, 0.72 * x_size, 0.52 * y_size, 0, 0.32 * z_size, max(2.0, 0.045 * x_size))
            cylinder(9, 0.70 * x_size, 0.52 * y_size, 0.70 * z_size, z_size - 1, max(2.0, 0.045 * x_size))
            pv = (
                (np.abs(z - 0.27 * z_size) <= max(1, int(0.035 * z_size)))
                & (np.abs(y - 0.50 * y_size) <= max(1, int(0.035 * y_size)))
                & (x >= 0.12 * x_size) & (x <= 0.88 * x_size)
            )
            labels[frame_index][pv & (labels[frame_index] == 0)] = 10

            # A pair of thin epicardial curves, attached to the outer shell.
            shell = labels[frame_index] == 5
            theta = np.arctan2(y - 0.50 * y_size, x - 0.50 * x_size)
            coronary_paths = (
                (np.abs(np.sin(theta + 0.8 * (z / max(z_size - 1, 1)))) < 0.08)
                | (np.abs(np.sin(theta - 0.9 * (z / max(z_size - 1, 1)) + 1.8)) < 0.07)
            )
            labels[frame_index][shell & coronary_paths & (z > 0.22 * z_size)] = 11

        return cls(
            cine=cine,
            labels=labels,
            # Coarse but plausible teaching-MRI spacing; it also makes the
            # synthetic ED/ES chamber volumes human-scale rather than toy-scale.
            spacing_zyx=(4.5, 2.5, 2.5),
            affine=np.diag([2.5, 2.5, 4.5, 1.0]),
            provenance={
            "dataset": "Open 4D Cardiac Anatomy synthetic demonstration",
                "source_url": "",
                "license": "GPL-3.0 project-generated demonstration",
                "citation": "Open 4D Cardiac Anatomy",
                "processing_note": (
                    "Synthetic ellipsoidal chamber cavities for software testing; "
                    "not human MRI and not anatomically diagnostic."
                ),
            },
            evidence={label: "synthetic" for label in ANATOMY},
        )

    def load_label_nifti(
        self,
        label_path: Path,
        input_to_internal: Mapping[int, int],
        current_frame: int = 0,
    ) -> None:
        """Load a 3D reference mask or a complete 4D label sequence."""

        if nib is None:
            raise MissingImagingDependency(
                "NIfTI loading requires nibabel. Install requirements.txt."
            )
        image = nib.as_closest_canonical(nib.load(str(label_path)))
        raw = _as_tzyx(np.asanyarray(image.dataobj))
        mapped = np.zeros(raw.shape, dtype=np.uint8)
        for input_value, internal_value in input_to_internal.items():
            if internal_value not in ANATOMY:
                raise ValueError(f"Invalid cardiac anatomy label: {internal_value}")
            mapped[raw == int(input_value)] = int(internal_value)

        if mapped.shape[1:] != self.spatial_shape:
            raise ValueError(
                f"Mask spatial shape {mapped.shape[1:]} does not match cine "
                f"shape {self.spatial_shape}. Resampling is intentionally not silent."
            )
        if mapped.shape[0] == self.n_frames:
            self.labels[...] = mapped
        elif mapped.shape[0] == 1:
            current_frame = int(np.clip(current_frame, 0, self.n_frames - 1))
            self.labels[current_frame] = mapped[0]
        else:
            raise ValueError(
                f"Mask has {mapped.shape[0]} frames; cine has {self.n_frames}."
            )
        self.provenance["processing_note"] = (
            f"Chamber masks loaded from {Path(label_path).name}; label mapping "
            "was supplied explicitly by the user."
        )
        for internal_value in input_to_internal.values():
            self.evidence[int(internal_value)] = "unknown"

    def save_label_nifti(self, output_path: Path) -> None:
        if nib is None:
            raise MissingImagingDependency(
                "NIfTI saving requires nibabel. Install requirements.txt."
            )
        xyzt = np.transpose(self.labels, (3, 2, 1, 0))
        image = nib.Nifti1Image(xyzt.astype(np.uint8), self.affine)
        nib.save(image, str(output_path))

    def mesh_for_label(
        self, frame_index: int, label: int
    ) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """Return centred physical-space vertices and triangular faces."""

        if marching_cubes is None:
            raise MissingImagingDependency(
                "3D surface reconstruction requires scikit-image."
            )
        frame_index = int(np.clip(frame_index, 0, self.n_frames - 1))
        binary = self.labels[frame_index] == int(label)
        if not np.any(binary):
            return None

        padded = np.pad(binary.astype(np.float32), 1, mode="constant")
        vertices_zyx, faces, _, _ = marching_cubes(
            padded,
            level=0.5,
            spacing=self.spacing_zyx,
            allow_degenerate=False,
        )
        vertices_zyx -= np.asarray(self.spacing_zyx, dtype=np.float32)
        vertices_xyz = vertices_zyx[:, [2, 1, 0]]
        z_size, y_size, x_size = self.spatial_shape
        sz, sy, sx = self.spacing_zyx
        centre_xyz = np.asarray(
            [(x_size - 1) * sx, (y_size - 1) * sy, (z_size - 1) * sz],
            dtype=np.float32,
        ) / 2.0
        vertices_xyz = vertices_xyz.astype(np.float32) - centre_xyz
        return vertices_xyz, faces.astype(np.uint32)

    def chamber_volume_ml(self, frame_index: int, label: int) -> float:
        voxel_mm3 = float(np.prod(self.spacing_zyx))
        count = int(np.count_nonzero(self.labels[frame_index] == int(label)))
        return count * voxel_mm3 / 1000.0

    def quality_report(self) -> Dict[str, object]:
        """Return conservative, explainable checks; never a clinical validation."""

        present = {
            label: int(np.count_nonzero(self.labels == label)) > 0 for label in ANATOMY
        }
        empty_frames = {
            ANATOMY[label].short_name: [
                index for index in range(self.n_frames)
                if not np.any(self.labels[index] == label)
            ]
            for label in ANATOMY if present[label]
        }
        temporal_jumps: Dict[str, List[int]] = {}
        for label in ANATOMY:
            volumes = np.asarray([
                self.chamber_volume_ml(index, label) for index in range(self.n_frames)
            ])
            positive = volumes[volumes > 0]
            if positive.size < 2:
                continue
            scale = max(float(np.median(positive)), 1e-6)
            jumps = np.where(np.abs(np.diff(volumes, append=volumes[0])) / scale > 0.35)[0]
            temporal_jumps[ANATOMY[label].short_name] = jumps.astype(int).tolist()
        measured = [ANATOMY[k].short_name for k, v in self.evidence.items() if v == "measured" and present.get(k)]
        statistical = [ANATOMY[k].short_name for k, v in self.evidence.items() if v == "statistical" and present.get(k)]
        composite = [ANATOMY[k].short_name for k, v in self.evidence.items() if v in {"registered", "synthetic"} and present.get(k)]
        return {
            "frames": self.n_frames,
            "spacing_zyx_mm": list(self.spacing_zyx),
            "present_structures": [ANATOMY[k].short_name for k, v in present.items() if v],
            "missing_core_chambers": [CHAMBERS[k].short_name for k in CHAMBERS if not present[k]],
            "empty_frames": empty_frames,
            "temporal_volume_jump_frames": temporal_jumps,
            "measured_structures": measured,
            "statistical_structures": statistical,
            "composite_or_synthetic_structures": composite,
            "diagnostic_validation": False,
        }

    def propagate_from_reference(
        self,
        reference_frame: int,
        progress: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """Propagate a corrected reference mask through time using optical flow.

        This is a teaching/research aid, not a validated diagnostic segmenter.
        The method deliberately leaves the reference frame unchanged and replaces
        all other frames, so callers should confirm before running it.
        """

        if optical_flow_tvl1 is None or warp is None:
            raise MissingImagingDependency(
                "Automatic temporal propagation requires scikit-image."
            )
        reference_frame = int(np.clip(reference_frame, 0, self.n_frames - 1))
        if not np.any(self.labels[reference_frame]):
            raise ValueError("Correct or load at least one chamber on this frame first")

        total_pairs = max(0, self.n_frames - 1)
        completed = 0

        def propagate_pair(source_index: int, target_index: int) -> None:
            source_image = _normalise_frame(self.cine[source_index])
            target_image = _normalise_frame(self.cine[target_index])
            result = np.zeros(self.spatial_shape, dtype=np.uint8)
            for slice_index in range(self.n_slices):
                source_slice = source_image[slice_index]
                target_slice = target_image[slice_index]
                source_mask = self.labels[source_index, slice_index]
                if not np.any(source_mask):
                    continue
                # Flow is calculated from target coordinates back to source.
                flow = optical_flow_tvl1(target_slice, source_slice)
                row, col = np.meshgrid(
                    np.arange(source_slice.shape[0]),
                    np.arange(source_slice.shape[1]),
                    indexing="ij",
                )
                coordinates = np.asarray([row + flow[0], col + flow[1]])
                warped = warp(
                    source_mask,
                    coordinates,
                    order=0,
                    mode="constant",
                    cval=0,
                    preserve_range=True,
                )
                result[slice_index] = np.rint(warped).astype(np.uint8)
            self.labels[target_index] = result

        for target in range(reference_frame + 1, self.n_frames):
            propagate_pair(target - 1, target)
            completed += 1
            if progress:
                progress(completed, total_pairs)
        for target in range(reference_frame - 1, -1, -1):
            propagate_pair(target + 1, target)
            completed += 1
            if progress:
                progress(completed, total_pairs)
        for label in ANATOMY:
            if np.any(self.labels[reference_frame] == label):
                self.evidence[label] = "propagated"

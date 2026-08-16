"""Bundled open-data cardiac anatomy and 3D+t motion model."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

from .core import ANATOMY, CHAMBERS


ASSET_PATH = Path(__file__).resolve().parent / "assets" / "open_heart_atlas_v2.npz"


class OpenHeartAtlasStudy:
    """Detailed atlas anatomy registered to a CT-derived statistical motion model.

    This is deliberately not a ``CardiacCineStudy``.  It has no underlying patient
    image and therefore cannot expose image-derived cavity volumes or a paintable
    source slice.  The distinction prevents a composite atlas from masquerading as
    one measured subject.
    """

    is_open_heart_atlas = True
    has_image_data = False
    n_slices = 1

    def __init__(self, asset_path: Path = ASSET_PATH) -> None:
        self.asset_path = Path(asset_path)
        if not self.asset_path.is_file():
            raise FileNotFoundError(f"Bundled open-heart asset is missing: {self.asset_path}")
        self._archive = np.load(self.asset_path, allow_pickle=False)
        self._array_cache: dict[str, np.ndarray] = {}
        self._anatomical_axes_cache: Optional[Dict[str, np.ndarray]] = None
        self._valve_animation_cache: dict[int, Dict[str, np.ndarray]] = {}
        self._procedural_valve_cache: dict[
            int, Dict[str, np.ndarray | float | int]
        ] = {}
        self.metadata = json.loads(bytes(self._archive["metadata_json"]).decode("utf-8"))
        self.n_frames = int(self.metadata["frame_count"])
        self.end_diastole_frame = int(self.metadata["end_diastole_frame"])
        self.end_systole_frame = int(self.metadata["end_systole_frame"])
        self.exact_source_phases = set(int(v) for v in self.metadata["exact_source_phases"])
        self.interpolated_phases = set(int(v) for v in self.metadata["interpolated_phases"])
        self.evidence = {
            label: ("registered" if f"atlas_{label}_vertices" in self._archive else "unknown")
            for label in ANATOMY
        }
        self.source_evidence = {
            label: ("statistical" if f"source_{label}_vertices" in self._archive else "unknown")
            for label in ANATOMY
        }
        self.provenance = {
            "dataset": "Open Heart Atlas composite v2",
            "source_url": "https://github.com/Z-Anatomy/Models-of-human-anatomy ; https://www5.cs.fau.de/conrad/data/heart-model/",
            "license": "Z-Anatomy CC BY-SA 4.0; CONRAD GPL-3.0; combined adapted asset GPL-3.0",
            "citation": "BodyParts3D; Z-Anatomy; Unberath et al., ISBI 2015; Open 4D Cardiac Anatomy",
            "processing_note": self.metadata["composite_notice"],
        }
        self.source_path = self.asset_path

    @property
    def observed_consecutive_beats(self) -> int:
        """Consecutive beats represented by the bundled motion source.

        FAU/CONRAD is a population statistical model over one normalized cycle.
        Its ten phases are not a longitudinal recording of consecutive beats.
        """

        return 1

    @property
    def supports_observed_beat_to_beat_variation(self) -> bool:
        return False

    @property
    def spatial_shape(self) -> Tuple[int, int, int]:
        return (1, 1, 1)

    @property
    def spacing_zyx(self) -> Tuple[float, float, float]:
        return (1.0, 1.0, 1.0)

    def available_labels(self, source_faithful: bool = False) -> set[int]:
        prefix = "source" if source_faithful else "atlas"
        return {
            label for label in ANATOMY
            if f"{prefix}_{label}_vertices" in self._archive
        }

    def _array(self, key: str) -> np.ndarray:
        """Decompress each NPZ member once; playback then only selects frame views."""

        if key not in self._array_cache:
            self._array_cache[key] = np.asarray(self._archive[key])
        return self._array_cache[key]

    def evidence_for_label(self, label: int, source_faithful: bool = False) -> str:
        collection = self.source_evidence if source_faithful else self.evidence
        return collection.get(int(label), "unknown")

    def mesh_for_label(
        self,
        frame_index: int,
        label: int,
        source_faithful: bool = False,
    ) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        prefix = "source" if source_faithful else "atlas"
        vertices_key = f"{prefix}_{int(label)}_vertices"
        faces_key = f"{prefix}_{int(label)}_faces"
        if vertices_key not in self._archive or faces_key not in self._archive:
            return None
        frame_index = int(np.clip(frame_index, 0, self.n_frames - 1))
        return (
            np.asarray(self._array(vertices_key)[frame_index], dtype=np.float32),
            np.asarray(self._array(faces_key), dtype=np.uint32),
        )

    def mesh_for_phase(
        self,
        phase: float,
        label: int,
        source_faithful: bool = False,
    ) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """Return a mesh at a continuous, normalized cardiac-cycle phase.

        The bundled asset contains a closed 20-frame loop. Linear interpolation
        between adjacent frames adds display samples without claiming additional
        measured anatomy. It also preserves the exact source-derived surfaces at
        their stored phase positions and avoids spline overshoot around thin valves
        and coronary vessels.
        """

        prefix = "source" if source_faithful else "atlas"
        vertices_key = f"{prefix}_{int(label)}_vertices"
        faces_key = f"{prefix}_{int(label)}_faces"
        if vertices_key not in self._archive or faces_key not in self._archive:
            return None

        normalized_phase = float(phase) % 1.0
        frame_position = normalized_phase * self.n_frames
        lower = int(np.floor(frame_position)) % self.n_frames
        upper = (lower + 1) % self.n_frames
        fraction = float(frame_position - np.floor(frame_position))
        stored = self._array(vertices_key)
        if fraction <= 1e-6:
            vertices = np.asarray(stored[lower], dtype=np.float32)
        else:
            vertices = np.asarray(
                stored[lower] + fraction * (stored[upper] - stored[lower]),
                dtype=np.float32,
            )
        return vertices, np.asarray(self._array(faces_key), dtype=np.uint32)

    def frame_position_for_phase(self, phase: float) -> float:
        """Map normalized cycle phase to the fractional stored-frame position."""

        return (float(phase) % 1.0) * self.n_frames

    def _valve_animation_geometry(self, label: int) -> Dict[str, np.ndarray]:
        """Cache a conservative annulus-to-free-edge deformation field.

        The source atlas contains leaflet geometry but no measured leaflet motion.
        PCA supplies a local valve plane; vertices near the outer radial envelope
        behave as a fixed annulus while central/free-edge vertices receive most of
        the procedural opening displacement. This changes no topology.
        """

        label = int(label)
        if label not in {12, 13, 14, 15}:
            raise ValueError(f"Label {label} is not a supported valve leaflet mesh")
        if label in self._valve_animation_cache:
            return self._valve_animation_cache[label]

        base = np.asarray(self._array(f"atlas_{label}_vertices")[0], dtype=np.float32)
        centre = base.mean(axis=0)
        relative = base - centre
        _, eigenvectors = np.linalg.eigh(np.cov(relative.T))
        normal = np.asarray(eigenvectors[:, 0], dtype=np.float32)
        target_label = {12: 1, 13: 2, 14: 6, 15: 7}[label]
        target = np.asarray(
            self._array(f"atlas_{target_label}_vertices")[0], dtype=np.float32
        ).mean(axis=0)
        if float(np.dot(normal, target - centre)) < 0.0:
            normal *= -1.0

        in_plane = relative - np.outer(relative @ normal, normal)
        radial_distance = np.linalg.norm(in_plane, axis=1)
        radial_unit = np.zeros_like(in_plane, dtype=np.float32)
        valid = radial_distance > 1e-6
        radial_unit[valid] = in_plane[valid] / radial_distance[valid, None]
        radial_limit = max(float(np.percentile(radial_distance, 95.0)), 1e-6)
        free_edge_weight = np.clip(
            1.0 - radial_distance / radial_limit, 0.0, 1.0
        ) ** 1.6
        geometry = {
            "normal": normal,
            "radial_unit": radial_unit,
            "free_edge_weight": free_edge_weight.astype(np.float32),
        }
        self._valve_animation_cache[label] = geometry
        return geometry

    def animate_valve_vertices(
        self, label: int, vertices: np.ndarray, open_fraction: float
    ) -> np.ndarray:
        """Apply visible but explicitly procedural leaflet opening.

        Mitral/tricuspid free edges bow ventricularly and separate slightly;
        aortic/pulmonary free edges move chiefly toward their vessel wall. The
        operation is for phase teaching and is not patient-measured kinematics.
        """

        label = int(label)
        opening = float(np.clip(open_fraction, 0.0, 1.0))
        current = np.asarray(vertices, dtype=np.float32)
        if label not in {12, 13, 14, 15} or opening <= 1e-6:
            return current
        geometry = self._valve_animation_geometry(label)
        weight = geometry["free_edge_weight"][:, None]
        normal = geometry["normal"][None, :]
        radial = geometry["radial_unit"]
        if label in {12, 13}:
            displacement = 7.5 * normal * weight + 2.0 * radial * weight
        else:
            displacement = 2.0 * normal * weight + 5.0 * radial * weight
        return np.asarray(current + opening * displacement, dtype=np.float32)

    @staticmethod
    def procedural_valve_leaflet_count(label: int) -> int:
        """Return the anatomically expected leaflet/cusp count."""

        counts = {12: 2, 13: 3, 14: 3, 15: 3}
        try:
            return counts[int(label)]
        except KeyError as exc:
            raise ValueError(f"Label {label} is not a supported valve") from exc

    def _procedural_valve_geometry(
        self, label: int
    ) -> Dict[str, np.ndarray | float | int]:
        """Build a stable annulus and topology for a valve teaching overlay.

        The redistributed atlas valves supply location but not measured leaflet
        kinematics.  The overlay therefore states its topology explicitly: two
        mitral leaflets, three tricuspid leaflets and three semilunar cusps.
        """

        label = int(label)
        if label in self._procedural_valve_cache:
            return self._procedural_valve_cache[label]
        leaflet_count = self.procedural_valve_leaflet_count(label)
        reference = np.asarray(
            self._array(f"atlas_{label}_vertices")[0], dtype=np.float32
        )
        centre = np.median(reference, axis=0).astype(np.float32)
        target_label = {12: 1, 13: 2, 14: 6, 15: 7}[label]
        target = np.asarray(
            self._array(f"atlas_{target_label}_vertices")[0], dtype=np.float32
        ).mean(axis=0)
        normal = np.asarray(target - centre, dtype=np.float32)
        normal /= max(float(np.linalg.norm(normal)), 1e-6)
        superior = np.asarray([0.0, 0.0, 1.0], dtype=np.float32)
        if abs(float(np.dot(normal, superior))) > 0.90:
            superior = np.asarray([1.0, 0.0, 0.0], dtype=np.float32)
        axis_one = np.cross(normal, superior)
        axis_one /= max(float(np.linalg.norm(axis_one)), 1e-6)
        axis_two = np.cross(normal, axis_one)
        axis_two /= max(float(np.linalg.norm(axis_two)), 1e-6)

        projected_one = (reference - centre) @ axis_one
        projected_two = (reference - centre) @ axis_two
        measured_one = 0.5 * float(
            np.percentile(projected_one, 90.0)
            - np.percentile(projected_one, 10.0)
        )
        measured_two = 0.5 * float(
            np.percentile(projected_two, 90.0)
            - np.percentile(projected_two, 10.0)
        )
        limits = {
            12: ((11.5, 16.5), (8.5, 13.5)),
            13: ((13.0, 18.0), (10.0, 15.0)),
            14: ((6.5, 9.5), (6.5, 9.5)),
            15: ((7.0, 10.0), (7.0, 10.0)),
        }[label]
        radius_one = float(np.clip(measured_one, *limits[0]))
        radius_two = float(np.clip(measured_two, *limits[1]))

        angular_samples = 13
        radial_samples = 8
        faces = []
        for leaflet in range(leaflet_count):
            offset = leaflet * angular_samples * radial_samples
            for angular in range(angular_samples - 1):
                for radial in range(radial_samples - 1):
                    a = offset + angular * radial_samples + radial
                    b = a + radial_samples
                    faces.append((a, b, a + 1))
                    faces.append((b, b + 1, a + 1))
        sample_indices = np.linspace(
            0, len(reference) - 1, min(384, len(reference)), dtype=np.int64
        )
        geometry: Dict[str, np.ndarray | float | int] = {
            "reference_sample": reference[sample_indices],
            "sample_indices": sample_indices,
            "centre": centre,
            "normal": normal,
            "axis_one": axis_one,
            "axis_two": axis_two,
            "radius_one": radius_one,
            "radius_two": radius_two,
            "leaflet_count": leaflet_count,
            "angular_samples": angular_samples,
            "radial_samples": radial_samples,
            "faces": np.asarray(faces, dtype=np.uint32),
        }
        self._procedural_valve_cache[label] = geometry
        return geometry

    def procedural_valve_mesh(
        self,
        label: int,
        phase: float,
        open_fraction: float,
        current_vertices: Optional[np.ndarray] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Return a correctly counted moving valve teaching mesh.

        The source atlas supplies annular position and rigid cycle motion. Opening
        is parametric and must not be interpreted as measured leaflet tracking.
        """

        label = int(label)
        geometry = self._procedural_valve_geometry(label)
        leaflet_count = int(geometry["leaflet_count"])
        angular_samples = int(geometry["angular_samples"])
        radial_samples = int(geometry["radial_samples"])
        opening = float(np.clip(open_fraction, 0.0, 1.0))
        axis_one = np.asarray(geometry["axis_one"], dtype=np.float32)
        axis_two = np.asarray(geometry["axis_two"], dtype=np.float32)
        normal = np.asarray(geometry["normal"], dtype=np.float32)
        radius_one = float(geometry["radius_one"])
        radius_two = float(geometry["radius_two"])
        centre = np.asarray(geometry["centre"], dtype=np.float32)

        points = []
        sector = 2.0 * np.pi / leaflet_count
        half_span = 0.46 * sector
        mitral_offset = 0.5 * np.pi if label == 12 else 0.0
        semilunar = label in {14, 15}
        free_edge_radius = (
            0.06 + 0.72 * opening if semilunar else 0.08 + 0.54 * opening
        )
        axial_travel = (4.5 if semilunar else 8.0) * opening
        for leaflet in range(leaflet_count):
            middle = mitral_offset + leaflet * sector
            for angle in np.linspace(
                middle - half_span,
                middle + half_span,
                angular_samples,
            ):
                annular = (
                    radius_one * np.cos(angle) * axis_one
                    + radius_two * np.sin(angle) * axis_two
                )
                for fraction in np.linspace(0.0, 1.0, radial_samples):
                    radial_scale = 1.0 - fraction * (1.0 - free_edge_radius)
                    bow = (1.0 - opening) * 1.4 * np.sin(np.pi * fraction)
                    axial = axial_travel * fraction**1.35 + bow
                    points.append(centre + radial_scale * annular + axial * normal)
        base_vertices = np.asarray(points, dtype=np.float32)

        if current_vertices is None:
            current = self.mesh_for_phase(float(phase), label)
            if current is None:
                return base_vertices, np.asarray(geometry["faces"], dtype=np.uint32)
            current_vertices, _ = current
        current_vertices = np.asarray(current_vertices, dtype=np.float32)
        sample_indices = np.asarray(geometry["sample_indices"], dtype=np.int64)
        reference_sample = np.asarray(
            geometry["reference_sample"], dtype=np.float32
        )
        current_sample = np.asarray(current_vertices[sample_indices], dtype=np.float32)
        reference_mean = reference_sample.mean(axis=0)
        current_mean = current_sample.mean(axis=0)
        covariance = (reference_sample - reference_mean).T @ (
            current_sample - current_mean
        )
        u, _, vt = np.linalg.svd(covariance)
        rotation = u @ vt
        if np.linalg.det(rotation) < 0.0:
            u[:, -1] *= -1.0
            rotation = u @ vt
        vertices = (base_vertices - reference_mean) @ rotation + current_mean
        return (
            np.asarray(vertices, dtype=np.float32),
            np.asarray(geometry["faces"], dtype=np.uint32),
        )

    def bounds(self, frame_index: int = 0, source_faithful: bool = False):
        minima = []
        maxima = []
        for label in self.available_labels(source_faithful):
            mesh = self.mesh_for_label(frame_index, label, source_faithful)
            if mesh is None:
                continue
            vertices, _ = mesh
            minima.append(vertices.min(axis=0))
            maxima.append(vertices.max(axis=0))
        if not minima:
            return np.zeros(3, dtype=np.float32), np.ones(3, dtype=np.float32)
        return np.min(minima, axis=0), np.max(maxima, axis=0)

    def anatomical_axes(self) -> Dict[str, np.ndarray]:
        """Return the validated anatomical frame of the bundled atlas.

        The registered FAU Cartesian frame is ``+X left, -Y anterior, +Z
        superior``. Named-structure checks confirm that the left chambers lie
        leftward of the right chambers, the right chambers lie anterior to the
        left chambers, and the aorta lies superior to the ventricles. Keeping this
        fixed frame avoids contaminating camera orientation with asymmetric mesh
        centroids or chamber-size differences.

        This atlas-specific frame must not be applied to imported NIfTI data;
        patient orientation requires the source image affine/DICOM metadata.
        """

        if self._anatomical_axes_cache is not None:
            return {key: value.copy() for key, value in self._anatomical_axes_cache.items()}
        left = np.asarray([1.0, 0.0, 0.0], dtype=np.float32)
        anterior = np.asarray([0.0, -1.0, 0.0], dtype=np.float32)
        superior = np.asarray([0.0, 0.0, 1.0], dtype=np.float32)
        axes = {
            "Left": left,
            "Right": -left,
            "Superior": superior,
            "Inferior": -superior,
            "Anterior": anterior,
            "Posterior": -anterior,
        }
        self._anatomical_axes_cache = axes
        return {key: value.copy() for key, value in axes.items()}

    def surface_vessel_attachment_report(self) -> Dict[str, object]:
        return dict(self.metadata.get("surface_vessel_attachment", {}))

    def phase_description(self, frame_index: int) -> str:
        frame_index = int(np.clip(frame_index, 0, self.n_frames - 1))
        labels = []
        if frame_index == self.end_diastole_frame:
            labels.append("end-diastole")
        if frame_index == self.end_systole_frame:
            labels.append("end-systole")
        labels.append(
            "FAU statistical source phase"
            if frame_index in self.exact_source_phases
            else "linearly interpolated phase"
        )
        return " · ".join(labels)

    def quality_report(self) -> Dict[str, object]:
        present = sorted(self.available_labels(False))
        return {
            "frames": self.n_frames,
            "spacing_zyx_mm": None,
            "present_structures": [ANATOMY[label].short_name for label in present],
            "missing_core_chambers": [
                CHAMBERS[label].short_name for label in CHAMBERS if label not in present
            ],
            "empty_frames": {},
            "temporal_volume_jump_frames": {},
            "measured_structures": [],
            "statistical_structures": ["FAU source: MYO, RA, LA, RV, AO, LV"],
            "composite_or_synthetic_structures": [
                ANATOMY[label].short_name for label in present
            ],
            "diagnostic_validation": False,
            "temporal_source": {
                "normalized_cycles": 1,
                "observed_consecutive_beats": self.observed_consecutive_beats,
                "observed_beat_to_beat_variation": (
                    self.supports_observed_beat_to_beat_variation
                ),
                "sequence_playback": (
                    "repeats one statistical cycle; does not add observed beats"
                ),
            },
            "atlas_registration_landmark_rms_mm": float(
                self.metadata["atlas_registration_landmark_rms_mm"]
            ),
            "volume_reporting": "disabled: atlas meshes are not cavity segmentations",
            "surface_vessel_attachment": self.surface_vessel_attachment_report(),
            "procedural_valve_motion": {
                "enabled": False,
                "labels": [12, 13, 14, 15],
                "leaflet_counts": {"mitral": 2, "tricuspid": 3, "aortic": 3, "pulmonary": 3},
                "evidence": (
                    "withheld from clean presets because the incomplete source "
                    "leaflets and procedural overlay are not fitted to the visible "
                    "annuli/outflow orifices"
                ),
            },
        }

    def chamber_volume_ml(self, frame_index: int, label: int) -> float:
        return float("nan")

    def close(self) -> None:
        self._archive.close()
        self._array_cache.clear()
        self._valve_animation_cache.clear()
        self._procedural_valve_cache.clear()

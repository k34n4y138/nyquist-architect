from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, Tuple


def _as_float(values: Dict[str, Any], *keys: str, default: float | None = None) -> float | None:
    for key in keys:
        if key in values and values[key] is not None:
            try:
                return float(values[key])
            except (TypeError, ValueError):
                continue
    return default


def _sensor_pixels(sensor_w_mm: float, sensor_h_mm: float, px_w_um: float | None, px_h_um: float | None) -> Tuple[float, float]:
    px_w_mm = (px_w_um or 0.0) / 1000.0
    px_h_mm = (px_h_um or 0.0) / 1000.0
    if px_w_mm <= 0 and px_h_mm <= 0:
        return 0.0, 0.0
    if px_w_mm <= 0 <= px_h_mm:
        px_w_mm = px_h_mm
    if px_h_mm <= 0 <= px_w_mm:
        px_h_mm = px_w_mm
    pixels_horz = sensor_w_mm / px_w_mm if px_w_mm > 0 else 0.0
    pixels_vert = sensor_h_mm / px_h_mm if px_h_mm > 0 else 0.0
    return pixels_horz, pixels_vert


def _lens_geometry(f_mm: float, working_distance_mm: float) -> Tuple[float, float]:
    f = float(f_mm)
    do = float(working_distance_mm)
    if do <= f:
        di = float("inf")
        m = float("inf")
    else:
        di = f * do / (do - f)
        m = abs(di / do)
    return di, m


def _dof_hyperfocal(f_mm: float, f_number: float, coc_mm: float, subject_distance_mm: float) -> Dict[str, float]:
    f = float(f_mm)
    N = float(f_number)
    c = max(float(coc_mm), 1e-12)
    s = float(subject_distance_mm)
    H = f * f / (N * c) + f
    Dn = (H * s) / (H + (s - f))
    if s >= H:
        Df = float("inf")
        dof = float("inf")
    else:
        Df = (H * s) / (H - (s - f))
        dof = Df - Dn
    return {"circle_of_confusion_mm_used": c, "near_mm": Dn, "far_mm": Df, "DOF_mm": dof, "hyperfocal_mm": H}


def _diffraction_sampling_metrics(pixel_size_mm_min: float, f_number_eff: float, wavelength_um: float = 0.55) -> Dict[str, float]:
    lambda_mm = float(wavelength_um) / 1000.0
    airy_um = 2.44 * float(wavelength_um) * float(f_number_eff)
    airy_px = airy_um / (pixel_size_mm_min * 1000.0) if pixel_size_mm_min > 0 else float("inf")
    nyquist_lp_per_mm = 1.0 / (2.0 * pixel_size_mm_min) if pixel_size_mm_min > 0 else float("inf")
    diffraction_cutoff_lp_per_mm = 1.0 / (lambda_mm * float(f_number_eff)) if lambda_mm > 0 and f_number_eff > 0 else float("inf")
    ratio = nyquist_lp_per_mm / diffraction_cutoff_lp_per_mm if math.isfinite(diffraction_cutoff_lp_per_mm) and diffraction_cutoff_lp_per_mm > 0 else float("inf")
    return {
        "wavelength_um": float(wavelength_um),
        "airy_disk_diameter_um": airy_um,
        "airy_disk_diameter_pixels": airy_px,
        "diffraction_cutoff_lp_per_mm": diffraction_cutoff_lp_per_mm,
        "nyquist_over_diffraction_cutoff": ratio,
        "sensor_nyquist_lp_per_mm": nyquist_lp_per_mm,
    }


def _illumination_metrics(sensor_diag_mm: float, image_distance_mm: float, lens_relative_illumination: float | None) -> Dict[str, float]:
    center_percent = 100.0
    corner_ratio = None
    if lens_relative_illumination is not None:
        corner_ratio = float(lens_relative_illumination)
        if corner_ratio > 1.5:
            corner_ratio = corner_ratio / 100.0
        corner_ratio = max(min(corner_ratio, 1.0), 0.0)
    else:
        r = 0.5 * sensor_diag_mm
        if math.isfinite(image_distance_mm) and image_distance_mm > 0:
            tan_theta = r / image_distance_mm
            cos_theta = 1.0 / math.sqrt(1.0 + tan_theta * tan_theta)
            corner_ratio = cos_theta ** 4
        else:
            corner_ratio = 1.0
    corner_percent = 100.0 * corner_ratio
    vignetting_loss_percent = max(0.0, 100.0 - corner_percent)
    exposure_comp_stops = math.log2(1.0 / max(corner_ratio, 1e-9)) if corner_ratio > 0 else float("inf")
    return {
        "relative_illumination_center_percent": center_percent,
        "relative_illumination_corner_percent": corner_percent,
        "corner_to_center_ratio": corner_ratio,
        "vignetting_loss_percent": vignetting_loss_percent,
        "exposure_compensation_stops_at_corners": exposure_comp_stops,
    }


def calculate(params: Dict[str, Any]) -> Dict[str, Any]:
    sensor_w_mm = _as_float(params, "sensor_width_mm", default=0.0) or 0.0
    sensor_h_mm = _as_float(params, "sensor_height_mm", default=0.0) or 0.0
    sensor_diag_mm = _as_float(params, "sensor_diagonal_mm")
    if not sensor_diag_mm and sensor_w_mm > 0 and sensor_h_mm > 0:
        sensor_diag_mm = math.hypot(sensor_w_mm, sensor_h_mm)

    px_w_um = _as_float(params, "sensor_pixel_size_width_um")
    px_h_um = _as_float(params, "sensor_pixel_size_height_um")

    pixels_horz, pixels_vert = _sensor_pixels(sensor_w_mm, sensor_h_mm, px_w_um, px_h_um)
    total_pixels = pixels_horz * pixels_vert if pixels_horz > 0 and pixels_vert > 0 else 0.0
    aspect_ratio = (sensor_w_mm / sensor_h_mm) if sensor_h_mm > 0 else float("inf")

    pixel_size_mm_min = min(
        (px_w_um or float("inf")) / 1000.0,
        (px_h_um or float("inf")) / 1000.0,
    )
    sensor_nyquist_lp_per_mm = 1.0 / (2.0 * pixel_size_mm_min) if math.isfinite(pixel_size_mm_min) and pixel_size_mm_min > 0 else float("inf")

    f_mm = _as_float(params, "lens_focal_length_mm", default=0.0) or 0.0
    f_stop = _as_float(params, "lens_fstop", default=0.0) or 0.0
    lens_diag_mm = _as_float(params, "lens_diagonal_mm") or 0.0
    lens_distortion_perc = _as_float(params, "lens_distortion_perc")
    lens_resolution_lp_per_mm = _as_float(params, "lens_resolution")

    working_distance_mm = _as_float(params, "working_distance_mm", default=0.0) or 0.0
    di_mm, m = _lens_geometry(f_mm, working_distance_mm)
    aperture_diameter_mm = (f_mm / f_stop) if f_stop > 0 else float("inf")
    effective_f_number = (f_stop * (1.0 + (m if math.isfinite(m) else 0.0))) if f_stop > 0 else float("inf")

    if math.isfinite(m) and m > 0:
        fov_w_mm = sensor_w_mm / m
        fov_h_mm = sensor_h_mm / m
    else:
        fov_w_mm = float("inf")
        fov_h_mm = float("inf")
    fov_diag_mm = math.hypot(fov_w_mm, fov_h_mm)
    fov_area_mm2 = (fov_w_mm * fov_h_mm) if math.isfinite(fov_w_mm) and math.isfinite(fov_h_mm) else float("inf")

    pixels_per_mm_x = (pixels_horz / fov_w_mm) if fov_w_mm > 0 and pixels_horz > 0 else 0.0
    pixels_per_mm_y = (pixels_vert / fov_h_mm) if fov_h_mm > 0 and pixels_vert > 0 else 0.0
    mm_per_pixel_x = (1.0 / pixels_per_mm_x) if pixels_per_mm_x > 0 else float("inf")
    mm_per_pixel_y = (1.0 / pixels_per_mm_y) if pixels_per_mm_y > 0 else float("inf")

    target_fov_w = _as_float(params, "target_fov_width")
    target_fov_h = _as_float(params, "target_fov_height")
    fov_width_actual_vs_target_percent = float("nan")
    fov_height_actual_vs_target_percent = float("nan")
    if target_fov_w and target_fov_w > 0 and math.isfinite(fov_w_mm) and fov_w_mm > 0:
        fov_width_actual_vs_target_percent = (fov_w_mm / target_fov_w) * 100.0
    if target_fov_h and target_fov_h > 0 and math.isfinite(fov_h_mm) and fov_h_mm > 0:
        fov_height_actual_vs_target_percent = (fov_h_mm / target_fov_h) * 100.0

    sensor_fps = _as_float(params, "sensor_framerate") or 0.0
    frame_period_us = (1e6 / sensor_fps) if sensor_fps > 0 else float("inf")
    allowed_blur_px = _as_float(params, "object_allowed_blur_pixels") or 0.0
    object_speed_mm_s = _as_float(params, "object_initial_speed_mm_s") or 0.0
    motion_axis = str(params.get("object_motion_axis", "W")).strip().upper()
    px_per_mm_axis = pixels_per_mm_y if motion_axis == "H" else pixels_per_mm_x
    object_speed_px_s = object_speed_mm_s * px_per_mm_axis
    if object_speed_px_s > 0 and allowed_blur_px > 0:
        max_exposure_us_motion = 1e6 * (allowed_blur_px / object_speed_px_s)
    elif object_speed_mm_s <= 0:
        max_exposure_us_motion = float("inf")
    else:
        max_exposure_us_motion = 0.0
    max_exposure_us_frame = frame_period_us
    # Always recommend exposure for <= 1 pixel blur on the selected axis
    if object_speed_px_s > 0:
        max_exposure_us_motion_1px = 1e6 * (1.0 / object_speed_px_s)
    else:
        max_exposure_us_motion_1px = float("inf")
    recommended_exposure_us = min(max_exposure_us_motion_1px, max_exposure_us_frame)

    coc_mm = pixel_size_mm_min if math.isfinite(pixel_size_mm_min) else max((px_w_um or 0.0), (px_h_um or 0.0)) / 1000.0
    dof = _dof_hyperfocal(f_mm, f_stop, coc_mm if coc_mm > 0 else 1e-3, working_distance_mm)

    diff = _diffraction_sampling_metrics(pixel_size_mm_min if pixel_size_mm_min > 0 else 1e-6, max(effective_f_number, 1e-9))
    lens_mtf50_lp_per_mm = lens_resolution_lp_per_mm if lens_resolution_lp_per_mm is not None else 0.5 * diff["diffraction_cutoff_lp_per_mm"]
    mtf50_vs_nyquist_ratio = lens_mtf50_lp_per_mm / diff["sensor_nyquist_lp_per_mm"] if diff["sensor_nyquist_lp_per_mm"] > 0 else float("inf")
    if diff["nyquist_over_diffraction_cutoff"] > 1.1:
        sampling_regime = "optics-limited (diffraction)"
    elif lens_mtf50_lp_per_mm < 0.9 * diff["sensor_nyquist_lp_per_mm"]:
        sampling_regime = "optics-limited (aberrations)"
    elif diff["nyquist_over_diffraction_cutoff"] < 0.9:
        sampling_regime = "sensor-limited"
    else:
        sampling_regime = "balanced"

    coverage_ok = (lens_diag_mm >= (sensor_diag_mm or 0.0)) if lens_diag_mm and sensor_diag_mm else bool(lens_diag_mm and sensor_diag_mm and lens_diag_mm >= sensor_diag_mm)
    coverage_margin_mm = 0.5 * (lens_diag_mm - (sensor_diag_mm or 0.0)) if lens_diag_mm and sensor_diag_mm else float("nan")
    coverage_ratio_actual_vs_design = ((sensor_diag_mm or 0.0) / lens_diag_mm) if lens_diag_mm > 0 and sensor_diag_mm else float("nan")
    fov_width_scale_vs_design = coverage_ratio_actual_vs_design
    fov_height_scale_vs_design = coverage_ratio_actual_vs_design
    fov_area_scale_vs_design = (coverage_ratio_actual_vs_design ** 2) if math.isfinite(coverage_ratio_actual_vs_design) else float("nan")

    if lens_distortion_perc is not None and math.isfinite(coverage_ratio_actual_vs_design):
        if coverage_ratio_actual_vs_design <= 1.0:
            effective_distortion_percent_at_actual_edge = lens_distortion_perc * coverage_ratio_actual_vs_design
        else:
            effective_distortion_percent_at_actual_edge = lens_distortion_perc
    else:
        effective_distortion_percent_at_actual_edge = float("nan")

    if math.isfinite(effective_distortion_percent_at_actual_edge):
        edge_position_error_mm_effective = (effective_distortion_percent_at_actual_edge / 100.0) * (0.5 * fov_diag_mm)
    else:
        edge_position_error_mm_effective = float("nan")

    lens_relative_illumination = _as_float(params, "lens_relative_illumination")
    illum = _illumination_metrics(sensor_diag_mm or 0.0, di_mm, lens_relative_illumination)

    appearance_axis_used = motion_axis
    traversal_extent_mm = fov_h_mm if motion_axis == "H" else fov_w_mm
    duration_s = (traversal_extent_mm / object_speed_mm_s) if object_speed_mm_s > 0 and math.isfinite(traversal_extent_mm) else float("inf")
    expected_frames = (duration_s * sensor_fps) if sensor_fps > 0 and math.isfinite(duration_s) else float("inf")
    frames_min = int(math.floor(expected_frames)) if math.isfinite(expected_frames) else 0
    frames_max = int(math.ceil(expected_frames)) if math.isfinite(expected_frames) else 0
    displacement_per_frame_mm = (object_speed_mm_s / sensor_fps) if sensor_fps > 0 else float("inf")
    displacement_per_frame_px = displacement_per_frame_mm * px_per_mm_axis if math.isfinite(displacement_per_frame_mm) else float("inf")

    diffraction_dominant = diff["nyquist_over_diffraction_cutoff"] > 1.0
    exposure_limited_by_frame = max_exposure_us_frame < max_exposure_us_motion if math.isfinite(max_exposure_us_frame) and math.isfinite(max_exposure_us_motion) else False
    potential_vignetting = (not coverage_ok) or (illum["corner_to_center_ratio"] < 0.7)

    return {
        "sensor": {
            "pixels_horz": pixels_horz,
            "pixels_vert": pixels_vert,
            "total_pixels": total_pixels,
            "aspect_ratio": aspect_ratio,
            "sensor_nyquist_lp_per_mm": sensor_nyquist_lp_per_mm,
        },
        "lens_geometry": {
            "aperture_diameter_mm": aperture_diameter_mm,
            "effective_f_number": effective_f_number,
            "working_distance_mm": working_distance_mm,
            "image_distance_mm": di_mm,
            "magnification_percent": (m * 100.0 if math.isfinite(m) else float("inf")),
        },
        "fov_sampling": {
            "fov_width_mm": fov_w_mm,
            "fov_height_mm": fov_h_mm,
            "fov_diagonal_mm": fov_diag_mm,
            "fov_area_mm2": fov_area_mm2,
            "pixels_per_mm_x": pixels_per_mm_x,
            "pixels_per_mm_y": pixels_per_mm_y,
            "mm_per_pixel_x": mm_per_pixel_x,
            "mm_per_pixel_y": mm_per_pixel_y,
            "fov_width_actual_vs_target_percent": fov_width_actual_vs_target_percent,
            "fov_height_actual_vs_target_percent": fov_height_actual_vs_target_percent,
        },
        "motion_exposure": {
            "object_speed_mm_s": object_speed_mm_s,
            "object_speed_px_s": object_speed_px_s,
            "frame_period_us": frame_period_us,
            "max_exposure_us_motion_blur_for_allowed_blur_px": max_exposure_us_motion,
            "max_exposure_us_frame": max_exposure_us_frame,
            "recommended_exposure_us": recommended_exposure_us,
        },
        "depth_of_field": dof,
        "diffraction_mtf": {
            "wavelength_um": diff["wavelength_um"],
            "airy_disk_diameter_um": diff["airy_disk_diameter_um"],
            "airy_disk_diameter_pixels": diff["airy_disk_diameter_pixels"],
            "diffraction_cutoff_lp_per_mm": diff["diffraction_cutoff_lp_per_mm"],
            "nyquist_over_diffraction_cutoff": diff["nyquist_over_diffraction_cutoff"],
            "lens_mtf50_lp_per_mm": lens_mtf50_lp_per_mm,
            "mtf50_vs_nyquist_ratio": mtf50_vs_nyquist_ratio,
            "sampling_regime": sampling_regime,
        },
        "coverage_distortion": {
            "coverage_ok": coverage_ok,
            "coverage_margin_mm": coverage_margin_mm,
            "coverage_ratio_actual_vs_design": coverage_ratio_actual_vs_design,
            "fov_width_scale_vs_design": fov_width_scale_vs_design,
            "fov_height_scale_vs_design": fov_height_scale_vs_design,
            "fov_area_scale_vs_design": fov_area_scale_vs_design,
            "effective_distortion_percent_at_actual_edge": effective_distortion_percent_at_actual_edge,
            "edge_position_error_mm_effective": edge_position_error_mm_effective,
        },
        "illumination": illum,
        "appearances": {
            "appearance_axis_used": appearance_axis_used,
            "traversal_extent_mm": traversal_extent_mm,
            "duration_s": duration_s,
            "expected_frames": expected_frames,
            "frames_min": frames_min,
            "frames_max": frames_max,
            "displacement_per_frame_mm": displacement_per_frame_mm,
            "displacement_per_frame_px": displacement_per_frame_px,
        },
        "flags": {
            "diffraction_dominant": diffraction_dominant,
            "exposure_limited_by_frame": exposure_limited_by_frame,
            "potential_vignetting": potential_vignetting,
        },
    }


def main() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(script_dir, "input.json")
    results_path = os.path.join(script_dir, "results.json")

    with open(input_path, "r", encoding="utf-8") as f:
        params: Dict[str, Any] = json.load(f)

    results = calculate(params)

    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, sort_keys=True)

    print(f"Wrote results to {results_path}")


if __name__ == "__main__":
    main()



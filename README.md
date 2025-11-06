# Nyquist Architect - Imaging System Calculator

This repo packages the calculator with a JSON input (`input.json`), a runner (`run.py`) that writes `results.json`.

## Overview

A tiny optics + vision calculator to de‑risk camera design. It turns real camera + lens + scene inputs into the numbers you need to spec and de‑risk a design. It bundles first‑order optics, sampling theory, and a few practical heuristics into one pass.

### What it computes (high level)
- Sensor: pixel grid estimates, aspect, and sensor Nyquist (lp/mm)
- Lens/geometry: aperture diameter, effective f‑number, image distance, magnification
- FOV & sampling: object‑space FOV (W/H/diag/area), pixels/mm, mm/px
- Motion & exposure: object speed in px/s, blur‑limited exposure, frame‑limited exposure, recommended exposure
- DOF: near/far limits, hyperfocal, DOF span using pixel pitch as CoC
- Diffraction & MTF: Airy disk, diffraction cutoff, lens MTF50 vs. sensor Nyquist, regime label (sensor‑limited vs optics‑limited)
- Coverage & distortion: image‑circle coverage check, margin, effective distortion at the actual edge, edge error in mm
- Illumination: corner falloff (cos⁴ estimate or datasheet), compensation in stops
- Appearances: how long an object stays in frame, expected frames, min/max frames, displacement per frame (mm and px)

### Why it’s useful
- Choose focal length and working distance to hit a target FOV with adequate sampling
- Set f‑number with eyes on both DOF and diffraction
- Pick frame rate and exposure that respect motion‑blur constraints
- Evaluate whether a lens (format, MTF, distortion) is suitable for your sensor
- Anticipate vignetting and compensation needs at the corners
- Communicate design trade‑offs with numbers, not guesswork

> Once the parameters have been set for your application,  It is difficult to change them later,
>
>
> upfront planning for the exact calculation are therefore crucial for the lasting performance of the vision system

### How it works (first‑order and transparent)
- Thin‑lens (1/f = 1/do + 1/di) → magnification and image distance
- FOV ∝ sensor size / magnification → sampling in object space (px/mm, mm/px)
- Motion blur: exposure ≤ allowed_blur_px / (speed_px_per_s)
- DOF via hyperfocal with CoC = pixel pitch (conservative, sampling‑aligned)
- Diffraction: Airy = 2.44·λ·N, cutoff ≈ 1/(λ·N), compared to sensor Nyquist
- Illumination: cos⁴(θ) at corners unless provided by datasheet

## How to run

```bash
python /home/keanay/operation_pinhole/neo_calc/run.py
```

- Edit `input.json` to match your camera, lens, and scene.
- Running the command writes the categorized JSON to `results.json`.

---

## Input Documentation (input.json)

Unless noted, units are millimeters (mm), micrometers (µm), seconds (s), and frames per second (fps).

- sensor_width_mm (mm): Active sensor width. Used with magnification to compute FOV width.
- sensor_height_mm (mm): Active sensor height. Used with magnification to compute FOV height.
- sensor_diagonal_mm (mm, optional): Sensor diagonal. If omitted, derived from width/height.
- sensor_pixel_size_width_um (µm): Pixel pitch along width. If missing, mirrored from height.
- sensor_pixel_size_height_um (µm): Pixel pitch along height. If missing, mirrored from width.
- sensor_framerate (fps): Camera frame rate. Sets frame_period_us and caps exposure.
- lens_diagonal_mm (mm): Lens image-circle diagonal (coverage check vs sensor).
- lens_focal_length_mm (mm): Lens focal length. Drives magnification with working distance.
- lens_fstop (f-number): Aperture setting. Affects effective f-number, diffraction, and DOF.
- lens_resolution (lp/mm at ~MTF50): Lens contrast/resolution figure. If omitted, a heuristic from diffraction cutoff is used.
- lens_relative_illumination (percent or ratio 0–1): Corner illumination relative to center. If omitted, cos⁴ estimate is used.
- lens_pixel_pitch_um (µm): Informational reference to lens-supported sensor pitch (not used in calculations).
- lens_distortion_perc (%): Radial distortion at full field. Scaled to effective used field for edge error.
- working_distance_mm (mm): Object distance. Combined with focal length in thin lens to set magnification.
- object_initial_speed_mm_s (mm/s): Object speed along the chosen axis. Used for motion blur and appearances.
- object_allowed_blur_pixels (px): Allowed motion blur for the reference motion-blur exposure metric.
  - Note: recommended_exposure_us is always computed for ≤ 1 px blur on the selected axis, independent of this value.
- object_motion_axis ('H' or 'W'): Motion axis. 'H' uses vertical FOV; 'W' uses horizontal FOV for appearances and px/s.
- target_fov_width (mm, optional): Target FOV width. Used for fov_width_actual_vs_target_percent.
- target_fov_height (mm, optional): Target FOV height. Used for fov_height_actual_vs_target_percent.

General notes:
- Magnification m and image distance are from the thin-lens model (paraxial approximation).
- Sensor Nyquist uses the tighter (smaller) pixel pitch across axes.
- Coverage/distortion uses lens vs sensor diagonal; edge error scales with used field radius.
- Illumination corner estimate defaults to cos⁴ unless a datasheet value is provided.

## Output Documentation

The calculator returns a JSON object organized into nested categories. Each field’s meaning, design significance, and the key input parameters that influence it are described below. Inputs refer to keys in the top-level `input.json` unless otherwise stated (some values are derived from others as noted).

### sensor
- **pixels_horz (px)**: Estimated sensor horizontal pixel count based on sensor size and pixel pitch.  
  Significance: Sets sampling density horizontally; used for pixels/mm and blur in px/s.  
  Inputs: `sensor_width_mm`, `sensor_pixel_size_width_um` (mirrors height if missing).
- **pixels_vert (px)**: Estimated sensor vertical pixel count based on sensor size and pixel pitch.  
  Significance: Sets sampling density vertically; used for pixels/mm and blur in px/s.  
  Inputs: `sensor_height_mm`, `sensor_pixel_size_height_um` (mirrors width if missing).
- **total_pixels (px)**: pixels_horz × pixels_vert.  
  Significance: Overall sensor sampling capacity; useful for data rate and coverage planning.  
  Inputs: Derived from pixels_horz, pixels_vert.
- **aspect_ratio (unitless)**: sensor_width_mm ÷ sensor_height_mm.  
  Significance: Governs FOV shape in object space for a given magnification.  
  Inputs: `sensor_width_mm`, `sensor_height_mm`.
- **sensor_nyquist_lp_per_mm (lp/mm)**: Nyquist frequency from the tighter pixel pitch (1/(2·pixel_size_mm_min)).  
  Significance: Sampling limit to compare against optics/diffraction.  
  Inputs: `sensor_pixel_size_width_um`, `sensor_pixel_size_height_um` (uses the smaller pitch).

### lens_geometry
- **aperture_diameter_mm (mm)**: Physical entrance pupil diameter (focal_length_mm / f_stop).  
  Significance: Relates to light throughput and diffraction scale (via f-number).  
  Inputs: `lens_focal_length_mm`, `lens_fstop`.
- **effective_f_number (unitless)**: f_stop scaled by (1 + magnification).  
  Significance: Realistic f-number at the sensor under magnification; affects diffraction.  
  Inputs: `lens_fstop`, `lens_focal_length_mm`, `working_distance_mm` (magnification derived from thin lens).
- **working_distance_mm (mm)**: Object distance used in thin-lens geometry.  
  Significance: Primary driver of magnification and FOV for a fixed focal length.  
  Inputs: `working_distance_mm`.
- **image_distance_mm (mm)**: Image distance from thin-lens equation.  
  Significance: Useful for cos^4 illumination estimate and geometric sanity checks.  
  Inputs: `lens_focal_length_mm`, `working_distance_mm`.
- **magnification_percent (%)**: 100 × (image_distance / object_distance).  
  Significance: Maps sensor size to object-space FOV; directly controls sampling in scene units.  
  Inputs: `lens_focal_length_mm`, `working_distance_mm`.

### fov_sampling
- **fov_width_mm (mm)**: Object-space FOV width = sensor_width_mm / magnification.  
  Significance: Scene coverage along width; impacts required system standoff and composition.  
  Inputs: `sensor_width_mm`, `lens_focal_length_mm`, `working_distance_mm`.
- **fov_height_mm (mm)**: Object-space FOV height = sensor_height_mm / magnification.  
  Significance: Scene coverage along height; paired with width for area coverage.  
  Inputs: `sensor_height_mm`, `lens_focal_length_mm`, `working_distance_mm`.
- **fov_diagonal_mm (mm)**: sqrt(fov_width_mm^2 + fov_height_mm^2).  
  Significance: Useful for distortion edge calculations and qualitative coverage checks.  
  Inputs: Derived from fov_width_mm and fov_height_mm.
- **fov_area_mm2 (mm^2)**: fov_width_mm × fov_height_mm.  
  Significance: Total scene area captured; used in coverage trade-offs.  
  Inputs: Derived from fov_width_mm and fov_height_mm.
- **pixels_per_mm_x (px/mm)**: Horizontal sampling density in object space.  
  Significance: Sets resolvable feature size and motion blur in px/s (width axis).  
  Inputs: `sensor_width_mm`, `sensor_pixel_size_width_um`, `lens_focal_length_mm`, `working_distance_mm`.
- **pixels_per_mm_y (px/mm)**: Vertical sampling density in object space.  
  Significance: Sets resolvable feature size and motion blur in px/s (height axis).  
  Inputs: `sensor_height_mm`, `sensor_pixel_size_height_um`, `lens_focal_length_mm`, `working_distance_mm`.
- **mm_per_pixel_x (mm/px)**: Reciprocal of pixels_per_mm_x.  
  Significance: Feature size per pixel horizontally (object space).  
  Inputs: Derived from pixels_per_mm_x.
- **mm_per_pixel_y (mm/px)**: Reciprocal of pixels_per_mm_y.  
  Significance: Feature size per pixel vertically (object space).  
  Inputs: Derived from pixels_per_mm_y.
- **fov_width_actual_vs_target_percent (%)**: 100 × (actual fov_width_mm / target_fov_width) if target provided.  
  Significance: Indicates how actual width compares to goal (100% = match, <100% tighter, >100% looser).  
  Inputs: `target_fov_width`, plus those that set fov_width_mm.
- **fov_height_actual_vs_target_percent (%)**: 100 × (actual fov_height_mm / target_fov_height) if target provided.  
  Significance: Indicates how actual height compares to goal.  
  Inputs: `target_fov_height`, plus those that set fov_height_mm.

### motion_exposure
- **object_speed_mm_s (mm/s)**: Object speed along selected motion axis.  
  Significance: Used to compute blur-limited exposure and appearance timing.  
  Inputs: `object_initial_speed_mm_s`.
- **object_speed_px_s (px/s)**: Object speed in pixel units along chosen axis.  
  Significance: Converts blur tolerance (px) to a time budget for exposure.  
  Inputs: `object_initial_speed_mm_s`, `object_motion_axis`, pixels_per_mm_(axis).
- **frame_period_us (µs)**: 1e6 / sensor_framerate.  
  Significance: Upper bound on exposure to avoid frame overlap (frame-limited).  
  Inputs: `sensor_framerate`.
- **max_exposure_us_motion_blur_for_allowed_blur_px (µs)**: Blur-limited exposure time for given px tolerance.  
  Significance: Ensures motion smear stays within acceptable pixel limit.  
  Inputs: `object_allowed_blur_pixels`, `object_initial_speed_mm_s`, `object_motion_axis`, pixels_per_mm_(axis).
- **max_exposure_us_frame (µs)**: Frame-limited exposure cap (equals frame_period_us).  
  Significance: Prevents overlapping frames; camera timing constraint.  
  Inputs: `sensor_framerate`.
- **recommended_exposure_us (µs)**: min(motion-blur limit, frame limit).  
  Significance: Practical exposure recommendation balancing motion blur and frame timing.  
  Inputs: Derived from motion-blur limit and frame limit.

### depth_of_field
- **circle_of_confusion_mm_used (mm)**: CoC set to tighter pixel pitch (conservative).  
  Significance: Ties DOF sharpness to sensor sampling capability.  
  Inputs: `sensor_pixel_size_width_um`, `sensor_pixel_size_height_um` (uses tighter pitch).
- **near_mm (mm)**: Near DOF limit via hyperfocal method.  
  Significance: Closest distance that remains acceptably sharp at the chosen f-number.  
  Inputs: `lens_focal_length_mm`, `lens_fstop`, CoC, `working_distance_mm`.
- **far_mm (mm or inf)**: Far DOF limit via hyperfocal method.  
  Significance: Farthest distance that remains acceptably sharp (can extend to infinity).  
  Inputs: `lens_focal_length_mm`, `lens_fstop`, CoC, `working_distance_mm`.
- **DOF_mm (mm or inf)**: Depth of field span (far - near).  
  Significance: Usable sharpness range for the subject depth.  
  Inputs: Derived from near_mm and far_mm.
- **hyperfocal_mm (mm)**: f^2/(N·c) + f.  
  Significance: Focusing here yields far limit at infinity; key DOF planning metric.  
  Inputs: `lens_focal_length_mm`, `lens_fstop`, CoC.

### diffraction_mtf
- **wavelength_um (µm)**: Wavelength used for diffraction estimates (default ~0.55 µm).  
  Significance: Sets scale of diffraction effects.  
  Inputs: Fixed at 0.55 µm in this setup.
- **airy_disk_diameter_um (µm)**: 2.44·λ·N (first-dark-ring diameter at sensor).  
  Significance: Blur kernel size from diffraction; grows with f-number.  
  Inputs: `lens_fstop`, magnification (via effective_f_number), wavelength.
- **airy_disk_diameter_pixels (px)**: Airy diameter expressed in pixel units.  
  Significance: Compares diffraction blur to pixel sampling directly.  
  Inputs: Airy diameter and sensor pixel pitch (tighter axis).
- **diffraction_cutoff_lp_per_mm (lp/mm)**: ~1/(λ·N).  
  Significance: Theoretical incoherent cutoff; optics cannot pass higher frequencies.  
  Inputs: `lens_fstop`, magnification (via effective_f_number), wavelength.
- **nyquist_over_diffraction_cutoff (unitless)**: Sensor Nyquist ÷ diffraction cutoff.  
  Significance: >1: optics-limited (diffraction); <1: sensor-limited regime.  
  Inputs: sensor Nyquist (from pixel pitch), diffraction cutoff.
- **lens_mtf50_lp_per_mm (lp/mm)**: Lens MTF50 (datasheet or heuristic if unknown).  
  Significance: Practical contrast/resolution indicator; compare to Nyquist.  
  Inputs: `lens_resolution` (if provided), else derived from diffraction cutoff.
- **mtf50_vs_nyquist_ratio (unitless)**: lens_mtf50_lp_per_mm ÷ sensor_nyquist_lp_per_mm.  
  Significance: <1 implies optics likely limit contrast before sampling does.  
  Inputs: `lens_resolution`, pixel pitch (sensor Nyquist).
- **sampling_regime (str)**: Qualitative label: sensor-limited, optics-limited, or balanced.  
  Significance: Guides whether to change f-number/pixel pitch/lens.  
  Inputs: Derived from the above metrics.

### coverage_distortion
- **coverage_ok (bool)**: True if lens image circle diagonal ≥ sensor diagonal.  
  Significance: Basic check for vignetting risk and coverage.  
  Inputs: `lens_diagonal_mm`, `sensor_diagonal_mm` (or derived from `sensor_width_mm`, `sensor_height_mm`).
- **coverage_margin_mm (mm)**: 0.5 × (lens_diag − sensor_diag).  
  Significance: Positive margin indicates safety against shading/vignetting.  
  Inputs: `lens_diagonal_mm`, `sensor_diagonal_mm` (or derived).
- **coverage_ratio_actual_vs_design (unitless)**: sensor_diag / lens_diag.  
  Significance: >1 means sensor exceeds rated image circle (risk region).  
  Inputs: `lens_diagonal_mm`, `sensor_diagonal_mm` (or derived).
- **fov_width_scale_vs_design (unitless)**, **fov_height_scale_vs_design (unitless)**, **fov_area_scale_vs_design (unitless)**: Scaling vs design format (diagonal-based when exact size unknown).  
  Significance: Relative FOV scaling; useful when repurposing lenses across formats.  
  Inputs: `lens_diagonal_mm`, `sensor_diagonal_mm` (diagonal ratio proxy).
- **effective_distortion_percent_at_actual_edge (%)**: Distortion scaled to used field radius (clamped beyond spec).  
  Significance: More realistic distortion at cropped edge; influences metrology accuracy.  
  Inputs: `lens_distortion_perc`, coverage_ratio_actual_vs_design.
- **edge_position_error_mm_effective (mm)**: Edge displacement in object space from effective distortion.  
  Significance: Upper bound on feature localization error at FOV edge.  
  Inputs: effective distortion and FOV diagonal.

### illumination
- **relative_illumination_center_percent (%)**: Normalized to 100 at image center.  
  Significance: Reference baseline for corner fall-off comparisons.  
  Inputs: Fixed to 100 (reference).
- **relative_illumination_corner_percent (%)**: Corner brightness vs center (percent).  
  Significance: Shading at corners; impacts exposure uniformity and SNR.  
  Inputs: `lens_relative_illumination` (if provided); else cos⁴ estimate using `sensor_diagonal_mm` and `image_distance_mm`.
- **corner_to_center_ratio (unitless)**: Corner/center illumination ratio (0–1).  
  Significance: Direct uniformity metric; higher is flatter field.  
  Inputs: Same as above (percent/100).
- **vignetting_loss_percent (%)**: 100 − corner_percent.  
  Significance: Exposure loss at corners; informs compensation or lens choice.  
  Inputs: Derived from relative_illumination_corner_percent.
- **exposure_compensation_stops_at_corners (stops)**: log2(1/ratio).  
  Significance: Additional stops required to equalize corners to center.  
  Inputs: Derived from corner_to_center_ratio.

### appearances
- **appearance_axis_used ('H'/'W')**: Axis used for motion (height or width).  
  Significance: Chooses which FOV dimension sets traversal distance and px/s.  
  Inputs: `object_motion_axis`.
- **traversal_extent_mm (mm)**: FOV extent along the chosen motion axis.  
  Significance: Distance to traverse within the frame along that axis.  
  Inputs: `object_motion_axis`, `fov_height_mm`/`fov_width_mm`.
- **duration_s (s)**: Time the object remains within the FOV assuming constant speed.  
  Significance: Window for capturing the event; informs frame count expectations.  
  Inputs: `object_initial_speed_mm_s`, traversal_extent_mm.
- **expected_frames (frames)**: duration_s × sensor_framerate.  
  Significance: Average number of frames; actual integer depends on phase.  
  Inputs: `sensor_framerate`, duration_s.
- **frames_min / frames_max (frames)**: floor/ceil of expected_frames.  
  Inputs: Derived from expected_frames.
- **displacement_per_frame_mm (mm/frame)**: object_speed_mm_s / sensor_framerate.  
  Significance: Scene motion per frame in mm; relates to blur and tracking.  
  Inputs: `object_initial_speed_mm_s`, `sensor_framerate`.
- **displacement_per_frame_px (px/frame)**: displacement_per_frame_mm × pixels_per_mm_(axis).  
  Significance: Pixel motion per frame; impacts tracking and feature stability.  
  Inputs: displacement_per_frame_mm, pixels_per_mm_(axis).

### flags
- **diffraction_dominant (bool)**: True if sensor sampling exceeds diffraction limit significantly.  
  Significance: Optics (diffraction) likely limit resolution; stopping down further hurts detail.  
  Inputs: `lens_fstop`, `lens_focal_length_mm`, `working_distance_mm` (via magnification/effective f-number), `sensor_pixel_size_*_um`, wavelength (0.55 µm).
- **exposure_limited_by_frame (bool)**: True if frame period < motion-blur-limited exposure.  
  Significance: Exposure is capped by frame timing rather than motion blur tolerance.  
  Inputs: `sensor_framerate`, `object_allowed_blur_pixels`, `object_initial_speed_mm_s`, `object_motion_axis`, pixels_per_mm_(axis).
- **potential_vignetting (bool)**: True if coverage not OK or corner ratio < 0.7.  
  Significance: Highlights risk of dark corners or inadequate image-circle coverage.  
  Inputs: `lens_diagonal_mm`, `sensor_diagonal_mm` (or derived), `lens_relative_illumination` (if provided) or cos⁴ estimate; threshold at 0.7.



"""Local image/prompt-to-CNC bas-relief generation.

The model weights are cached by Hugging Face. Inference runs in CarveFoundry's
existing isolated job subprocess; this module deliberately imports no Qt or ML
dependencies at module import time.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import trimesh

DEPTH_MODEL_ID = "depth-anything/Depth-Anything-V2-Small-hf"
TEXT_MODEL_ID = "stabilityai/sd-turbo"
Progress = Callable[[float, str], None]


@dataclass(frozen=True, slots=True)
class ReliefRequest:
    output_path: str
    width_mm: float
    height_mm: float
    relief_depth_mm: float = 4.0
    backing_thickness_mm: float = 1.5
    grid_samples: int = 256
    image_path: str = ""
    prompt: str = ""
    invert_depth: bool = False
    smoothing_px: float = 0.6

    def validate(self) -> None:
        measurements = (
            self.width_mm, self.height_mm, self.relief_depth_mm,
            self.backing_thickness_mm, self.smoothing_px,
        )
        if not np.isfinite(measurements).all():
            raise ValueError("Relief measurements must be finite.")
        if self.width_mm <= 0 or self.height_mm <= 0:
            raise ValueError("Relief width and height must be positive.")
        if self.relief_depth_mm <= 0 or self.backing_thickness_mm <= 0:
            raise ValueError("Relief depth and backing thickness must be positive.")
        if self.smoothing_px < 0 or self.smoothing_px > 12:
            raise ValueError("Smoothing must be between 0 and 12 pixels.")
        if not 32 <= self.grid_samples <= 384:
            raise ValueError("Grid samples must be between 32 and 384.")
        if bool(self.image_path.strip()) == bool(self.prompt.strip()):
            raise ValueError("Choose exactly one source: an image or a text prompt.")
        if self.image_path and not Path(self.image_path).is_file():
            raise ValueError("Source image does not exist.")
        output = Path(self.output_path).expanduser()
        if output.suffix.lower() != ".stl" or not output.name.strip():
            raise ValueError("Output must be a .stl file.")
        if not output.parent.is_dir():
            raise ValueError("Output folder does not exist.")


def mesh_from_depth(
    depth: np.ndarray,
    *,
    width_mm: float,
    height_mm: float,
    relief_depth_mm: float,
    backing_thickness_mm: float,
    invert_depth: bool = False,
    smoothing_px: float = 0.0,
) -> trimesh.Trimesh:
    """Make a closed, correctly wound heightfield solid in millimeters.

    The near surface is higher than the distant surface. The backing and four
    sidewalls make the exported STL watertight, unlike a single open heightmap.
    """
    from PIL import Image, ImageFilter

    values = np.asarray(depth, dtype=np.float32)
    if values.ndim != 2 or min(values.shape) < 2 or not np.isfinite(values).all():
        raise ValueError("Depth estimation must produce a finite 2D array.")
    if not np.isfinite((width_mm, height_mm, relief_depth_mm, backing_thickness_mm)).all():
        raise ValueError("Mesh dimensions must be finite.")
    if min(width_mm, height_mm, relief_depth_mm, backing_thickness_mm) <= 0:
        raise ValueError("Mesh dimensions must be positive.")
    if not np.isfinite(smoothing_px) or not 0 <= smoothing_px <= 12:
        raise ValueError("Invalid smoothing amount.")

    # The model predicts *relative* depth. Clip outliers before scaling to
    # a physical CNC relief height; do not treat predictions as millimeters.
    low, high = np.percentile(values, (1, 99))
    if high - low < 1e-8:
        raise ValueError("Depth map is flat; no relief can be generated.")
    heights = np.clip((values - low) / (high - low), 0, 1)
    if invert_depth:
        heights = 1 - heights
    if smoothing_px:
        image = Image.fromarray(np.asarray(heights, dtype=np.float32), mode="F")
        heights = np.asarray(
            image.filter(ImageFilter.GaussianBlur(radius=smoothing_px)), dtype=np.float32
        )
        heights = np.clip(heights, 0, 1)

    rows, cols = heights.shape
    x = np.linspace(0, width_mm, cols, dtype=np.float32)
    y = np.linspace(height_mm, 0, rows, dtype=np.float32)
    xx, yy = np.meshgrid(x, y)
    upper = np.column_stack((
        xx.ravel(), yy.ravel(),
        (backing_thickness_mm + relief_depth_mm * heights).ravel(),
    ))
    lower = upper.copy()
    lower[:, 2] = 0
    vertices = np.vstack((upper, lower))
    count = rows * cols
    a = np.arange(count, dtype=np.int32).reshape(rows, cols)[:-1, :-1].ravel()
    b, c, d = a + 1, a + cols, a + cols + 1
    # The image row axis points toward negative Y. Reverse the face winding
    # from the usual array indexing so the relief top points toward +Z.
    upper_faces = np.vstack((
        np.column_stack((a, c, b)),
        np.column_stack((b, c, d)),
    ))
    bottom_faces = np.vstack((
        np.column_stack((a + count, b + count, c + count)),
        np.column_stack((b + count, d + count, c + count)),
    ))

    # Counter-clockwise XY perimeter, viewed from above.
    border = np.array(
        [((rows - 1) * cols + col) for col in range(cols)]
        + [(row * cols + cols - 1) for row in range(rows - 2, -1, -1)]
        + [col for col in range(cols - 2, -1, -1)]
        + [(row * cols) for row in range(1, rows - 1)],
        dtype=np.int32,
    )
    following = np.roll(border, -1)
    walls = np.vstack((
        np.column_stack((border, border + count, following)),
        np.column_stack((following, border + count, following + count)),
    ))
    faces = np.vstack((upper_faces, bottom_faces, walls))
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    if not mesh.is_watertight or mesh.volume <= 0:
        raise ValueError("Generated bas-relief has invalid closed geometry.")
    mesh.metadata["units"] = "mm"
    return mesh


def _prompt_image(prompt: str, report: Progress):
    """Generate the reference image entirely in the local worker process."""
    try:
        import torch
        from diffusers import AutoPipelineForText2Image
    except ImportError as exc:
        raise RuntimeError(
            "Local text generation needs the optional AI packages: "
            "pip install -e '.[ai]' (and a compatible PyTorch build)."
        ) from exc
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    report(0.07, "Loading local text-to-image model (first use downloads weights)")
    pipe = AutoPipelineForText2Image.from_pretrained(TEXT_MODEL_ID, torch_dtype=dtype)
    pipe = pipe.to(device)
    report(0.18, "Generating reference image locally")
    with torch.inference_mode():
        result = pipe(
            prompt=(
                "Orthographic front view of a single sculpted bas-relief subject, "
                "centered composition, simple clean background, directional "
                "shading, no text, no frame, no perspective: " + prompt
            ),
            num_inference_steps=2,
            guidance_scale=0.0,
            height=512,
            width=512,
        )
    image = result.images[0].convert("RGB")
    del result, pipe
    return image


def _estimate_depth(image, report: Progress) -> np.ndarray:
    try:
        import torch
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation
    except ImportError as exc:
        raise RuntimeError(
            "Local depth estimation needs the optional AI packages: "
            "pip install -e '.[ai]' (and a compatible PyTorch build)."
        ) from exc
    device = "cuda" if torch.cuda.is_available() else "cpu"
    report(0.30, "Loading local Depth Anything V2 (first use downloads weights)")
    processor = AutoImageProcessor.from_pretrained(DEPTH_MODEL_ID)
    model = AutoModelForDepthEstimation.from_pretrained(DEPTH_MODEL_ID).to(device)
    model.eval()
    report(0.53, "Estimating relative depth locally")
    inputs = processor(images=image, return_tensors="pt").to(device)
    with torch.inference_mode():
        result = model(**inputs)
        depth = processor.post_process_depth_estimation(
            result, target_sizes=[(image.height, image.width)]
        )[0]["predicted_depth"]
    array = depth.detach().float().cpu().numpy()
    del model, inputs, result, depth
    return array


def generate_relief(request: ReliefRequest, report: Progress) -> dict[str, object]:
    """Save STL atomically; return its path for normal CarveFoundry STL import."""
    from PIL import Image

    request.validate()
    destination = Path(request.output_path).expanduser()
    if request.image_path:
        report(0.05, "Opening source image")
        with Image.open(request.image_path) as source:
            image = source.convert("RGB")
    else:
        image = _prompt_image(request.prompt.strip(), report)

    depth = _estimate_depth(image, report)
    report(0.72, "Preparing CNC resolution")
    longest = max(request.width_mm, request.height_mm)
    cols = max(16, round(request.grid_samples * request.width_mm / longest))
    rows = max(16, round(request.grid_samples * request.height_mm / longest))
    depth_image = Image.fromarray(np.asarray(depth, dtype=np.float32), mode="F")
    depth = np.asarray(
        depth_image.resize((cols, rows), resample=Image.Resampling.BILINEAR),
        dtype=np.float32,
    )
    report(0.78, "Building closed bas-relief geometry")
    mesh = mesh_from_depth(
        depth,
        width_mm=request.width_mm,
        height_mm=request.height_mm,
        relief_depth_mm=request.relief_depth_mm,
        backing_thickness_mm=request.backing_thickness_mm,
        invert_depth=request.invert_depth,
        smoothing_px=request.smoothing_px,
    )
    report(0.89, "Writing STL")
    fd, pending = tempfile.mkstemp(
        prefix=f".{destination.stem}-", suffix=".stl.tmp", dir=destination.parent
    )
    os.close(fd)
    try:
        mesh.export(pending, file_type="stl")
        os.replace(pending, destination)
    finally:
        Path(pending).unlink(missing_ok=True)

    reference_path = ""
    if request.prompt:
        # Preserve the actual generated input next to the STL for later
        # reproducibility and manual refinement, without modifying the project.
        reference = destination.with_name(destination.stem + "_source.png")
        image.save(reference)
        reference_path = str(reference)
    report(0.96, "STL ready for import")
    return {
        "path": str(destination),
        "source_image": reference_path,
        "vertices": len(mesh.vertices),
        "faces": len(mesh.faces),
    }

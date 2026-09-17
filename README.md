# CarveFoundry

CarveFoundry is a native Linux CNC design and CAM application with an approachable, ribbon-based workflow. It is being built for Linux/Wayland first, with strong support for common CNC workflows including Onefinity-style GRBL machines.

## Project direction

CarveFoundry aims to cover the practical workflow people often use Easel for while giving more control over imported geometry, cutter definitions, 3D relief work, preview, optimization, and G-code export.

Planned and current areas include:

- 2D/2.5D design and CAM workflows
- SVG, DXF, image, STL, and G-code import paths
- first-class STL mesh import with retained geometry and mesh metadata
- stock and project setup
- cutter-aware CAM using the actual selected cutter profile
- roughing and finishing strategies for 3-axis CNC
- preview and simulation
- G-code export
- Linux/Wayland-native desktop behavior

## Cutter geometry

CarveFoundry is not designed around a ball-nose-only 3D finishing assumption. Cutter definitions model the actual cutter profile so flat end mills, ball noses, V-bits, engraving/conical tools, tapered ball noses, and future custom revolved profiles can be handled by the CAM engine.

## Development

Requires Python 3.12 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e '.[dev]'
carvefoundry
```

Run the test and lint suites with:

```bash
ruff check src tests
pytest -q
```

# CarveFoundry

CarveFoundry is a native Linux CNC design and CAM application. The goal is an approachable design-to-G-code workflow in the spirit of browser-based tools such as Easel, without requiring the browser or cloud for normal use.

The UI uses the same dark navy / lime-accent visual language as Bi-Weekly Bills, adapted to a Microsoft Office-style ribbon and a large CAD/CAM workspace.

## Early project goals

- Native PySide6 Linux desktop application with first-class Wayland support.
- SVG, DXF, STL, image, and G-code import.
- 2D / 2.5D operations: profile, pocket, engraving, V-carve, drilling, and tabs.
- STL-based 3D roughing, finishing, rest machining, and boundary control.
- Cutter-aware 3D toolpaths. Finishing is **not** restricted to ball-nose cutters; the CAM engine is designed to compensate for the selected cutter profile.
- Tool library for flat end mills, ball noses, V-bits, engraving/conical tools, tapered ball noses, and custom profiles.
- Toolpath preview, simulation, feeds/speeds, stock setup, origins, machine profiles, and postprocessors.
- GRBL / Onefinity-friendly G-code as an early target, with postprocessors kept modular.

## Run from source on Arch Linux

```bash
git clone git@github.com:newnetmp3/CarveFoundry.git
cd CarveFoundry
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e '.[dev]'
carvefoundry
```

## Status

CarveFoundry is in early development. The initial application shell establishes the ribbon-based UI, project workspace, tool library model, and cutter-profile abstraction that future CAM operations will use.

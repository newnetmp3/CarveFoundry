# CarveFoundry Web — isolated early preview

A new browser-first frontend for CarveFoundry, designed for eventual hosting at
**https://cnc.skotic.com**. This is a **prototype**: CNC toolpath visualization
is not verified for machining and G-code export is deliberately disabled.

## Desktop independence

All application sources live in `web/`. Its Rust crate (`web/engine/`)
is separate from the desktop `rust/` PyO3 extension; none of the desktop
Python, UI, project file, Rust, packaging, or dependency files have changed.

The desktop application remains the existing source of truth for CAM correctness.
We will add cross-engine regression test vectors before shipping G-code.

## Current capabilities

- React/TypeScript and interactive Three.js 3D stock viewport; orbit, pan, zoom.
- Select and edit rectangle/ellipse designs and stock dimensions.
- Explicit stock-bottom-left XY origin and stock-top Z0.
- Load/save **local web-only JSON** projects (NOT desktop .cf3d yet).
- Run a real independent Rust/WebAssembly raster pocket preview inside a
  dedicated browser Web Worker, including depth passes and input validation.
- No CAM computation server; local preview works without authentication.
- Hard-disabled NC export with visible prototype warnings.

Not yet implemented: STL import, .cf3d compatibility, object-based toolpaths,
full cutter compensation, arbitrary 3D machining, independent preflight, G-code
verification, fixture clearance, saved cloud projects, accounts and R2/D1.

**Do not send these demonstration paths to a CNC machine.**

## Local development

Requires Node.js 22+, Rust stable, wasm32-unknown-unknown target, and wasm-pack.

```sh
rustup target add wasm32-unknown-unknown
cargo install wasm-pack --locked
cd web
npm install
npm run dev
```

The Vite development server runs at http://127.0.0.1:5173.
The first command automatically compiles `web/engine` to
`web/src/wasm/pkg` (ignored by git). The project has no backend.

Production build, checks and Rust tests:

```sh
cd web
npm run build
npm run check
cargo test --manifest-path engine/Cargo.toml
```

The build output is `web/dist`. The CI workflow is restricted to
`web/**` and its own GitHub workflow file.

## Cloudflare Pages & temporary domain

See [CLOUDFLARE.md](./CLOUDFLARE.md) for one-time Cloudflare setup,
GitHub Actions deployment and `cnc.skotic.com` domain attachment. The
repo cannot provision your Cloudflare account or change DNS without an
authorized Cloudflare API connection/token.

There are **no user accounts or cloud files** in this milestone. Users can
download and reopen their local projects. Hosted storage will be integrated
only after the main design and CAM data formats are stable.

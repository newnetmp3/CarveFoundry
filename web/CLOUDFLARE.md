# Deployment at cnc.skotic.com

The preview uses **Cloudflare Pages Free**, with all CAM processing
performed in browser WebAssembly. No Python backend or Containers needed.

**Important:** Adding these files does not create a Cloudflare Pages project,
DNS record, certificate or live website. Those require access to your
Cloudflare account. No domain has been claimed to be active.

## One-time setup (mostly automated)

1. In GitHub → `newnetmp3/CarveFoundry` → **Settings** →
   **Secrets and variables** → **Actions**, add these repository secrets:
   - `CLOUDFLARE_API_TOKEN`: a Cloudflare API token scoped to your account
     with **Cloudflare Pages Write** permission. Keep it secret.
   - `CLOUDFLARE_ACCOUNT_ID`: account ID for the Cloudflare account
     containing the `skotic.com` zone.
2. After merging the web foundation, go to **GitHub Actions** →
   **Deploy CarveFoundry Web** → **Run workflow** on the `main` branch.
3. The workflow will **automatically**:
   - Create `carvefoundry-web` Pages project if it doesn't already exist.
   - Compile local Rust to WASM, build React and deploy `web/dist`.
   - Attach `cnc.skotic.com` to the Pages project.
4. In Cloudflare Pages → `carvefoundry-web` → **Custom domains**,
   confirm `cnc.skotic.com` moves to **Active** and the HTTPS
   certificate finishes provisioning. If `skotic.com` is hosted
   in the same Cloudflare account, Cloudflare generally configures its
   CNAME automatically during attachment.
5. Verify both `https://carvefoundry-web.pages.dev` and
   `https://cnc.skotic.com` open the early preview and that local WASM
   calculations finish. NC export must remain disabled.

The workflow reports a notice and skips deployment if the secrets
have not been configured. Without an authenticated Cloudflare connection
in this chat, I cannot supply those secrets, create DNS records, or
confirm activation.

If your `skotic.com` DNS is at a different provider, manually create
a **cnc CNAME** to `carvefoundry-web.pages.dev` **after** the
Cloudflare Pages custom-domain attachment. A DNS CNAME alone is not enough.

You may also run `bash web/scripts/attach-domain.sh` manually with
`CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` set.

## Deploy manually (alternative)

```sh
cd web
npm install
npm run build
npx wrangler pages deploy dist --project-name=carvefoundry-web --branch=main
```

## Domain migration later

A new future domain can be added through the same Custom domains screen.
Neither the React app nor browser CAM engine is tied to `cnc.skotic.com`;
all production asset paths are relative to the hostname.

## Security note

This is **an early development preview**, not a production CNC tool.
Keep G-code export disabled until verified independent browser CAM, actual
posted-NC decoding, fixture preflight, and machine limits are complete.
Never store secrets in the frontend: its JavaScript and WASM are public.

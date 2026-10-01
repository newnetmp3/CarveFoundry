# Deployment at cnc.skotic.com

The preview uses **Cloudflare Pages Free**, with all CAM processing
performed in browser WebAssembly. No Python backend or Containers needed.

**Important:** Adding these files does not create a Cloudflare Pages project,
DNS record, certificate or live website. Those require access to your
Cloudflare account. No domain has been claimed to be active.

## One-time setup

1. Sign in to the Cloudflare account holding the `skotic.com` DNS zone.
2. Workers & Pages → Create → Pages, or install Wrangler and run:
   ```sh
   npx wrangler pages project create carvefoundry-web --production-branch=main
   ```
   Use **Direct Upload** / Wrangler deploys, not a second Git-integrated
   project on the same name.
3. In the **GitHub repository settings**, add these Actions secrets:
   - `CLOUDFLARE_API_TOKEN`: scoped token with Cloudflare Pages Edit/Write
     permission for the intended account; do **not** paste it into the repo.
   - `CLOUDFLARE_ACCOUNT_ID`: account ID shown in Cloudflare.
4. A subsequent push to main affecting `web/**`, or a manual run of the
   **Deploy CarveFoundry Web** workflow, builds and uploads `web/dist` to
   `carvefoundry-web.pages.dev`. Monitor the Actions run for confirmation.
5. After a successful Pages deployment, navigate to Workers & Pages →
   `carvefoundry-web` → **Custom domains** → **Set up a domain**, then enter
   **cnc.skotic.com**. If `skotic.com` is in the same Cloudflare account,
   Cloudflare can create the corresponding DNS entry for you.

   Alternatively, with Pages Write permission, run
   `web/scripts/attach-domain.sh` after setting `CLOUDFLARE_ACCOUNT_ID`
   and `CLOUDFLARE_API_TOKEN` in your shell. It uses the official Cloudflare
   Pages custom-domain API. Cloudflare must then validate the domain and TLS.

6. Verify the production URL loads, WASM successfully calculates a pocket
   preview, no G-code export exists, and Cloudflare shows domain status Active.

If the zone is managed by a different DNS provider, point the **cnc** CNAME
record to `carvefoundry-web.pages.dev` only **after** associating
`cnc.skotic.com` with the Pages project. A CNAME alone is insufficient.

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

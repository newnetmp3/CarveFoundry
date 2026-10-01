/**
 * Idempotent Cloudflare Pages provisioning for the isolated web preview.
 * Runs inside GitHub Actions only after the account ID and a scoped Pages token
 * have been configured as repository secrets. Never runs in the browser.
 */
const account = process.env.CLOUDFLARE_ACCOUNT_ID;
const token = process.env.CLOUDFLARE_API_TOKEN;
const project = 'carvefoundry-web';
const domain = 'cnc.skotic.com';
const operation = process.argv[2];
if (!account || !token) {
  throw Error('CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are required');
}
if (!['project', 'domain'].includes(operation)) {
  throw Error('Usage: node scripts/provision-cloudflare.mjs project|domain');
}
const root = `https://api.cloudflare.com/client/v4/accounts/${encodeURIComponent(account)}/pages/projects`;

async function request(method, url, payload, allowMissing = false) {
  const response = await fetch(url, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    ...(payload ? { body: JSON.stringify(payload) } : {}),
  });
  if (allowMissing && response.status === 404) return null;
  const body = await response.json();
  if (!response.ok || !body.success) {
    const details = (body.errors || []).map((item) => item.message).join('; ');
    throw Error(`Cloudflare API ${method} failed (${response.status}): ${details || 'unknown error'}`);
  }
  return body.result;
}

if (operation === 'project') {
  const existing = await request('GET', `${root}/${project}`, null, true);
  if (existing) {
    console.log(`Pages project ${project} already exists; leaving configuration unchanged.`);
  } else {
    await request('POST', root, { name: project, production_branch: 'main' });
    console.log(`Created Cloudflare Pages project ${project}.`);
  }
} else {
  const existing = await request('GET', `${root}/${project}/domains`);
  const matching = existing.find((item) => item.name === domain);
  if (matching) {
    console.log(`Custom domain ${domain} is already attached (status: ${matching.status}).`);
  } else {
    const added = await request('POST', `${root}/${project}/domains`, { name: domain });
    console.log(`Attached custom domain ${domain} (status: ${added.status}).`);
    console.log('Cloudflare may need time to finish DNS and TLS verification.');
  }
}

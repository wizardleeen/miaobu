/**
 * Aliyun ESA Edge Routine for Miaobu Domain Routing
 *
 * Handles routing for all domains (subdomains + custom domains) by:
 * 1. Looking up the hostname in Edge KV
 * 2. For static projects: rewriting path to OSS prefix (cached by ESA)
 * 3. For Python projects: proxying to Function Compute endpoint
 * 4. For unconfigured metavm.tech subdomains: passthrough to origin
 *
 * Uses Aliyun EdgeKV API (new EdgeKV({ namespace }))
 *
 * KV Value Format:
 *   Static:  { "type": "static", "oss_path": "projects/slug/", ... }
 *   Python:  { "type": "python", "fc_endpoint": "https://...", ... }
 *   Legacy:  { "oss_path": "projects/slug/", ... }  (no type = static)
 */

const BASE_DOMAIN = 'metavm.tech';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const hostname = url.hostname.toLowerCase();

    console.log(`[Miaobu] Request: ${hostname}${url.pathname}`);

    try {
      const edgeKV = new EdgeKV({ namespace: "miaobu" });
      const kvValue = await edgeKV.get(hostname, { type: "text" });

      if (kvValue) {
        const mapping = JSON.parse(kvValue);
        console.log(`[Miaobu] Found mapping for ${hostname}:`, mapping);

        const projectType = mapping.type || 'static';

        if (projectType === 'python') {
          if (!mapping.fc_endpoint) {
            console.error(`[Miaobu] Python mapping missing fc_endpoint:`, mapping);
            return new Response('Invalid mapping: missing fc_endpoint', { status: 500 });
          }
          return proxyToFC(request, url, mapping.fc_endpoint);
        } else {
          if (!mapping.oss_path) {
            console.error(`[Miaobu] Static mapping missing oss_path:`, mapping);
            return new Response('Invalid mapping: missing oss_path', { status: 500 });
          }
          return rewriteToOSS(request, url, mapping.oss_path);
        }
      }

      // No KV entry found
      if (hostname.endsWith(`.${BASE_DOMAIN}`) || hostname === BASE_DOMAIN) {
        console.log(`[Miaobu] No KV entry, passthrough: ${hostname}`);
        return fetch(request);
      }

      // Custom domain not configured
      console.log(`[Miaobu] Domain not configured: ${hostname}`);
      return new Response(
        `Domain ${hostname} is not configured in Miaobu`,
        {
          status: 404,
          headers: { 'Content-Type': 'text/plain' }
        }
      );

    } catch (error) {
      console.error('[Miaobu] Error:', error.message);
      return new Response(
        `Routing error: ${error.message}`,
        {
          status: 500,
          headers: { 'Content-Type': 'text/plain' }
        }
      );
    }
  }
};

/**
 * Rewrite request path for static content, then let ESA handle
 * origin fetch + caching. By keeping the same host and only changing
 * the path, the request goes through ESA's normal cache pipeline.
 */
function rewriteToOSS(request, url, ossPath) {
  let path = `/${ossPath}${url.pathname}`;
  if (path.endsWith('/')) {
    path = `${path}index.html`;
  }

  const newUrl = `${url.protocol}//${url.host}${path}${url.search}`;
  console.log(`[Miaobu] Rewrite: ${url.pathname} -> ${path}`);

  return fetch(new Request(newUrl, {
    method: request.method,
    headers: request.headers,
  }));
}

/**
 * Proxy request to Function Compute endpoint for Python projects
 */
async function proxyToFC(request, url, fcEndpoint) {
  const targetUrl = `${fcEndpoint.replace(/\/$/, '')}${url.pathname}${url.search}`;
  console.log(`[Miaobu] Proxying to FC: ${targetUrl}`);

  const proxyHeaders = new Headers(request.headers);
  proxyHeaders.set('X-Forwarded-Host', url.hostname);
  proxyHeaders.set('X-Forwarded-Proto', url.protocol.replace(':', ''));
  proxyHeaders.delete('host');

  const proxyRequest = new Request(targetUrl, {
    method: request.method,
    headers: proxyHeaders,
    body: request.body,
    redirect: 'follow'
  });

  const response = await fetch(proxyRequest);

  const responseHeaders = new Headers(response.headers);
  responseHeaders.delete('Content-Disposition');
  responseHeaders.delete('content-disposition');
  responseHeaders.set('Cache-Control', 'no-store, no-cache, must-revalidate');

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders
  });
}

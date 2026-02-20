/**
 * Aliyun ESA Edge Routine for Miaobu Domain Routing
 *
 * Handles routing for all domains (subdomains + custom domains) by:
 * 1. Looking up the hostname in Edge KV
 * 2. For staging: password protection with cookie-based session
 * 3. For static projects: rewriting path to OSS prefix (cached by ESA)
 * 4. For Python projects: proxying to Function Compute endpoint
 * 5. For unconfigured metavm.tech subdomains: passthrough to origin
 *
 * Uses Aliyun EdgeKV API (new EdgeKV({ namespace }))
 *
 * KV Value Format:
 *   Static:  { "type": "static", "oss_path": "projects/slug/", ... }
 *   Python:  { "type": "python", "fc_endpoint": "https://...", ... }
 *   Node:    { "type": "node",   "fc_endpoint": "https://...", ... }
 *   Legacy:  { "oss_path": "projects/slug/", ... }  (no type = static)
 *   Staging: adds "staging": true, "staging_password_hash": "..." to any type
 */

const BASE_DOMAIN = '__BASE_DOMAIN__';
const STAGING_COOKIE_NAME = '__miaobu_staging';
const STAGING_SESSION_HOURS = 24;
const STAGING_HMAC_KEY = 'miaobu-staging-edge-key-2026';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const hostname = url.hostname.toLowerCase();

    console.log(`[Miaobu] Request: ${hostname}${url.pathname}`);

    try {
      const edgeKV = new EdgeKV({ namespace: "__KV_NAMESPACE__" });
      const kvValue = await edgeKV.get(hostname, { type: "text" });

      if (kvValue) {
        const mapping = JSON.parse(kvValue);
        console.log(`[Miaobu] Found mapping for ${hostname}:`, mapping);

        // --- Staging password protection (static/frontend only) ---
        const projectType = mapping.type || 'static';
        if (mapping.staging && mapping.staging_password_hash && projectType === 'static') {
          // Handle login POST
          if (url.pathname === '/__miaobu_staging_login' && request.method === 'POST') {
            return handleStagingLogin(request, url, mapping.staging_password_hash);
          }

          // Check session cookie
          const cookieValid = await verifyStagingCookie(request);
          if (!cookieValid) {
            return serveStagingLoginPage(url);
          }
        }

        let response;

        if (projectType === 'python' || projectType === 'node') {
          if (!mapping.fc_endpoint) {
            console.error(`[Miaobu] Python mapping missing fc_endpoint:`, mapping);
            return new Response('Invalid mapping: missing fc_endpoint', { status: 500 });
          }
          response = await proxyToFC(request, url, mapping.fc_endpoint);
        } else {
          if (!mapping.oss_path) {
            console.error(`[Miaobu] Static mapping missing oss_path:`, mapping);
            return new Response('Invalid mapping: missing oss_path', { status: 500 });
          }
          response = await rewriteToOSS(request, url, mapping.oss_path, mapping.is_spa === true);
        }

        // Add noindex header for staging
        if (mapping.staging) {
          const headers = new Headers(response.headers);
          headers.set('X-Robots-Tag', 'noindex, nofollow');
          return new Response(response.body, {
            status: response.status,
            statusText: response.statusText,
            headers: headers,
          });
        }

        return response;
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
 *
 * SPA mode: all non-file paths resolve to /index.html (for client-side routing)
 * MPA mode: /blog resolves to /blog/index.html, / resolves to /index.html
 */
function rewriteToOSS(request, url, ossPath, isSPA) {
  let path = url.pathname;

  // Check if path has a file extension (e.g., .js, .css, .html, .png)
  const lastSegment = path.split('/').pop();
  const hasExtension = lastSegment && lastSegment.includes('.');

  if (!hasExtension) {
    if (isSPA) {
      // SPA: all non-file paths serve /index.html
      path = '/index.html';
    } else {
      // MPA: /blog -> /blog/index.html, / -> /index.html
      if (!path.endsWith('/')) {
        path = path + '/';
      }
      path = path + 'index.html';
    }
  }

  const fullPath = `/${ossPath}${path}`;
  const newUrl = `${url.protocol}//${url.host}${fullPath}${url.search}`;
  console.log(`[Miaobu] Rewrite (${isSPA ? 'SPA' : 'MPA'}): ${url.pathname} -> ${fullPath}`);

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
    redirect: 'manual'
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

// ---------------------------------------------------------------------------
// Staging password protection
// ---------------------------------------------------------------------------

/**
 * Compute SHA-256 hex digest using Web Crypto API
 */
async function sha256hex(message) {
  const encoder = new TextEncoder();
  const data = encoder.encode(message);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Compute HMAC-SHA256 hex digest using Web Crypto API
 */
async function hmacSha256hex(key, message) {
  const encoder = new TextEncoder();
  const keyData = encoder.encode(key);
  const cryptoKey = await crypto.subtle.importKey(
    'raw', keyData, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', cryptoKey, encoder.encode(message));
  const sigArray = Array.from(new Uint8Array(sig));
  return sigArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Parse cookies from request
 */
function parseCookies(request) {
  const cookieHeader = request.headers.get('Cookie') || '';
  const cookies = {};
  cookieHeader.split(';').forEach(pair => {
    const [name, ...rest] = pair.trim().split('=');
    if (name) cookies[name] = rest.join('=');
  });
  return cookies;
}

/**
 * Verify staging session cookie
 * Cookie format: {timestamp}.{hmac_signature}
 */
async function verifyStagingCookie(request) {
  const cookies = parseCookies(request);
  const cookie = cookies[STAGING_COOKIE_NAME];
  if (!cookie) return false;

  const dotIndex = cookie.indexOf('.');
  if (dotIndex === -1) return false;

  const timestamp = cookie.substring(0, dotIndex);
  const signature = cookie.substring(dotIndex + 1);

  // Check expiry
  const ts = parseInt(timestamp, 10);
  if (isNaN(ts)) return false;
  const now = Math.floor(Date.now() / 1000);
  if (now - ts > STAGING_SESSION_HOURS * 3600) return false;

  // Verify HMAC
  const expected = await hmacSha256hex(STAGING_HMAC_KEY, timestamp);
  return expected === signature;
}

/**
 * Handle staging login POST
 */
async function handleStagingLogin(request, url, passwordHash) {
  try {
    const formData = await request.formData();
    const password = formData.get('password') || '';

    const inputHash = await sha256hex(password);

    if (inputHash !== passwordHash) {
      return serveStagingLoginPage(url, true);
    }

    // Set session cookie
    const timestamp = Math.floor(Date.now() / 1000).toString();
    const signature = await hmacSha256hex(STAGING_HMAC_KEY, timestamp);
    const cookieValue = `${timestamp}.${signature}`;

    return new Response(null, {
      status: 302,
      headers: {
        'Location': '/',
        'Set-Cookie': `${STAGING_COOKIE_NAME}=${cookieValue}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${STAGING_SESSION_HOURS * 3600}`,
        'X-Robots-Tag': 'noindex, nofollow',
      },
    });
  } catch (e) {
    console.error('[Miaobu] Staging login error:', e.message);
    return serveStagingLoginPage(url, true);
  }
}

/**
 * Serve the staging login page HTML
 */
function serveStagingLoginPage(url, error = false) {
  const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Staging - 需要密码</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0a0a0a; color: #e5e5e5;
    display: flex; align-items: center; justify-content: center;
    min-height: 100vh; padding: 1rem;
  }
  .card {
    background: #171717; border: 1px solid #262626; border-radius: 12px;
    padding: 2rem; width: 100%; max-width: 380px;
  }
  .badge {
    display: inline-block; background: #7c3aed; color: #fff;
    font-size: 11px; font-weight: 600; padding: 2px 8px;
    border-radius: 4px; text-transform: uppercase; letter-spacing: 0.5px;
    margin-bottom: 1rem;
  }
  h1 { font-size: 1.25rem; margin-bottom: 0.5rem; }
  p { font-size: 0.875rem; color: #a3a3a3; margin-bottom: 1.5rem; }
  label { display: block; font-size: 0.8rem; color: #a3a3a3; margin-bottom: 0.5rem; }
  input[type="password"] {
    width: 100%; padding: 0.6rem 0.75rem; background: #0a0a0a;
    border: 1px solid #333; border-radius: 8px; color: #e5e5e5;
    font-size: 0.9rem; outline: none; transition: border-color 0.2s;
  }
  input[type="password"]:focus { border-color: #7c3aed; }
  button {
    width: 100%; margin-top: 1rem; padding: 0.6rem;
    background: #7c3aed; border: none; border-radius: 8px;
    color: #fff; font-size: 0.9rem; font-weight: 500; cursor: pointer;
    transition: background 0.2s;
  }
  button:hover { background: #6d28d9; }
  .error { color: #ef4444; font-size: 0.8rem; margin-top: 0.75rem; }
  .host { font-size: 0.75rem; color: #525252; text-align: center; margin-top: 1.25rem; }
</style>
</head>
<body>
<div class="card">
  <span class="badge">Staging</span>
  <h1>需要密码访问</h1>
  <p>此站点为预览环境，需要输入密码才能查看。</p>
  <form method="POST" action="/__miaobu_staging_login">
    <label for="password">访问密码</label>
    <input type="password" id="password" name="password" placeholder="输入密码" required autofocus>
    <button type="submit">访问</button>
    ${error ? '<p class="error">密码错误，请重试。</p>' : ''}
  </form>
  <p class="host">${url.hostname}</p>
</div>
</body>
</html>`;

  return new Response(html, {
    status: 401,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'X-Robots-Tag': 'noindex, nofollow',
      'Cache-Control': 'no-store',
    },
  });
}

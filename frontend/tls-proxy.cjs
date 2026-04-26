#!/usr/bin/env node
/**
 * tls-proxy.cjs — tiny HTTPS-fronted reverse proxy for the Vite dev
 * server.
 *
 * Why: certain hostnames (e.g. anything under bullerocapital.com)
 * have HSTS preloaded on the parent domain, so browsers force HTTPS
 * for every subdomain — `http://ssh.bullerocapital.com:7778` gets
 * silently rewritten to `https://...` and Vite (which only speaks
 * HTTP on that port) returns a TLS handshake failure.
 *
 * This script listens on 7779 with a self-signed cert (regenerated
 * at every start; in-memory, never persisted) and reverse-proxies
 * to localhost:7778 over HTTP, including a WebSocket upgrade pipe so
 * Vite HMR keeps working over wss://.
 *
 * Browser will show one cert warning the first time you connect; after
 * "proceed" it sticks for the session. For a no-warning setup, use
 * mkcert (Option 2) or Caddy (Option 3) — see the README.
 *
 * Run via `npm run dev` (alongside Vite via concurrently) or by hand
 * with `node tls-proxy.cjs`. Env knobs:
 *   TLS_PORT       (default 7779)
 *   VITE_HTTP_PORT (default 7778)
 *   TLS_HOSTNAME   (default '*' — used for the cert CN)
 */

const https = require("node:https");
const http = require("node:http");
const net = require("node:net");
const selfsigned = require("selfsigned");

const TLS_PORT = parseInt(process.env.TLS_PORT || "7779", 10);
const VITE_HTTP_PORT = parseInt(process.env.VITE_HTTP_PORT || "7778", 10);
const HOSTNAME = process.env.TLS_HOSTNAME || "ssh.bullerocapital.com";

// Generate a self-signed cert valid for 90 days. We include several
// SAN entries so the same cert covers localhost + the public hostname.
const attrs = [{ name: "commonName", value: HOSTNAME }];
const pems = selfsigned.generate(attrs, {
  days: 90,
  algorithm: "sha256",
  keySize: 2048,
  extensions: [
    {
      name: "subjectAltName",
      altNames: [
        { type: 2, value: HOSTNAME },        // DNS
        { type: 2, value: "localhost" },
        { type: 7, ip: "127.0.0.1" },
      ],
    },
  ],
});

const server = https.createServer(
  { key: pems.private, cert: pems.cert },
  (req, res) => {
    const upstream = http.request(
      {
        host: "127.0.0.1",
        port: VITE_HTTP_PORT,
        method: req.method,
        path: req.url,
        headers: req.headers,
      },
      (upRes) => {
        res.writeHead(upRes.statusCode || 502, upRes.headers);
        upRes.pipe(res);
      },
    );
    upstream.on("error", (err) => {
      console.error("upstream error:", err.message);
      if (!res.headersSent) res.writeHead(502, { "content-type": "text/plain" });
      res.end(`bad gateway: ${err.message}`);
    });
    req.pipe(upstream);
  },
);

// WebSocket upgrade path — Vite HMR.
server.on("upgrade", (req, socket, head) => {
  const upstream = net.connect(VITE_HTTP_PORT, "127.0.0.1", () => {
    upstream.write(
      `${req.method} ${req.url} HTTP/1.1\r\n` +
        Object.entries(req.headers)
          .map(([k, v]) => `${k}: ${v}`)
          .join("\r\n") +
        "\r\n\r\n",
    );
    if (head && head.length) upstream.write(head);
    upstream.pipe(socket);
    socket.pipe(upstream);
  });
  upstream.on("error", (err) => {
    console.error("ws upstream error:", err.message);
    socket.destroy();
  });
  socket.on("error", () => upstream.destroy());
});

server.listen(TLS_PORT, "0.0.0.0", () => {
  console.log(
    `tls-proxy listening on https://0.0.0.0:${TLS_PORT} → http://127.0.0.1:${VITE_HTTP_PORT}`,
  );
  console.log(`(self-signed cert; CN=${HOSTNAME}; valid 90 days)`);
});

server.on("error", (err) => {
  console.error("tls-proxy error:", err);
  process.exit(1);
});

import { mkdir, writeFile } from "node:fs/promises";

const output = new URL("../public/_headers", import.meta.url);
const apiOrigin = process.env.NEXT_PUBLIC_API_BASE_URL ? new URL(process.env.NEXT_PUBLIC_API_BASE_URL).origin : "'self'";
await mkdir(new URL("../public/", import.meta.url), { recursive: true });
await writeFile(
  output,
  `/*\n  X-Content-Type-Options: nosniff\n  X-Frame-Options: DENY\n  Referrer-Policy: no-referrer\n  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()\n  Content-Security-Policy: default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'; form-action 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self' ${apiOrigin}\n  Strict-Transport-Security: max-age=31536000; includeSubDomains\n`,
  "utf8",
);

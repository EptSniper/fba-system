/** @type {import('next').NextConfig} */
const nextConfig = {
  // The dashboard reads files from the sibling learning-hub/ and scout/ folders at
  // request time (server-side only). Nothing is bundled from there.
  reactStrictMode: true,
  // This project sits inside a larger workspace that has unrelated lockfiles.
  // Keep server tracing scoped to this app so builds are deterministic.
  outputFileTracingRoot: process.cwd(),
};

export default nextConfig;

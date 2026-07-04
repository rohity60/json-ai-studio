/** @type {import('next').NextConfig} */
const apiBase = process.env.API_BASE_URL || 'http://lohaii:8000';
const nextConfig = {
  async rewrites() {
    return [
        { source: '/api/:path*', destination: `${apiBase}/api/:path*` },
      ];
    },
};

export default nextConfig;

/** @type {import('next').NextConfig} */
const imageBackendHost = process.env.NEXUS_IMAGE_BACKEND_HOST || 'localhost';
const imageBackendPort = process.env.NEXUS_DEV_BACKEND_PORT || '8000';

const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,

  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'Cache-Control',
            value: 'no-store, no-cache, must-revalidate, max-age=0',
          },
          {
            key: 'Pragma',
            value: 'no-cache',
          },
          {
            key: 'Expires',
            value: '0',
          },
        ],
      },
    ];
  },
  
  // Разрешить загрузку с backend
  images: {
    remotePatterns: [
      {
        protocol: 'http',
        hostname: imageBackendHost,
        port: imageBackendPort,
      },
    ],
  },
}

module.exports = nextConfig

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Docker 部署需要独立产物；本地 dev 不受影响
  output: "standalone",
};

export default nextConfig;

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 静态导出：把前端打成纯 HTML/JS/CSS，交给 FastAPI 挂载，实现前后端单端口合并。
  // 前提：本项目无 app/api 服务端路由、无 cookies/headers/searchParams 等动态依赖，
  // 四个页面（/ /chat /knowledge /settings）都可静态化。
  output: "export",
  // 静态导出会把页面写成 /chat/index.html 之类，需要去掉尾随斜杠方便 SPA 回退匹配。
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;

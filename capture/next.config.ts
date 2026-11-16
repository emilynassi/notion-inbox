import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    // The hosted Bear Board is a static page in public/board/.
    return [
      { source: "/board", destination: "/board/index.html" },
      { source: "/board/", destination: "/board/index.html" },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-Content-Type-Options", value: "nosniff" },
        ],
      },
    ];
  },
};

export default nextConfig;

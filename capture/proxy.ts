import { NextRequest, NextResponse } from "next/server";

// Timing-safe string comparison for Edge runtime (no Node crypto here)
function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

export default function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (pathname.startsWith("/login") || pathname.startsWith("/_next")) {
    return NextResponse.next();
  }

  const secret = process.env.COOKIE_SECRET;
  if (!secret) throw new Error("COOKIE_SECRET env var is not set");

  const cookie = request.cookies.get("auth")?.value ?? "";
  if (!safeEqual(cookie, secret)) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};

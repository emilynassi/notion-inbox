"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { timingSafeEqual } from "crypto";

export async function login(prevState: string, formData: FormData) {
  const password = formData.get("password") as string;
  const correct = process.env.CAPTURE_PASSWORD;
  const secret = process.env.COOKIE_SECRET;

  if (!correct || !secret) throw new Error("Missing required env vars");

  const bufA = Buffer.from(password);
  const bufB = Buffer.from(correct);
  const matched =
    bufA.length === bufB.length && timingSafeEqual(bufA, bufB);

  if (!matched) {
    await new Promise((r) => setTimeout(r, 500));
    return "Wrong password.";
  }

  (await cookies()).set("auth", secret, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: 60 * 60 * 24 * 30, // 30 days
    path: "/",
  });

  redirect("/");
}

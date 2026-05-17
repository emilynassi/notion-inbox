"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export async function login(prevState: string, formData: FormData) {
  const password = formData.get("password") as string;
  const correct = process.env.CAPTURE_PASSWORD;

  if (!correct) throw new Error("CAPTURE_PASSWORD env var is not set");

  if (password !== correct) {
    return "Wrong password.";
  }

  (await cookies()).set("auth", "1", {
    httpOnly: true,
    sameSite: "lax",
    maxAge: 60 * 60 * 24 * 30, // 30 days
    path: "/",
  });

  redirect("/");
}

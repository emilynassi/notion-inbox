"use client";

import { useActionState } from "react";
import { login } from "@/app/actions/auth";

export default function LoginPage() {
  const [error, action, pending] = useActionState(login, "");

  return (
    <main className="min-h-screen flex items-center justify-center bg-stone-50">
      <form
        action={action}
        className="flex flex-col gap-4 w-full max-w-xs"
      >
        <h1 className="text-xl font-semibold text-stone-800">Inbox</h1>
        <input
          type="password"
          name="password"
          placeholder="Password"
          required
          autoFocus
          className="border border-stone-300 rounded-lg px-4 py-2 text-stone-800 focus:outline-none focus:ring-2 focus:ring-stone-400"
        />
        {error && <p className="text-red-500 text-sm">{error}</p>}
        <button
          type="submit"
          disabled={pending}
          className="bg-stone-800 text-white rounded-lg px-4 py-2 font-medium hover:bg-stone-700 disabled:opacity-50"
        >
          {pending ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}

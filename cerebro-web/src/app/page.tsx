import { redirect } from "next/navigation";

// This app is the team dashboard only — the client-facing marketing site
// now lives in the separate cerebro-client app. Nothing renders at the
// bare domain, so send visitors straight to the dashboard overview.
export default function RootPage() {
  redirect("/dashboard");
}

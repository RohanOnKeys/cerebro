import { NextResponse } from "next/server";
import { postAdmin } from "@/lib/api";

export async function POST() {
  const result = await postAdmin<{ channelsActive: boolean }>(
    "/admin/organization/revoke-access",
  );

  if (result.kind === "error") {
    return NextResponse.json({ error: "revoke failed" }, { status: result.status });
  }
  if (result.kind === "mock") {
    return NextResponse.json({ channelsActive: false, mocked: true });
  }
  return NextResponse.json(result.data);
}

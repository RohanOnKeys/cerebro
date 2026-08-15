import { NextResponse } from "next/server";
import { postAdmin } from "@/lib/api";

export async function POST() {
  const result = await postAdmin<{ workspaceActive: boolean }>(
    "/admin/organization/deactivate",
  );

  if (result.kind === "error") {
    return NextResponse.json({ error: "deactivate failed" }, { status: result.status });
  }
  if (result.kind === "mock") {
    return NextResponse.json({ workspaceActive: false, mocked: true });
  }
  return NextResponse.json(result.data);
}

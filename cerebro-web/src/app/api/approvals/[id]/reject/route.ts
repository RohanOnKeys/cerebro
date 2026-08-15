import { NextResponse } from "next/server";
import { postAdmin } from "@/lib/api";

export async function POST(_req: Request, { params }: { params: { id: string } }) {
  const result = await postAdmin<{ status: string; claim_id: string; claimant_principal_id: string }>(
    `/admin/approvals/${params.id}/reject`,
  );

  if (result.kind === "error") {
    return NextResponse.json({ error: "reject failed" }, { status: result.status });
  }
  if (result.kind === "mock") {
    return NextResponse.json({ status: "denied", claimId: params.id, mocked: true });
  }
  return NextResponse.json(result.data);
}

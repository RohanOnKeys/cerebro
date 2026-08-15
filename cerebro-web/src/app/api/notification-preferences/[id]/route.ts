import { NextResponse } from "next/server";
import { postAdmin } from "@/lib/api";

export async function POST(req: Request, { params }: { params: { id: string } }) {
  const { enabled } = (await req.json()) as { enabled: boolean };

  const result = await postAdmin<{ id: string; label: string; enabled: boolean }>(
    `/admin/notification-preferences/${params.id}/set`,
    { enabled },
  );

  if (result.kind === "error") {
    return NextResponse.json({ error: "update failed" }, { status: result.status });
  }
  if (result.kind === "mock") {
    return NextResponse.json({ id: params.id, enabled, mocked: true });
  }
  return NextResponse.json(result.data);
}

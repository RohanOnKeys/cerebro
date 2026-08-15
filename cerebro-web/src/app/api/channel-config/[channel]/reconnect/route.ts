import { NextResponse } from "next/server";
import { postAdmin } from "@/lib/api";
import type { ApiKeyStatus, ChannelName } from "@/lib/types";

export async function POST(
  _req: Request,
  { params }: { params: { channel: ChannelName } },
) {
  const result = await postAdmin<{ channel: ChannelName; apiKeyStatus: ApiKeyStatus }>(
    `/admin/channel-config/${params.channel}/reconnect`,
  );

  if (result.kind === "error") {
    return NextResponse.json({ error: "reconnect failed" }, { status: result.status });
  }
  if (result.kind === "mock") {
    return NextResponse.json({
      channel: params.channel,
      apiKeyStatus: "configured" satisfies ApiKeyStatus,
      mocked: true,
    });
  }
  return NextResponse.json(result.data);
}

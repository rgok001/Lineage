import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

// The river is now the map's front door at /g/[id]; keep this path working.
export default async function RiverRedirect({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/g/${id}`);
}

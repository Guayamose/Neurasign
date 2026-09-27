import { notFound, redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default function DemoPage() {
  if (process.env.NEURASIGN_ENV === "production" || process.env.K_SERVICE) notFound();
  redirect("/?demo=1#overview");
}

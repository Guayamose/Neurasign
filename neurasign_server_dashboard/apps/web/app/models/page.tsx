import { notFound } from "next/navigation";
import ModelEngine from "@/components/model-engine";

export const dynamic = "force-dynamic";

export default function ModelsPage() {
  if (process.env.NEURASIGN_ENV === "production" || process.env.K_SERVICE) notFound();
  return <ModelEngine />;
}

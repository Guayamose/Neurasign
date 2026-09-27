import { notFound } from "next/navigation";
import MonitoringDashboard from "@/components/monitoring-dashboard";

export const dynamic = "force-dynamic";

/** Source-labeled physiological exploration remains separate from the company demo. */
export default function SignalsPage() {
  if (process.env.NEURASIGN_ENV === "production" || process.env.K_SERVICE) notFound();
  return <MonitoringDashboard />;
}

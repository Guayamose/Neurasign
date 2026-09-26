import { notFound } from "next/navigation";
import MonitoringDashboard from "@/components/monitoring-dashboard";

export const dynamic = "force-dynamic";

export default function DemoPage() {
  if (process.env.NEURASIGN_ENV === "production" || process.env.K_SERVICE) notFound();
  return <MonitoringDashboard />;
}

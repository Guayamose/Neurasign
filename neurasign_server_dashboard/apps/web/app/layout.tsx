import type { Metadata } from "next";
import "./globals.css";
import "./monitoring.css";

export const metadata: Metadata = {
  title: "NEURASIGN — Team monitoring",
  description: "Your team's wearable measurements, signal freshness and physiological trends in one workspace.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}

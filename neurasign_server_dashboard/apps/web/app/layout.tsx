import type { Metadata } from "next";
import "./globals.css";
import "./monitoring.css";

export const metadata: Metadata = {
  title: "NEURASIGN — Team monitoring",
  description: "Understand your team, coordinate work and keep handovers connected in one private company workspace.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}

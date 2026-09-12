import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SemiBand · Paper research",
  description: "Follow the SemiBand paper portfolio, agent convictions, and walk-forward research.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body><a className="skip-link" href="#main-content">Skip to content</a>{children}</body>
    </html>
  );
}

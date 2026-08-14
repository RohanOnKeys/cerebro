import type { Metadata } from "next";
import { Archivo, Work_Sans } from "next/font/google";
import "./globals.css";

const archivo = Archivo({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-archivo",
  display: "swap",
});

const workSans = Work_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-work-sans",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  title: {
    default: "Cerebro — Agency Orchestration",
    template: "%s — Cerebro",
  },
  description:
    "Cerebro is the company second brain: one agent across WhatsApp, Telegram, Discord, Slack, and Email, with verified identity, scheduling, notification routing, and CI as a conversation.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${archivo.variable} ${workSans.variable}`}>
      <body className="font-sans">{children}</body>
    </html>
  );
}

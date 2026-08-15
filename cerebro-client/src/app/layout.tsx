import type { Metadata } from "next";
import { Unica_One, Work_Sans } from "next/font/google";
import "./globals.css";

const unicaOne = Unica_One({
  subsets: ["latin"],
  weight: ["400"],
  variable: "--font-unica",
  display: "swap",
});

const workSans = Work_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-work-sans",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3001"),
  title: {
    default: "Cerebro — Agency Orchestration",
    template: "%s — Cerebro",
  },
  description:
    "Cerebro is your direct line to the team: reach us on Telegram or email, get meetings scheduled, requests assigned, and questions answered, with every sender verified.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${unicaOne.variable} ${workSans.variable}`}>
      <body className="font-sans">{children}</body>
    </html>
  );
}

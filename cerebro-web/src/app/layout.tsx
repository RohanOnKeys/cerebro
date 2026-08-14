import type { Metadata } from "next";
import { Archivo, Unica_One, Work_Sans } from "next/font/google";
import "./globals.css";

const archivo = Archivo({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-archivo",
  display: "swap",
});

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
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
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
    <html lang="en" className={`${archivo.variable} ${unicaOne.variable} ${workSans.variable}`}>
      <body className="font-sans">{children}</body>
    </html>
  );
}

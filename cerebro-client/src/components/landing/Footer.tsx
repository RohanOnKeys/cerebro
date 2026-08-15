import Image from "next/image";
import { EmailIcon, TelegramIcon } from "@/components/landing/icons";

const CHANNEL_LINKS = [
  { label: "Telegram", href: "https://t.me/cerebro_operations_bot", icon: TelegramIcon },
  { label: "Email", href: "mailto:cerebro-1d74f5@agents.trycaspianai.com", icon: EmailIcon },
];

export function Footer() {
  return (
    <footer
      id="contact"
      className="border-t border-cerebro-border px-6 py-10 sm:px-16"
    >
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4">
        <span className="text-sm text-cerebro-muted">More to life, less to arrangements.</span>

        <div className="flex items-center gap-x-6">
          <nav className="flex items-center gap-x-5" aria-label="Reach Cerebro">
            {CHANNEL_LINKS.map((link) => (
              <a
                key={link.label}
                href={link.href}
                title={link.label}
                aria-label={link.label}
                target={link.href.startsWith("mailto:") ? undefined : "_blank"}
                rel={link.href.startsWith("mailto:") ? undefined : "noopener noreferrer"}
                className="flex items-center justify-center text-cerebro-accent-lightest transition-colors hover:text-cerebro-ink"
              >
                <link.icon className="h-5 w-5" />
              </a>
            ))}
          </nav>

          <a
            href="https://github.com/TryCaspian/caspian-sdk"
            title="powered by caspian-ai"
            aria-label="powered by caspian-ai"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center opacity-80 transition-opacity hover:opacity-100"
          >
            <Image src="/orb.png" alt="caspian-ai" width={18} height={18} className="object-contain" />
          </a>
        </div>
      </div>
    </footer>
  );
}

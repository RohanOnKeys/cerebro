import Image from "next/image";
import { EmailIcon, TelegramIcon } from "@/components/landing/icons";

export function ChannelRow() {
  return (
    <section className="border-b border-cerebro-border py-16">
      <div
        className="mx-auto flex max-w-3xl items-center justify-center gap-4 px-6 sm:gap-8"
        aria-label="Cerebro is reachable on Telegram and Email"
      >
        <ChannelNode
          label="Telegram"
          icon={TelegramIcon}
          href="https://t.me/cerebro_operations_bot"
        />
        <Connector />
        <CerebroMark />
        <Connector />
        <ChannelNode
          label="Email"
          icon={EmailIcon}
          href="mailto:cerebro-1d74f5@agents.trycaspianai.com"
        />
      </div>
    </section>
  );
}

function ChannelNode({
  label,
  icon: Icon,
  href,
}: {
  label: string;
  icon: (props: { className?: string }) => JSX.Element;
  href: string;
}) {
  return (
    <a
      href={href}
      title={label}
      aria-label={label}
      target={href.startsWith("mailto:") ? undefined : "_blank"}
      rel={href.startsWith("mailto:") ? undefined : "noopener noreferrer"}
      className="flex items-center justify-center"
    >
      <Icon className="h-8 w-8 text-cerebro-accent-lighter transition-colors hover:text-cerebro-accent-lightest" />
    </a>
  );
}

function Connector() {
  return <div className="h-px w-12 bg-cerebro-accent-light sm:w-20" aria-hidden="true" />;
}

function CerebroMark() {
  return (
    <Image
      src="/cerebro-brain.png"
      alt="Cerebro"
      title="Cerebro"
      width={36}
      height={36}
      className="h-9 w-9 object-contain"
    />
  );
}

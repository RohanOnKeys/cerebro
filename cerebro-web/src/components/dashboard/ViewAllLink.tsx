import Link from "next/link";

export function ViewAllLink({ href }: { href: string }) {
  return (
    <Link
      href={href}
      className="text-sm text-cerebro-accent-lightest transition-colors hover:text-cerebro-ink"
    >
      View all →
    </Link>
  );
}

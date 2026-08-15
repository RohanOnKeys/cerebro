import { ChannelRow } from "@/components/landing/ChannelRow";
import { CoreCapabilities } from "@/components/landing/CoreCapabilities";
import { Footer } from "@/components/landing/Footer";
import { Hero } from "@/components/landing/Hero";
import { SecondaryCapabilities } from "@/components/landing/SecondaryCapabilities";

export default function LandingPage() {
  return (
    <main>
      <Hero />
      <ChannelRow />
      <CoreCapabilities />
      <SecondaryCapabilities />
      <Footer />
    </main>
  );
}

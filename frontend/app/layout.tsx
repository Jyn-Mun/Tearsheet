import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Mona_Sans, Geist, JetBrains_Mono } from "next/font/google";
import { Providers } from "./providers";
import "./globals.css";

// Display: industrial grotesque. Body: clean (not Inter). Numerics: tabular monospace.
const display = Mona_Sans({ subsets: ["latin"], variable: "--font-display", weight: ["500", "700", "800"] });
const body = Geist({ subsets: ["latin"], variable: "--font-body", weight: ["400", "500"] });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", weight: ["400", "500", "700"] });

export const metadata: Metadata = {
  title: "Tearsheet — equity research terminal",
  description: "An AI equity-research terminal. Research tool, not financial advice.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable} ${mono.variable}`}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

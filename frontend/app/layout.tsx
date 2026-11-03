import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Proofline | Evidence-backed AI Code Review",
  description:
    "Review the change. Verify the repair. Context-aware Python, JavaScript and TypeScript code review with Google Gemini.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}

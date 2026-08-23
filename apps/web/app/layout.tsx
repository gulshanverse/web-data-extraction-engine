/** Data Loom root: warm editorial type and semantic CSS variables provide the shared product system. */
import type { Metadata } from "next";
import { AuthGate } from "@/components/auth-gate";
import "./globals.css";
export const metadata: Metadata = { title: "data/loom — Web Data Extraction Engine", description: "A premium workspace for bounded web-to-data operations." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body><AuthGate>{children}</AuthGate></body></html>; }

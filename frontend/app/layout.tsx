import type { Metadata } from "next";
import Nav from "@/components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "Nepal Air Quality",
  description: "Real-time air pollution warnings for Kathmandu, Pokhara and Biratnagar",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Nav />
        <main className="page">{children}</main>
        <footer className="footer muted small">
          Data: Open-Meteo / CAMS air-quality model · Spark MLlib · Kafka · Cassandra · HDFS
        </footer>
      </body>
    </html>
  );
}

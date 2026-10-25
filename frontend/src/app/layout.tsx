import type { Metadata } from 'next';
import { IBM_Plex_Mono, Instrument_Sans, Instrument_Serif } from 'next/font/google';
import './globals.css';

const display = Instrument_Serif({
  subsets: ['latin'],
  weight: '400',
  style: ['normal', 'italic'],
  variable: '--font-display',
  display: 'swap',
});

const body = Instrument_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-body',
  display: 'swap',
});

const code = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
  variable: '--font-code',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'Legal Snaps — Editorial Infographic Engine',
  description:
    'Retrieves a judgment, analyses it with Qwen, verifies every claim against the source, and typesets a single editorial infographic.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      data-lamp="off"
      className={`${display.variable} ${body.variable} ${code.variable} h-full`}
    >
      <body className="relative min-h-full flex flex-col bg-ink text-paper">
        {children}
      </body>
    </html>
  );
}

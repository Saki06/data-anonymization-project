import type { Metadata } from 'next';
import './globals.css';
import { SessionProvider } from '@/lib/SessionContext';
import ThemeProvider from '@/components/ThemeProvider';
import AuthLayoutShell from '@/components/AuthLayoutShell';

export const metadata: Metadata = {
  title: 'Anonymization Automation System',
  description: 'AI-Powered Statistical Disclosure Control & Data Anonymization',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="bg-slate-100 dark:bg-slate-950 text-slate-800 dark:text-slate-200 font-sans antialiased overflow-hidden">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
          <SessionProvider>
            <AuthLayoutShell>{children}</AuthLayoutShell>
          </SessionProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}

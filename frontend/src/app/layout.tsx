import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Government Schemes Discovery & Matching Platform",
  description: "Document-driven MSME & Startup policy eligibility matcher and gap analysis synthesizer.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased">
        <div className="tricolor-stripe" />
        <header className="bg-white border-b border-slate-200 sticky top-0 z-50 shadow-sm">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex justify-between items-center h-16">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 rounded-lg bg-[#0A2540] text-white flex items-center justify-center font-bold text-lg shadow-md">
                🏛️
              </div>
              <div>
                <h1 className="text-base font-bold text-slate-900 leading-tight">
                  Government Schemes Discovery & RAG Platform
                </h1>
                <p className="text-xs text-slate-500">Document-Driven Business Profiling & Eligibility Reasoner</p>
              </div>
            </div>
            <div className="flex items-center space-x-3 text-xs">
              <span className="inline-flex items-center px-2.5 py-1 rounded-full font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                <span className="w-2 h-2 mr-1.5 bg-emerald-500 rounded-full animate-pulse" />
                41 Active Schemes
              </span>
              <a
                href="http://localhost:8000/docs"
                target="_blank"
                rel="noreferrer"
                className="px-2.5 py-1 rounded border border-slate-200 text-slate-600 hover:text-slate-900 font-medium"
              >
                API Docs
              </a>
            </div>
          </div>
        </header>
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">{children}</main>
      </body>
    </html>
  );
}

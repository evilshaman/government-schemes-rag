"use client";

import React, { useState, useEffect } from "react";
import { BusinessProfile, FullReasoningReport, SchemeEligibilityAssessment } from "@/lib/types";
import { fetchSampleProfile, uploadDocument, deliberateSchemes, sendChatMessage } from "@/lib/api";

export default function DashboardPage() {
  const [profile, setProfile] = useState<BusinessProfile | null>(null);
  const [report, setReport] = useState<FullReasoningReport | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string>("");

  // Chat state
  const [chatInput, setChatInput] = useState<string>("");
  const [chatMessages, setChatMessages] = useState<Array<{ role: string; content: string; cited?: any[] }>>([
    {
      role: "assistant",
      content: "Namaste! I am your Government Policy Copilot. Ask any question regarding collateral-free loans, margin money subsidies, or documentation checklists under central and state policies.",
    },
  ]);
  const [chatLoading, setChatLoading] = useState<boolean>(false);

  // Load default sample 1 on mount
  useEffect(() => {
    handleLoadSample(1);
  }, []);

  const handleLoadSample = async (id: number) => {
    setLoading(true);
    setStatusMessage(`Loading Sample #${id}...`);
    try {
      const p = await fetchSampleProfile(id);
      setProfile(p);
      setStatusMessage(`Sample #${id} loaded successfully.`);
      // Auto deliberate
      const rep = await deliberateSchemes(p, undefined, 4);
      setReport(rep);
    } catch (err: any) {
      alert("Error: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading(true);
    setStatusMessage(`Parsing document: ${file.name}...`);
    try {
      const data = await uploadDocument(file);
      setProfile(data.profile);
      setStatusMessage(`${file.name} parsed successfully.`);
      const rep = await deliberateSchemes(data.profile, undefined, 4);
      setReport(rep);
    } catch (err: any) {
      alert("Upload error: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleRunDeliberate = async () => {
    if (!profile) return;
    setLoading(true);
    try {
      const rep = await deliberateSchemes(profile, undefined, 4);
      setReport(rep);
    } catch (err: any) {
      alert("Deliberation error: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSendChat = async (textToSend?: string) => {
    const msg = textToSend || chatInput.trim();
    if (!msg) return;
    setChatInput("");
    setChatMessages((prev) => [...prev, { role: "user", content: msg }]);
    setChatLoading(true);

    try {
      const res = await sendChatMessage(msg, profile);
      setChatMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.reply, cited: res.cited_schemes },
      ]);
    } catch (err: any) {
      setChatMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${err.message}` },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* Hero Banner */}
      <div className="bg-gradient-to-r from-[#0A2540] via-indigo-950 to-slate-900 text-white rounded-2xl p-6 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <span className="inline-block px-3 py-1 bg-[#FF9933] text-slate-900 font-bold text-xs uppercase tracking-wider rounded-md mb-2">
              Phase 4 Full-Stack Platform Active
            </span>
            <h2 className="text-2xl font-bold">Document-Driven Scheme Matching & Gap Analysis</h2>
            <p className="text-slate-300 text-sm mt-1 max-w-2xl">
              Extract your business digital twin from GST / Udyam documents. Our RAG reasoner evaluates 41 official policies, calculates exact subsidies, and synthesizes step-by-step document gap resolutions.
            </p>
          </div>
          <div className="flex flex-col sm:flex-row gap-2">
            <button
              onClick={() => handleLoadSample(1)}
              className="px-3 py-1.5 bg-white/10 hover:bg-white/20 text-white text-xs font-semibold rounded-lg border border-white/20 transition"
            >
              Sample 1: Tech Startup (MH)
            </button>
            <button
              onClick={() => handleLoadSample(2)}
              className="px-3 py-1.5 bg-white/10 hover:bg-white/20 text-white text-xs font-semibold rounded-lg border border-white/20 transition"
            >
              Sample 2: Food Micro (GJ)
            </button>
            <button
              onClick={() => handleLoadSample(3)}
              className="px-3 py-1.5 bg-white/10 hover:bg-white/20 text-white text-xs font-semibold rounded-lg border border-white/20 transition"
            >
              Sample 3: Textile LLP (KA)
            </button>
          </div>
        </div>
      </div>

      {/* Main Grid: Left Profile & Upload, Right Results */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        
        {/* Left Column: Upload & Digital Twin Card */}
        <div className="lg:col-span-5 space-y-6">
          
          {/* Upload Dropzone */}
          <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
            <h3 className="text-sm font-bold text-slate-800">📄 Upload Registration Document</h3>
            <p className="text-xs text-slate-500 mt-1 mb-3">Accepts Form GST REG-06 or Udyam (PDF / Images)</p>
            <label className="border-2 border-dashed border-slate-300 hover:border-[#0A2540] rounded-xl p-5 text-center cursor-pointer transition flex flex-col items-center bg-slate-50/50 block">
              <input type="file" onChange={handleFileUpload} className="hidden" accept=".pdf,.png,.jpg,.jpeg,.txt,.json" />
              <span className="text-2xl mb-1">☁️</span>
              <span className="text-xs font-semibold text-slate-700">Click to browse or drop certificate</span>
              <span className="text-[11px] text-slate-400">Zero-retention ephemeral parsing</span>
            </label>
            {statusMessage && (
              <p className="text-xs font-semibold text-emerald-600 mt-2">✓ {statusMessage}</p>
            )}
          </div>

          {/* Business Profile Digital Twin Card */}
          {profile && (
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <h3 className="text-sm font-bold text-slate-800">🏢 Extracted Digital Twin</h3>
                <span className="px-2 py-0.5 rounded text-xs font-bold bg-blue-50 text-blue-700 border border-blue-200">
                  {profile.msme_tier}
                </span>
              </div>

              <div className="space-y-3 text-xs">
                <div>
                  <span className="text-slate-400 block font-medium">Legal Entity Name</span>
                  <input
                    type="text"
                    value={profile.legal_name}
                    onChange={(e) => setProfile({ ...profile, legal_name: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded px-2.5 py-1.5 font-semibold text-slate-800"
                  />
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <span className="text-slate-400 block font-medium">GSTIN</span>
                    <span className="font-mono font-bold text-slate-700">{profile.gstin || "N/A"}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block font-medium">State</span>
                    <span className="font-semibold text-slate-700">{profile.principal_address.state_name}</span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <span className="text-slate-400 block font-medium">Constitution</span>
                    <span className="font-medium text-slate-700">{profile.constitution}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block font-medium">Primary Sector</span>
                    <input
                      type="text"
                      value={profile.primary_sector}
                      onChange={(e) => setProfile({ ...profile, primary_sector: e.target.value })}
                      className="w-full bg-slate-50 border border-slate-200 rounded px-2 py-1 font-medium text-slate-700"
                    />
                  </div>
                </div>

                {/* Interactive Toggles */}
                <div className="pt-2 border-t border-slate-100 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-600">Turnover Bracket</span>
                    <select
                      value={profile.turnover_bracket}
                      onChange={(e) => setProfile({ ...profile, turnover_bracket: e.target.value })}
                      className="bg-slate-50 border border-slate-200 rounded px-2 py-1 text-slate-700"
                    >
                      <option value="Below ₹1 Crore">Below ₹1 Crore</option>
                      <option value="₹1 Crore to ₹5 Crore">₹1 Crore to ₹5 Crore</option>
                      <option value="₹5 Crore to ₹50 Crore">₹5 Crore to ₹50 Crore</option>
                      <option value="₹50 Crore to ₹250 Crore">₹50 Crore to ₹250 Crore</option>
                      <option value="Above ₹250 Crore">Above ₹250 Crore</option>
                      <option value="Unknown">Unknown</option>
                    </select>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-slate-600">Woman-Led / Majority Owned</span>
                    <input
                      type="checkbox"
                      checked={profile.is_woman_owned}
                      onChange={(e) => setProfile({ ...profile, is_woman_owned: e.target.checked })}
                      className="w-4 h-4 rounded text-blue-600"
                    />
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-slate-600">DPIIT Startup Recognized</span>
                    <input
                      type="checkbox"
                      checked={profile.is_dpiit_recognized}
                      onChange={(e) => setProfile({ ...profile, is_dpiit_recognized: e.target.checked })}
                      className="w-4 h-4 rounded text-blue-600"
                    />
                  </div>
                </div>

                <button
                  onClick={handleRunDeliberate}
                  disabled={loading}
                  className="w-full mt-2 py-2.5 bg-[#0A2540] hover:bg-slate-900 text-white font-bold text-xs rounded-xl shadow transition"
                >
                  {loading ? "Deliberating..." : "Re-Run Reasoner & Gap Analysis"}
                </button>
              </div>
            </div>
          )}

          {/* Policy Copilot Chat Widget */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-3">
            <div className="flex items-center justify-between border-b pb-2">
              <h3 className="text-xs font-bold text-purple-700 uppercase tracking-wider">
                💬 Policy Copilot Chat
              </h3>
              <span className="text-[10px] bg-purple-50 text-purple-700 px-2 py-0.5 rounded font-semibold">
                RAG Grounded
              </span>
            </div>

            <div className="h-44 overflow-y-auto space-y-2 text-xs p-1">
              {chatMessages.map((m, idx) => (
                <div
                  key={idx}
                  className={`p-2.5 rounded-xl ${
                    m.role === "user"
                      ? "bg-[#0A2540] text-white ml-6 text-right"
                      : "bg-slate-100 text-slate-800 mr-6"
                  }`}
                >
                  <p>{m.content}</p>
                  {m.cited && m.cited.length > 0 && (
                    <div className="mt-1 pt-1 border-t border-slate-200 text-[10px] text-slate-600 flex flex-wrap gap-1">
                      <span>Cited:</span>
                      {m.cited.map((c, i) => (
                        <span key={i} className="font-semibold text-blue-700">
                          {c.scheme_short_code}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {chatLoading && (
                <div className="text-xs text-slate-400 italic">Thinking...</div>
              )}
            </div>

            <div className="flex space-x-2">
              <input
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSendChat()}
                placeholder="Ask about subsidies, collateral..."
                className="flex-1 text-xs bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 focus:outline-none"
              />
              <button
                onClick={() => handleSendChat()}
                className="px-3 py-1.5 bg-[#0A2540] text-white text-xs font-semibold rounded-lg hover:bg-slate-900"
              >
                Send
              </button>
            </div>
          </div>
        </div>

        {/* Right Column: Deliberation Results */}
        <div className="lg:col-span-7 space-y-6">
          {report && (
            <>
              {/* Metric Breakdown */}
              <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-base font-bold text-slate-900">Eligibility Verdict & Gap Analysis</h3>
                  <span className="text-xs text-slate-500">Universe: {report.total_schemes_searched} Policies</span>
                </div>

                <div className="grid grid-cols-4 gap-2 text-center text-xs">
                  <div className="bg-slate-50 p-2.5 rounded-lg border">
                    <span className="text-slate-400 font-medium block">Audited</span>
                    <span className="text-lg font-bold text-slate-800">{report.top_candidates_evaluated}</span>
                  </div>
                  <div className="bg-emerald-50 p-2.5 rounded-lg border border-emerald-100">
                    <span className="text-emerald-600 font-medium block">Eligible</span>
                    <span className="text-lg font-bold text-emerald-700">{report.eligible_count}</span>
                  </div>
                  <div className="bg-yellow-50 p-2.5 rounded-lg border border-yellow-100">
                    <span className="text-yellow-700 font-medium block">Conditional</span>
                    <span className="text-lg font-bold text-yellow-800">{report.conditional_count}</span>
                  </div>
                  <div className="bg-red-50 p-2.5 rounded-lg border border-red-100">
                    <span className="text-red-600 font-medium block">Ineligible</span>
                    <span className="text-lg font-bold text-red-700">{report.ineligible_count}</span>
                  </div>
                </div>

                <div className="p-3 bg-blue-50/70 border border-blue-100 rounded-lg text-xs text-slate-700">
                  <span className="font-bold text-[#0A2540] uppercase tracking-wider block mb-1">
                    🧭 Strategic Advisory
                  </span>
                  {report.strategic_roadmap_summary}
                </div>
              </div>

              {/* Scheme Cards */}
              <div className="space-y-4">
                {report.top_recommendations.map((item, idx) => (
                  <div key={idx} className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center space-x-2">
                          <span className="text-xs font-bold text-slate-400">#{idx + 1}</span>
                          <span
                            className={`px-2 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider ${
                              item.verdict === "Eligible"
                                ? "bg-emerald-100 text-emerald-800"
                                : item.verdict === "Ineligible"
                                ? "bg-red-100 text-red-800"
                                : "bg-yellow-100 text-yellow-800"
                            }`}
                          >
                            {item.verdict}
                          </span>
                          <span className="text-xs font-mono font-bold bg-slate-100 text-slate-700 px-2 py-0.5 rounded">
                            Score: {item.match_score}/100
                          </span>
                        </div>
                        <h4 className="text-sm font-bold text-slate-900 mt-1.5">
                          {item.scheme_name} ({item.scheme_short_code})
                        </h4>
                        <p className="text-xs text-slate-500">{item.nodal_agency}</p>
                      </div>

                      <a
                        href={item.application_portal_url}
                        target="_blank"
                        rel="noreferrer"
                        className="px-3 py-1.5 text-xs font-bold bg-[#0A2540] text-white rounded-lg hover:bg-slate-900 transition flex-shrink-0"
                      >
                        Apply Portal ↗
                      </a>
                    </div>

                    {/* Financial Benefit Box */}
                    <div className="p-2.5 bg-emerald-50/70 border border-emerald-100 rounded-lg text-xs">
                      <span className="font-bold text-emerald-800 block">💰 Benefit Package:</span>
                      <p className="text-slate-800 font-medium">{item.financial_benefit.quantum_description}</p>
                      {item.financial_benefit.special_affirmative_boost && (
                        <p className="text-emerald-700 font-semibold mt-1">
                          ★ {item.financial_benefit.special_affirmative_boost}
                        </p>
                      )}
                    </div>

                    {/* Criteria Checkpoints */}
                    <div className="text-xs space-y-1">
                      <span className="font-bold text-slate-700 block">Criteria Verification:</span>
                      {item.eligibility_rationale.slice(0, 3).map((r, i) => (
                        <p key={i} className="text-slate-600">✓ {r}</p>
                      ))}
                      {item.disqualification_or_gap_reasons.map((g, i) => (
                        <p key={i} className="text-amber-700">⚠ {g}</p>
                      ))}
                    </div>

                    {/* Document Gap Accordion */}
                    <details className="text-xs bg-slate-50 rounded-lg border border-slate-200 p-2.5">
                      <summary className="font-bold text-slate-800 cursor-pointer flex justify-between">
                        <span>📋 Document Compliance Audit ({item.document_checklist.length} Documents)</span>
                        <span className="text-slate-400 font-normal">Click to toggle</span>
                      </summary>
                      <div className="mt-2 space-y-2">
                        {item.document_checklist.map((doc, dIdx) => (
                          <div key={dIdx} className="p-2 bg-white rounded border border-slate-100 flex justify-between items-start">
                            <div>
                              <span className="font-semibold text-slate-800 block">{doc.document_name}</span>
                              <span className="text-[11px] text-slate-500 block">Authority: {doc.issuing_authority}</span>
                              <span className="text-[11px] text-slate-600 italic">Action: {doc.how_to_obtain}</span>
                            </div>
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                doc.status === "Available"
                                  ? "bg-emerald-50 text-emerald-700"
                                  : doc.status === "Missing"
                                  ? "bg-red-50 text-red-700"
                                  : "bg-amber-50 text-amber-700"
                              }`}
                            >
                              {doc.status} ({doc.estimated_turnaround_days}d)
                            </span>
                          </div>
                        ))}
                      </div>
                    </details>

                    {/* Application Process Accordion */}
                    {item.application_roadmap && item.application_roadmap.length > 0 && (
                      <details className="text-xs bg-indigo-50/50 rounded-lg border border-indigo-100 p-2.5 mt-2">
                        <summary className="font-bold text-indigo-950 cursor-pointer flex justify-between">
                          <span>🚀 Step-by-Step Application Process ({item.application_roadmap.length} Steps)</span>
                          <span className="text-indigo-600 font-normal">Click to toggle</span>
                        </summary>
                        <div className="mt-2 space-y-1.5 pl-1">
                          {item.application_roadmap.map((step, sIdx) => (
                            <div key={sIdx} className="p-2 bg-white rounded border border-indigo-50 text-slate-700 flex items-start gap-2">
                              <span className="font-bold text-indigo-700 text-xs flex-shrink-0">{sIdx + 1}.</span>
                              <span>{step}</span>
                            </div>
                          ))}
                        </div>
                      </details>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

      </div>
    </div>
  );
}

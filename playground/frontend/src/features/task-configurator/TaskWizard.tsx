import React, { useState } from "react";
import {
  ShieldCheck,
  Globe,
  Settings2,
  FileText,
  Plus,
  Trash2,
  ArrowRight,
  CheckCircle,
  Eye,
  Layers,
  Sparkles,
} from "lucide-react";
import { useStudioStore } from "../../stores/useStudioStore";

export const TaskWizard: React.FC = () => {
  const { tasks, selectedTaskId, setSelectedTaskId, createTask, isLoading } = useStudioStore();

  const [step, setStep] = useState<1 | 2 | 3>(1);

  // Form states
  const [name, setName] = useState("");
  const [goalDescription, setGoalDescription] = useState("");
  const [instructions, setInstructions] = useState("");

  const [headless, setHeadless] = useState(false);
  const [useCloakBrowser, setUseCloakBrowser] = useState(true);
  const [userAgent, setUserAgent] = useState("");
  const [envVars, setEnvVars] = useState<Array<{ key: string; value: string }>>([
    { key: "ANTI_BOT_BYPASS", value: "strict" },
  ]);

  const [urlsInput, setUrlsInput] = useState(
    "https://api.example.com/v1/auth/login\nhttps://api.example.com/v1/user/profile"
  );

  const parsedUrls = urlsInput
    .split("\n")
    .map((u) => u.trim())
    .filter((u) => u.length > 0);

  const handleAddEnvVar = () => {
    setEnvVars([...envVars, { key: "", value: "" }]);
  };

  const handleRemoveEnvVar = (idx: number) => {
    setEnvVars(envVars.filter((_, i) => i !== idx));
  };

  const handleEnvVarChange = (idx: number, field: "key" | "value", val: string) => {
    const next = [...envVars];
    next[idx][field] = val;
    setEnvVars(next);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !goalDescription.trim() || parsedUrls.length === 0) {
      return;
    }

    const envMap: Record<string, string> = {};
    for (const item of envVars) {
      if (item.key.trim()) {
        envMap[item.key.trim()] = item.value.trim();
      }
    }

    await createTask({
      name: name.trim(),
      goal_description: goalDescription.trim(),
      instructions: instructions.trim(),
      env_vars: envMap,
      initial_urls: parsedUrls,
      browser_config: {
        headless,
        use_cloakbrowser: useCloakBrowser,
        user_agent: userAgent.trim() || undefined,
        viewport_width: 1440,
        viewport_height: 900,
      },
    });

    // Reset form after submit
    setName("");
    setGoalDescription("");
    setInstructions("");
    setStep(1);
  };

  const loadTemplate = (type: "ecommerce" | "social" | "fintech") => {
    if (type === "ecommerce") {
      setName("E-Commerce Checkout & Signature Flow");
      setGoalDescription("Intercept and reverse-engineer HMAC cart-add and checkout token generation.");
      setInstructions("Navigate to PDP, click Add to Cart, capture encrypted payload and cookie headers.");
      setUrlsInput("https://shopee.vn/api/v4/item/get\nhttps://shopee.vn/api/v4/cart/add_to_cart\nhttps://shopee.vn/api/v4/checkout/get");
    } else if (type === "social") {
      setName("Social Feed WASM Token Extractor");
      setGoalDescription("Deobfuscate canvas fingerprinting probe and extract _signature generator from WASM.");
      setInstructions("Observe request query params and find source buffer in memory.");
      setUrlsInput("https://www.tiktok.com/api/recommend/item_list/\nhttps://www.tiktok.com/api/comment/list/");
    } else {
      setName("FinTech OAuth2 PKCE Lineage");
      setGoalDescription("Map code_challenge, code_verifier and token exchange pipeline.");
      setInstructions("Trace code_verifier generated in sessionStorage to final POST /oauth/token.");
      setUrlsInput("https://auth.bank.example.com/oauth/authorize\nhttps://auth.bank.example.com/oauth/token");
    }
    setUseCloakBrowser(true);
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 p-6 max-w-7xl mx-auto">
      {/* Left Column: Task Creator Wizard */}
      <div className="lg:col-span-8 flex flex-col gap-6">
        <div className="glass-panel rounded-xl p-6 border border-border-subtle">
          <div className="flex items-center justify-between pb-5 border-b border-border-subtle">
            <div>
              <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                <Settings2 className="h-5 w-5 text-indigo-400" />
                Task Configurator Wizard
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                Configure reverse-engineering objective, cloaked browser flags, and initial target URLs.
              </p>
            </div>

            {/* Quick Templates */}
            <div className="flex items-center gap-1.5 bg-background-base p-1 rounded-lg border border-border-subtle">
              <span className="text-[11px] text-slate-500 px-2 flex items-center gap-1">
                <Sparkles className="w-3 h-3 text-amber-400" /> Presets:
              </span>
              <button
                onClick={() => loadTemplate("ecommerce")}
                type="button"
                className="text-[11px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 transition"
              >
                E-Commerce
              </button>
              <button
                onClick={() => loadTemplate("social")}
                type="button"
                className="text-[11px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 transition"
              >
                Anti-Bot WASM
              </button>
              <button
                onClick={() => loadTemplate("fintech")}
                type="button"
                className="text-[11px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 transition"
              >
                PKCE
              </button>
            </div>
          </div>

          {/* Stepper Progress */}
          <div className="flex items-center justify-between my-6 px-4">
            <button
              type="button"
              onClick={() => setStep(1)}
              className={`flex items-center gap-2 text-xs font-medium ${
                step >= 1 ? "text-indigo-400" : "text-slate-500"
              }`}
            >
              <span
                className={`h-6 w-6 rounded-full flex items-center justify-center text-xs font-bold ${
                  step === 1 ? "bg-indigo-600 text-white" : step > 1 ? "bg-emerald-600 text-white" : "bg-slate-800 text-slate-400"
                }`}
              >
                1
              </span>
              <span>Metadata & Goal</span>
            </button>
            <div className={`h-0.5 flex-1 mx-3 ${step > 1 ? "bg-indigo-600" : "bg-slate-800"}`} />

            <button
              type="button"
              onClick={() => setStep(2)}
              className={`flex items-center gap-2 text-xs font-medium ${
                step >= 2 ? "text-indigo-400" : "text-slate-500"
              }`}
            >
              <span
                className={`h-6 w-6 rounded-full flex items-center justify-center text-xs font-bold ${
                  step === 2 ? "bg-indigo-600 text-white" : step > 2 ? "bg-emerald-600 text-white" : "bg-slate-800 text-slate-400"
                }`}
              >
                2
              </span>
              <span>Browser & Env</span>
            </button>
            <div className={`h-0.5 flex-1 mx-3 ${step > 2 ? "bg-indigo-600" : "bg-slate-800"}`} />

            <button
              type="button"
              onClick={() => setStep(3)}
              className={`flex items-center gap-2 text-xs font-medium ${
                step >= 3 ? "text-indigo-400" : "text-slate-500"
              }`}
            >
              <span
                className={`h-6 w-6 rounded-full flex items-center justify-center text-xs font-bold ${
                  step === 3 ? "bg-indigo-600 text-white" : "bg-slate-800 text-slate-400"
                }`}
              >
                3
              </span>
              <span>Start URLs & Sessions</span>
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Step 1: Metadata */}
            {step === 1 && (
              <div className="space-y-4 animate-in fade-in">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Task Name <span className="text-red-400">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Shopee Checkout API Reversal"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full bg-background-elevated border border-border-subtle rounded-lg px-3.5 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Goal Description <span className="text-red-400">*</span>
                  </label>
                  <textarea
                    required
                    rows={3}
                    placeholder="Describe what specific API request or crypto token signature you want to reconstruct..."
                    value={goalDescription}
                    onChange={(e) => setGoalDescription(e.target.value)}
                    className="w-full bg-background-elevated border border-border-subtle rounded-lg px-3.5 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Agent Instructions & Guidelines
                  </label>
                  <textarea
                    rows={3}
                    placeholder="Step-by-step user instructions for the agent or human operator when clicking through pages..."
                    value={instructions}
                    onChange={(e) => setInstructions(e.target.value)}
                    className="w-full bg-background-elevated border border-border-subtle rounded-lg px-3.5 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  />
                </div>

                <div className="flex justify-end pt-3">
                  <button
                    type="button"
                    onClick={() => {
                      if (name.trim() && goalDescription.trim()) setStep(2);
                    }}
                    disabled={!name.trim() || !goalDescription.trim()}
                    className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg text-xs font-medium transition shadow-glow"
                  >
                    <span>Next: Browser & Env</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            )}

            {/* Step 2: Browser & Environment */}
            {step === 2 && (
              <div className="space-y-4 animate-in fade-in">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-3.5 rounded-lg border border-border-subtle bg-background-elevated flex items-start justify-between">
                    <div>
                      <div className="text-xs font-medium text-slate-200 flex items-center gap-1.5">
                        <ShieldCheck className="w-4 h-4 text-emerald-400" />
                        Use CloakBrowser (Stealth)
                      </div>
                      <p className="text-[11px] text-slate-400 mt-1">
                        Patches navigator.webdriver, CDP runtime fingerprints & canvas noise.
                      </p>
                    </div>
                    <input
                      type="checkbox"
                      checked={useCloakBrowser}
                      onChange={(e) => setUseCloakBrowser(e.target.checked)}
                      className="mt-1 h-4 w-4 rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-indigo-500"
                    />
                  </div>

                  <div className="p-3.5 rounded-lg border border-border-subtle bg-background-elevated flex items-start justify-between">
                    <div>
                      <div className="text-xs font-medium text-slate-200 flex items-center gap-1.5">
                        <Eye className="w-4 h-4 text-indigo-400" />
                        Headless Mode
                      </div>
                      <p className="text-[11px] text-slate-400 mt-1">
                        Run browser in background without visible window. (Recommended: unchecked for manual capture).
                      </p>
                    </div>
                    <input
                      type="checkbox"
                      checked={headless}
                      onChange={(e) => setHeadless(e.target.checked)}
                      className="mt-1 h-4 w-4 rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-indigo-500"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Custom User-Agent (Optional)
                  </label>
                  <input
                    type="text"
                    placeholder="Leave empty for auto Chrome 128 User-Agent"
                    value={userAgent}
                    onChange={(e) => setUserAgent(e.target.value)}
                    className="w-full bg-background-elevated border border-border-subtle rounded-lg px-3.5 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                  />
                </div>

                {/* Env Vars Editor */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-xs font-medium text-slate-300">
                      Environment Variables & Secrets
                    </label>
                    <button
                      type="button"
                      onClick={handleAddEnvVar}
                      className="flex items-center gap-1 text-[11px] text-indigo-400 hover:text-indigo-300"
                    >
                      <Plus className="w-3.5 h-3.5" /> Add Variable
                    </button>
                  </div>

                  <div className="space-y-2">
                    {envVars.map((env, idx) => (
                      <div key={idx} className="flex items-center gap-2">
                        <input
                          type="text"
                          placeholder="KEY (e.g. AUTH_TOKEN)"
                          value={env.key}
                          onChange={(e) => handleEnvVarChange(idx, "key", e.target.value)}
                          className="flex-1 bg-background-elevated border border-border-subtle rounded-md px-2.5 py-1.5 text-xs text-slate-100 placeholder-slate-500 font-mono focus:outline-none focus:border-indigo-500"
                        />
                        <input
                          type="text"
                          placeholder="VALUE"
                          value={env.value}
                          onChange={(e) => handleEnvVarChange(idx, "value", e.target.value)}
                          className="flex-1 bg-background-elevated border border-border-subtle rounded-md px-2.5 py-1.5 text-xs text-slate-100 placeholder-slate-500 font-mono focus:outline-none focus:border-indigo-500"
                        />
                        <button
                          type="button"
                          onClick={() => handleRemoveEnvVar(idx)}
                          className="p-1.5 text-slate-500 hover:text-red-400"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="flex justify-between pt-3">
                  <button
                    type="button"
                    onClick={() => setStep(1)}
                    className="px-3.5 py-2 border border-border-subtle text-slate-300 hover:bg-slate-800 rounded-lg text-xs font-medium transition"
                  >
                    Back
                  </button>
                  <button
                    type="button"
                    onClick={() => setStep(3)}
                    className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-medium transition shadow-glow"
                  >
                    <span>Next: Start URLs</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            )}

            {/* Step 3: Start URLs & Review */}
            {step === 3 && (
              <div className="space-y-4 animate-in fade-in">
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="text-xs font-medium text-slate-300">
                      Initial URLs (1 URL per line = 1 Browser Session) <span className="text-red-400">*</span>
                    </label>
                    <span className="text-[11px] font-medium text-indigo-400 bg-indigo-950/60 px-2 py-0.5 rounded border border-indigo-500/20">
                      {parsedUrls.length} Sessions will be spawned
                    </span>
                  </div>
                  <textarea
                    rows={4}
                    required
                    placeholder="https://example.com/login&#10;https://example.com/dashboard"
                    value={urlsInput}
                    onChange={(e) => setUrlsInput(e.target.value)}
                    className="w-full bg-background-elevated border border-border-subtle rounded-lg px-3.5 py-2 text-xs font-mono text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                  />
                </div>

                {/* Review Summary Box */}
                <div className="p-4 rounded-lg bg-background-elevated border border-border-subtle text-xs space-y-2">
                  <div className="font-semibold text-slate-200 flex items-center gap-1.5">
                    <CheckCircle className="w-4 h-4 text-emerald-400" />
                    Review Task Summary
                  </div>
                  <div className="grid grid-cols-2 gap-2 pt-1 text-slate-400">
                    <div>
                      Task Name: <span className="text-slate-200 font-medium">{name || "N/A"}</span>
                    </div>
                    <div>
                      Browser Stealth:{" "}
                      <span className="text-emerald-400 font-medium">
                        {useCloakBrowser ? "CloakBrowser ON" : "Default"}
                      </span>
                    </div>
                    <div>
                      Headless:{" "}
                      <span className="text-slate-200 font-medium">{headless ? "YES" : "NO (Interactive)"}</span>
                    </div>
                    <div>
                      Sessions to create:{" "}
                      <span className="text-indigo-400 font-bold">{parsedUrls.length}</span>
                    </div>
                  </div>
                </div>

                <div className="flex justify-between pt-3">
                  <button
                    type="button"
                    onClick={() => setStep(2)}
                    className="px-3.5 py-2 border border-border-subtle text-slate-300 hover:bg-slate-800 rounded-lg text-xs font-medium transition"
                  >
                    Back
                  </button>
                  <button
                    type="submit"
                    disabled={isLoading || parsedUrls.length === 0}
                    className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-400 disabled:opacity-50 text-white rounded-lg text-xs font-semibold transition shadow-glow"
                  >
                    <Plus className="w-4 h-4" />
                    <span>Create Task & Generate Sessions</span>
                  </button>
                </div>
              </div>
            )}
          </form>
        </div>
      </div>

      {/* Right Column: Existing Tasks List */}
      <div className="lg:col-span-4 flex flex-col gap-4">
        <div className="glass-panel rounded-xl p-5 border border-border-subtle flex flex-col h-full">
          <div className="flex items-center justify-between pb-3 border-b border-border-subtle">
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Layers className="h-4 w-4 text-indigo-400" />
              Active Tasks ({tasks.length})
            </h3>
          </div>

          <div className="space-y-3 mt-4 overflow-y-auto max-h-[560px] pr-1">
            {tasks.map((task) => {
              const isSelected = task.id === selectedTaskId;
              return (
                <div
                  key={task.id}
                  onClick={() => setSelectedTaskId(task.id)}
                  className={`p-3.5 rounded-lg border cursor-pointer transition-all ${
                    isSelected
                      ? "bg-indigo-950/40 border-indigo-500/50 shadow-glow"
                      : "bg-background-elevated border-border-subtle hover:border-slate-700"
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <h4 className="text-xs font-bold text-slate-100 leading-snug">{task.name}</h4>
                    <span
                      className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                        task.status === "COMPLETED"
                          ? "bg-emerald-950 text-emerald-400 border border-emerald-500/30"
                          : task.status === "IN_PROGRESS"
                          ? "bg-blue-950 text-blue-400 border border-blue-500/30"
                          : "bg-slate-800 text-slate-300"
                      }`}
                    >
                      {task.status}
                    </span>
                  </div>

                  <p className="text-[11px] text-slate-400 line-clamp-2 mt-1.5 leading-relaxed">
                    {task.goal_description}
                  </p>

                  <div className="flex items-center justify-between text-[11px] text-slate-500 mt-3 pt-2 border-t border-border-subtle">
                    <span>{task.session_ids?.length || 0} sessions</span>
                    <span className="font-mono text-[10px]">
                      {new Date(task.created_at_ns / 1_000_000).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};

import React from "react";
import { CheckCircle2, AlertTriangle, Info, XCircle, X } from "lucide-react";
import { useStudioStore } from "../../stores/useStudioStore";

export const ToastContainer: React.FC = () => {
  const { toasts, removeToast } = useStudioStore();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 max-w-md w-full pointer-events-none">
      {toasts.map((toast) => {
        const isSuccess = toast.type === "success";
        const isError = toast.type === "error";
        const isWarning = toast.type === "warning";

        return (
          <div
            key={toast.id}
            className={`pointer-events-auto flex items-start gap-3 p-3.5 rounded-lg border shadow-xl backdrop-blur-md transition-all duration-200 animate-in fade-in slide-in-from-bottom-2 ${
              isSuccess
                ? "bg-emerald-950/80 border-emerald-500/30 text-emerald-200"
                : isError
                ? "bg-red-950/80 border-red-500/30 text-red-200"
                : isWarning
                ? "bg-amber-950/80 border-amber-500/30 text-amber-200"
                : "bg-slate-900/90 border-slate-700/50 text-slate-200"
            }`}
          >
            <div className="mt-0.5 shrink-0">
              {isSuccess && <CheckCircle2 className="w-4 h-4 text-emerald-400" />}
              {isError && <XCircle className="w-4 h-4 text-red-400" />}
              {isWarning && <AlertTriangle className="w-4 h-4 text-amber-400" />}
              {!isSuccess && !isError && !isWarning && <Info className="w-4 h-4 text-blue-400" />}
            </div>
            <div className="flex-1 text-xs leading-relaxed font-sans">{toast.message}</div>
            <button
              onClick={() => removeToast(toast.id)}
              className="text-slate-400 hover:text-white transition-colors shrink-0"
              aria-label="Close notification"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
};

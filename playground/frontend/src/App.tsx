import React, { useEffect } from "react";
import { Navbar } from "./components/layout/Navbar";
import { ToastContainer } from "./components/ui/ToastContainer";
import { TaskWizard } from "./features/task-configurator/TaskWizard";
import { SessionLauncherGrid } from "./features/session-launcher/SessionLauncherGrid";
import { GraphStudio } from "./features/graph-studio/GraphStudio";
import { EvolutionDashboard } from "./features/evolution-dashboard/EvolutionDashboard";
import { useStudioStore } from "./stores/useStudioStore";

export function App() {
  const { activeTab, fetchTasks } = useStudioStore();

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  return (
    <div className="min-h-screen bg-background-base text-slate-100 font-sans selection:bg-indigo-500 selection:text-white flex flex-col">
      <Navbar />

      <main className="flex-1 w-full overflow-x-hidden">
        {activeTab === "tasks" && <TaskWizard />}
        {activeTab === "launcher" && <SessionLauncherGrid />}
        {activeTab === "graph" && <GraphStudio />}
        {activeTab === "evolution" && <EvolutionDashboard />}
      </main>

      <ToastContainer />
    </div>
  );
}

export default App;

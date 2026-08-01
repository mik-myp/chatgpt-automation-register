import { create } from "zustand"

type WorkspaceState = {
  searchQuery: string
  selectedPipelineRunId: string | null
  setSearchQuery: (query: string) => void
  selectPipelineRun: (runId: string | null) => void
  resetWorkspace: () => void
}

const initialState = {
  searchQuery: "",
  selectedPipelineRunId: null,
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  ...initialState,
  setSearchQuery: (searchQuery) => set({ searchQuery }),
  selectPipelineRun: (selectedPipelineRunId) => set({ selectedPipelineRunId }),
  resetWorkspace: () => set(initialState),
}))

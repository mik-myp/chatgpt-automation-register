import { create } from "zustand"

type AccountsState = {
  importOpen: boolean
  deleteTarget: string | null
  selectedEmails: string[]
  bulkDeleteOpen: boolean
  setImportOpen: (open: boolean) => void
  setDeleteTarget: (email: string | null) => void
  setSelectedEmails: (emails: string[]) => void
  toggleSelectedEmail: (email: string) => void
  clearSelection: () => void
  setBulkDeleteOpen: (open: boolean) => void
}

export const useAccountsStore = create<AccountsState>((set) => ({
  importOpen: false,
  deleteTarget: null,
  selectedEmails: [],
  bulkDeleteOpen: false,
  setImportOpen: (importOpen) => set({ importOpen }),
  setDeleteTarget: (deleteTarget) => set({ deleteTarget }),
  setSelectedEmails: (selectedEmails) => set({ selectedEmails }),
  toggleSelectedEmail: (email) =>
    set((state) => ({
      selectedEmails: state.selectedEmails.includes(email)
        ? state.selectedEmails.filter((value) => value !== email)
        : [...state.selectedEmails, email],
    })),
  clearSelection: () => set({ selectedEmails: [] }),
  setBulkDeleteOpen: (bulkDeleteOpen) => set({ bulkDeleteOpen }),
}))

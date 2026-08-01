import { create } from "zustand"

import type { AccountStatus } from "@/api/generated"

type AccountStatusFilter = AccountStatus | "all"

type AccountsState = {
  search: string
  status: AccountStatusFilter
  page: number
  pageSize: number
  importOpen: boolean
  deleteTarget: string | null
  selectedEmails: string[]
  bulkDeleteOpen: boolean
  setSearch: (search: string) => void
  setStatus: (status: AccountStatusFilter) => void
  setPage: (page: number) => void
  setPageSize: (pageSize: number) => void
  setImportOpen: (open: boolean) => void
  setDeleteTarget: (email: string | null) => void
  setSelectedEmails: (emails: string[]) => void
  toggleSelectedEmail: (email: string) => void
  clearSelection: () => void
  setBulkDeleteOpen: (open: boolean) => void
}

export const useAccountsStore = create<AccountsState>((set) => ({
  search: "",
  status: "all",
  page: 0,
  pageSize: 25,
  importOpen: false,
  deleteTarget: null,
  selectedEmails: [],
  bulkDeleteOpen: false,
  setSearch: (search) => set({ search, page: 0, selectedEmails: [] }),
  setStatus: (status) => set({ status, page: 0, selectedEmails: [] }),
  setPage: (page) => set({ page, selectedEmails: [] }),
  setPageSize: (pageSize) => set({ pageSize, page: 0, selectedEmails: [] }),
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

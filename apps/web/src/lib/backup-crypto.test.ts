import { describe, expect, it } from "vitest"

import { decryptBackup, encryptBackup, isEncryptedBackup } from "./backup-crypto"

describe("backup encryption", () => {
  it("round trips sensitive backup data", async () => {
    const source = { version: 2, sections: { credentials: [{ password: "known" }] } }
    const encrypted = await encryptBackup(source, "personal-passphrase")

    expect(isEncryptedBackup(encrypted)).toBe(true)
    expect(JSON.stringify(encrypted)).not.toContain("known")
    await expect(decryptBackup(encrypted, "personal-passphrase")).resolves.toEqual(source)
  })

  it("rejects a wrong passphrase", async () => {
    const encrypted = await encryptBackup({ ok: true }, "correct")
    await expect(decryptBackup(encrypted, "wrong")).rejects.toThrow("口令错误")
  })
})

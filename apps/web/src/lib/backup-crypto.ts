const ENCRYPTED_FORMAT = "gpt-auto-register-encrypted-backup"
const ITERATIONS = 250_000

export type EncryptedBackup = {
  format: typeof ENCRYPTED_FORMAT
  version: 1
  algorithm: "PBKDF2-SHA256/AES-256-GCM"
  iterations: number
  salt: string
  iv: string
  ciphertext: string
}

function toBase64(value: Uint8Array) {
  let binary = ""
  for (const byte of value) binary += String.fromCharCode(byte)
  return btoa(binary)
}

function fromBase64(value: string) {
  const binary = atob(value)
  return Uint8Array.from(binary, (character) => character.charCodeAt(0))
}

function toBuffer(value: Uint8Array) {
  return value.slice().buffer as ArrayBuffer
}

async function deriveKey(
  passphrase: string,
  salt: Uint8Array,
  iterations: number
) {
  if (!passphrase) throw new Error("请输入备份口令")
  const material = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(passphrase),
    "PBKDF2",
    false,
    ["deriveKey"]
  )
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", hash: "SHA-256", salt: toBuffer(salt), iterations },
    material,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"]
  )
}

export function isEncryptedBackup(value: unknown): value is EncryptedBackup {
  return (
    typeof value === "object" &&
    value !== null &&
    "format" in value &&
    value.format === ENCRYPTED_FORMAT
  )
}

export async function encryptBackup(value: unknown, passphrase: string) {
  const salt = crypto.getRandomValues(new Uint8Array(16))
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const key = await deriveKey(passphrase, salt, ITERATIONS)
  const plaintext = new TextEncoder().encode(JSON.stringify(value))
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    key,
    plaintext
  )
  return {
    format: ENCRYPTED_FORMAT,
    version: 1,
    algorithm: "PBKDF2-SHA256/AES-256-GCM",
    iterations: ITERATIONS,
    salt: toBase64(salt),
    iv: toBase64(iv),
    ciphertext: toBase64(new Uint8Array(ciphertext)),
  } satisfies EncryptedBackup
}

export async function decryptBackup(
  value: EncryptedBackup,
  passphrase: string
) {
  try {
    const salt = fromBase64(value.salt)
    const iv = fromBase64(value.iv)
    const key = await deriveKey(passphrase, salt, value.iterations)
    const plaintext = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: toBuffer(iv) },
      key,
      toBuffer(fromBase64(value.ciphertext))
    )
    return JSON.parse(new TextDecoder().decode(plaintext)) as unknown
  } catch (error) {
    throw new Error("备份口令错误或加密文件已损坏", { cause: error })
  }
}

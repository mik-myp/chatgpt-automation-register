import { Clipboard } from "lucide-react"
import { toast } from "sonner"

import { type RegistrationResultDetail } from "@/api/generated"
import {
  CredentialField,
  SecurityDetails,
  TotpSetup,
} from "@/features/results/components/result-details"
import { Button } from "@workspace/ui/components/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@workspace/ui/components/dialog"

export function ResultDetailDialog({
  open,
  onOpenChange,
  result,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  result?: RegistrationResultDetail
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100svh-2rem)] overflow-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>凭证详情</DialogTitle>
          <DialogDescription>{result?.email}</DialogDescription>
        </DialogHeader>
        {result && (
          <div>
            <div className="flex justify-end border-b pb-2">
              <Button
                onClick={() => {
                  void navigator.clipboard.writeText(
                    JSON.stringify(result, null, 2)
                  )
                  toast.success("已复制完整凭证 JSON")
                }}
                size="sm"
                variant="outline"
              >
                <Clipboard />
                复制 JSON
              </Button>
            </div>
            <CredentialField label="邮箱" value={result.email} />
            <CredentialField label="密码" value={result.password} sensitive />
            <TotpSetup email={result.email} secret={result.totp_secret} />
            <CredentialField
              label="Authenticator TOTP Secret"
              value={result.totp_secret}
              sensitive
            />
            <SecurityDetails metadata={result.metadata_json ?? {}} />
            <CredentialField label="Access Token" value={result.access_token} />
            <CredentialField
              label="Session Token"
              value={result.session_token}
            />
            <CredentialField
              label="Refresh Token"
              value={result.refresh_token}
            />
            <CredentialField label="ID Token" value={result.id_token} />
            <CredentialField label="Device ID" value={result.device_id} />
            <CredentialField label="Cookie" value={result.cookie_header} />
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

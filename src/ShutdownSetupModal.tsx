import React from "react";
import { ConfirmModal, TextField, ButtonItem, showModal } from "@decky/ui";
import { configureShutdown } from "./api";

interface Props {
  initialUser: string;
  onConfigured: (user: string) => void;
  close: () => void;
}

function ShutdownSetupDialog({ initialUser, onConfigured, close }: Props) {
  const [user, setUser] = React.useState(initialUser);
  const [password, setPassword] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [command, setCommand] = React.useState("");
  const [copied, setCopied] = React.useState(false);
  const [success, setSuccess] = React.useState(false);

  const submit = async () => {
    if (success) {
      close();
      return;
    }
    if (!user.trim() || !password || busy) return;
    setBusy(true);
    setError("");
    setCommand("");
    setCopied(false);
    try {
      const r: any = await configureShutdown(user.trim(), password);
      if (r?.error) {
        setError(r.message ?? r.error);
        if (r.command) setCommand(r.command);
        return;
      }
      setSuccess(true);
      onConfigured(r.user ?? user.trim());
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const copyCommand = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 3000);
    } catch {
      // ignore clipboard write failure
    }
  };

  let okText = "Configure";
  if (busy) okText = "Connecting…";
  else if (success) okText = "Done";
  else if (error) okText = "Try again";

  return React.createElement(
    ConfirmModal,
    {
      strTitle: "Configure shutdown",
      strOKButtonText: okText,
      strCancelButtonText: "Cancel",
      bOKDisabled: busy || (!success && (!user.trim() || !password)),
      bCancelDisabled: busy,
      bAlertDialog: success,
      bDisableBackgroundDismiss: true,
      onOK: submit,
      onCancel: close,
    },
    success
      ? React.createElement(
          "div",
          { style: { padding: "12px 0", textAlign: "left" } },
          React.createElement(
            "div",
            { style: { color: "#22c55e", fontSize: 14, fontWeight: 600, marginBottom: 8 } },
            "✓ Shutdown configured successfully"
          ),
          React.createElement(
            "div",
            { style: { fontSize: 12, opacity: 0.8, lineHeight: "1.4" } },
            "The SSH key was installed on the PC. Your password was not saved. You can now use the 'Shut down PC' button."
          )
        )
      : React.createElement(
          React.Fragment,
          null,
          React.createElement(TextField, {
            label: "Windows username",
            description: "What `whoami` prints on the PC, for example DESKTOP-PC\\luis",
            value: user,
            disabled: busy,
            focusOnMount: true,
            onChange: (e: any) => setUser(e.target.value),
          }),
          React.createElement(TextField, {
            label: "Windows password",
            description: "Used once to install the SSH key. It is not saved.",
            value: password,
            disabled: busy,
            bIsPassword: true,
            onChange: (e: any) => setPassword(e.target.value),
          }),
          busy
            ? React.createElement(
                "div",
                { style: { color: "#38bdf8", fontSize: 12, marginTop: 8 } },
                "Connecting to the PC over SSH and configuring shutdown key…"
              )
            : null,
          error
            ? React.createElement(
                "div",
                { style: { color: "#ef4444", fontSize: 12, marginTop: 8, lineHeight: "1.4" } },
                error
              )
            : null,
          command
            ? React.createElement(
                "div",
                { style: { marginTop: 12 } },
                React.createElement(
                  ButtonItem,
                  { layout: "below", onClick: copyCommand },
                  copied ? "Copied PowerShell command!" : "Copy PowerShell setup command"
                ),
                React.createElement(
                  "div",
                  { style: { fontSize: 11, opacity: 0.7, marginTop: 4 } },
                  "Run this in PowerShell as Administrator on the PC to enable OpenSSH Server, then try again."
                )
              )
            : null,
          !busy && !error
            ? React.createElement(
                "div",
                { style: { fontSize: 11, opacity: 0.7, marginTop: 8 } },
                "OpenSSH Server must be enabled on the PC. The PC needs to be on for this setup."
              )
            : null
        )
  );
}

export function openShutdownSetup(initialUser: string, onConfigured: (user: string) => void) {
  let close = () => {};
  const modal = showModal(
    React.createElement(ShutdownSetupDialog, { initialUser, onConfigured, close: () => close() })
  );
  close = modal.Close;
}

import React from "react";
import { ConfirmModal, TextField, showModal } from "@decky/ui";

interface Props {
  initialUser: string;
  onConfirm: (user: string, password: string) => void;
  close: () => void;
}

function ShutdownSetupDialog({ initialUser, onConfirm, close }: Props) {
  const [user, setUser] = React.useState(initialUser);
  const [password, setPassword] = React.useState("");

  const submit = () => {
    if (!user.trim() || !password) return;
    close();
    onConfirm(user.trim(), password);
  };

  return React.createElement(
    ConfirmModal,
    {
      strTitle: "Configure shutdown",
      strOKButtonText: "Configure",
      strCancelButtonText: "Cancel",
      bOKDisabled: !user.trim() || !password,
      bDisableBackgroundDismiss: true,
      onOK: submit,
      onCancel: close,
    },
    React.createElement(TextField, {
      label: "Windows username",
      description: "What `whoami` prints on the PC, for example DESKTOP-PC\\luis",
      value: user,
      focusOnMount: true,
      onChange: (e: any) => setUser(e.target.value),
    }),
    React.createElement(TextField, {
      label: "Windows password",
      description: "Used once to install the SSH key. It is not saved.",
      value: password,
      bIsPassword: true,
      onChange: (e: any) => setPassword(e.target.value),
    }),
    React.createElement("div", { style: { fontSize: 11, opacity: 0.7 } },
      "OpenSSH Server must be enabled on the PC. The PC needs to be on for this setup."
    )
  );
}

export function openShutdownSetup(initialUser: string, onConfirm: (user: string, password: string) => void) {
  let close = () => {};
  const modal = showModal(
    React.createElement(ShutdownSetupDialog, { initialUser, onConfirm, close: () => close() })
  );
  close = modal.Close;
}

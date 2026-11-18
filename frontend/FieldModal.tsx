import React from "react";
import { ConfirmModal, TextField, showModal } from "@decky/ui";

export type FieldKind = "ip" | "mac" | "broadcast";

interface FieldSpec {
  title: string;
  label: string;
  hint?: string;
  kind: FieldKind;
  initial: string;
  onConfirm: (value: string) => void;
}

const sanitize = (raw: string, kind: FieldKind): string => {
  if (kind === "ip" || kind === "broadcast") {
    return raw.replace(/[^0-9.]/g, "").slice(0, 15);
  }
  return raw.replace(/[^0-9a-fA-F:.-]/g, "").slice(0, 17);
};

const validIpv4 = (v: string): boolean => {
  if (!/^\d{1,3}(\.\d{1,3}){3}$/.test(v)) return false;
  return v.split(".").every((p) => Number(p) <= 255 && String(Number(p)) === p);
};

export const validateField = (value: string, kind: FieldKind): string => {
  const v = value.trim();
  switch (kind) {
    case "ip":
      if (!v) return "Enter the PC's IP address.";
      return validIpv4(v) ? "" : "Enter a valid IPv4 address, for example 192.168.1.42";
    case "broadcast":
      if (!v) return "";
      return validIpv4(v) ? "" : "Enter a valid IPv4 address, or leave empty to derive it.";
    case "mac":
      if (!v) return "";
      return /^([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}$|^[0-9a-fA-F]{12}$/.test(v)
        ? ""
        : "Enter 12 hex digits, for example AA:BB:CC:DD:EE:FF";
    default:
      return "";
  }
};

function FieldDialog(spec: FieldSpec & { close: () => void }) {
  const [value, setValue] = React.useState(spec.initial ?? "");
  const error = validateField(value, spec.kind);

  const submit = () => {
    if (error) return;
    spec.close();
    spec.onConfirm(value.trim());
  };

  return React.createElement(
    ConfirmModal,
    {
      strTitle: spec.title,
      strOKButtonText: "Save",
      strCancelButtonText: "Cancel",
      bOKDisabled: !!error,
      bDisableBackgroundDismiss: true,
      onOK: submit,
      onCancel: spec.close,
    },
    React.createElement(TextField, {
      label: spec.label,
      description: error || spec.hint,
      value,
      focusOnMount: true,
      bShowClearAction: true,
      onChange: (e: any) => setValue(sanitize(e.target.value, spec.kind)),
    })
  );
}

export function openFieldEditor(spec: FieldSpec) {
  let close = () => {};
  const modal = showModal(React.createElement(FieldDialog, { ...spec, close: () => close() }));
  close = modal.Close;
}

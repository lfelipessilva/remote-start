import React from "react";
import { PanelSection, PanelSectionRow, DialogButton, Focusable } from "@decky/ui";

export interface KeypadSpec {
  title: string;
  initial: string;
  charset: string;
  maxLength: number;
  error?: string;
  onCancel: () => void;
  onConfirm: (value: string) => void;
}

export function KeypadModal(props: KeypadSpec) {
  const [value, setValue] = React.useState(props.initial ?? "");

  const chars = props.charset.split("");
  const rows: string[][] = [];
  for (let i = 0; i < chars.length; i += 3) rows.push(chars.slice(i, i + 3));

  const press = (c: string) => setValue((v) => (v.length >= props.maxLength ? v : v + c));
  const back = () => setValue((v) => v.slice(0, -1));

  return React.createElement(PanelSection, { title: props.title },
    React.createElement(PanelSectionRow, null,
      React.createElement("div", {
        style: {
          fontFamily: "monospace", fontSize: 26, letterSpacing: 1,
          padding: "10px 6px", minHeight: 34, wordBreak: "break-all",
          background: "rgba(0,0,0,0.25)", borderRadius: 4,
        },
      }, value || "\u2014")
    ),
    props.error ? React.createElement(PanelSectionRow, null,
      React.createElement("div", { style: { color: "#ef4444", fontSize: 12 } }, props.error)
    ) : null,
    ...rows.map((row, i) => React.createElement(PanelSectionRow, { key: `row-${i}` },
      React.createElement(Focusable, { "flow-children": "row", style: { display: "flex", gap: 6 } } as any,
        ...row.map((c) => React.createElement(DialogButton, {
          key: c, onClick: () => press(c), style: { flex: 1, minHeight: 44, fontSize: 18 },
        }, c)),
        i === rows.length - 1 ? React.createElement(DialogButton, {
          onClick: back, disabled: !value, style: { flex: 1, minHeight: 44, fontSize: 18 },
        }, "\u232b") : null
      )
    )),
    React.createElement(PanelSectionRow, null,
      React.createElement(Focusable, { "flow-children": "row", style: { display: "flex", gap: 6 } } as any,
        React.createElement(DialogButton, { onClick: props.onCancel, style: { flex: 1 } }, "Cancel"),
        React.createElement(DialogButton, {
          onClick: () => props.onConfirm(value), disabled: !value, style: { flex: 1 },
        }, "OK")
      )
    )
  );
}

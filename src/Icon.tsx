import React from "react";

/**
 * Decky renders `icon` as-is in the Quick Access plugin list, so it must be a
 * real element. Uses `currentColor` so it follows the Steam theme.
 */
export function RemoteStartIcon({ size = 24 }: { size?: number }) {
  return React.createElement(
    "svg",
    {
      width: size,
      height: size,
      viewBox: "0 0 24 24",
      fill: "none",
      xmlns: "http://www.w3.org/2000/svg",
      "aria-hidden": true,
      focusable: false,
      style: { display: "block" },
    },
    React.createElement("rect", {
      x: 1.9,
      y: 3.9,
      width: 15.6,
      height: 11.2,
      rx: 1.7,
      stroke: "currentColor",
      strokeWidth: 1.6,
    }),
    React.createElement("path", {
      d: "M9.7 15.1v3.2",
      stroke: "currentColor",
      strokeWidth: 1.6,
      strokeLinecap: "round",
    }),
    React.createElement("path", {
      d: "M6.6 18.9h6.2",
      stroke: "currentColor",
      strokeWidth: 1.6,
      strokeLinecap: "round",
    }),
    // power glyph
    React.createElement("path", {
      d: "M12.1 7a2.9 2.9 0 1 1-4.8 0",
      stroke: "currentColor",
      strokeWidth: 1.6,
      strokeLinecap: "round",
    }),
    React.createElement("path", {
      d: "M9.7 5.9v3.3",
      stroke: "currentColor",
      strokeWidth: 1.6,
      strokeLinecap: "round",
    }),
    // remote-wake signal
    React.createElement("path", {
      d: "M19.3 5.1a3.7 3.7 0 0 1 0 5.2",
      stroke: "currentColor",
      strokeWidth: 1.6,
      strokeLinecap: "round",
      opacity: 0.85,
    }),
    React.createElement("path", {
      d: "M21.6 3a6.9 6.9 0 0 1 0 9.4",
      stroke: "currentColor",
      strokeWidth: 1.6,
      strokeLinecap: "round",
      opacity: 0.5,
    })
  );
}

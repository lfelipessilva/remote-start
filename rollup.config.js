import commonjs from "@rollup/plugin-commonjs";
import resolve from "@rollup/plugin-node-resolve";
import typescript from "@rollup/plugin-typescript";

export default {
  input: "src/index.tsx",
  output: {
    file: "dist/index.js",
    format: "iife",
    name: "WakePc",
    globals: {
      react: "SP_REACT",
      "react-dom": "SP_REACTDOM",
      "@decky/manifest": "_manifest",
    },
  },
  external: ["react", "react-dom", "@decky/manifest"],
  plugins: [resolve(), commonjs(), typescript({ tsconfig: "./tsconfig.json" })],
};
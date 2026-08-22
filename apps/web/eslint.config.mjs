import { FlatCompat } from "@eslint/eslintrc";
import { fileURLToPath } from "node:url";
import path from "node:path";
const __filename = fileURLToPath(import.meta.url);
const compat = new FlatCompat({ baseDirectory: path.dirname(__filename) });
const config = [...compat.extends("next/core-web-vitals", "next/typescript"), { ignores: [".next/**", "node_modules/**", "coverage/**", "next-env.d.ts"] }, { rules: { "@next/next/no-img-element": "off" } }];
export default config;

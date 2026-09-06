// Root ESLint 9 flat config: delegates to the per-package configs so linting
// works whether it is run from /app, /app/frontend or /app/wa-service.
import frontendConfig from "./frontend/eslint.config.js";
import waServiceConfig from "./wa-service/eslint.config.js";

const prefix = (configs, dir) =>
  configs.map((c) => {
    const out = { ...c };
    if (c.files) out.files = c.files.map((f) => `${dir}/${f}`);
    if (c.ignores) out.ignores = c.ignores.map((f) => `${dir}/${f}`);
    if (!c.files && !c.ignores) out.files = [`${dir}/**/*.{js,jsx,mjs,cjs}`];
    return out;
  });

export default [
  {
    ignores: [
      "**/node_modules/**",
      "frontend/build/**",
      ".emergent/**",
      "backend/**",
      "tests/**",
      "deploy/**",
    ],
  },
  ...prefix(frontendConfig, "frontend"),
  ...prefix(waServiceConfig, "wa-service"),
];

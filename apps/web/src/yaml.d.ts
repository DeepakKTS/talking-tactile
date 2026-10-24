// config/*.yaml is turned into a JSON module at build time by the yamlConfig plugin in
// vite.config.ts. Its shape is checked at runtime by the loaders in src/shared/config.ts.
declare module "*.yaml" {
  const data: unknown;
  export default data;
}

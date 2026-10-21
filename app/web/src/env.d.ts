// Build-time settings read from the repo-root .env (only VITE_* names reach the client).
interface ImportMetaEnv {
  readonly VITE_ORG_NAME?: string;
}

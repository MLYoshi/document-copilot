// Field names mirror the backend contract exactly (snake_case) — no camelCase mapping layer.

export interface UserPublic {
  id: string; // UUID string from the backend
  email: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string; // "bearer"
}

export interface CredentialsPayload {
  email: string;
  password: string;
}

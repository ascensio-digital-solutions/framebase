import { webcrypto } from "node:crypto";

const { subtle } = webcrypto;

/** Refresh the session this long before it expires. */
const SESSION_SKEW_MS = 60_000;

export class CloudApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "CloudApiError";
  }
}

export interface CloudClientOptions {
  baseUrl: string;
  pairingSecret: string;
  deviceId: string;
  /** Least privilege: browsing needs only `library.read`. */
  scopes?: string[];
  fetchImpl?: typeof fetch;
  now?: () => number;
}

export interface BootstrapEntity {
  entityType: string;
  entityId: string;
  revision: number;
  payload: Record<string, unknown>;
}

interface Session {
  token: string;
  expiresAtMs: number;
}

const b64url = (bytes: ArrayBuffer | Uint8Array) =>
  Buffer.from(bytes as Uint8Array).toString("base64url");

/**
 * Server-side client for the Framebase Cloudflare API. It enrolls this server as a device with an
 * ephemeral ECDSA key (the Worker has no session-refresh endpoint, so a new hourly session is minted by
 * repeating the signed challenge) and attaches the session token to every request. Credentials never
 * leave the server process.
 */
export class CloudClient {
  readonly #opts: Required<Omit<CloudClientOptions, "fetchImpl" | "now">> & {
    fetchImpl: typeof fetch;
    now: () => number;
  };
  #keys?: Promise<webcrypto.CryptoKeyPair>;
  #session?: Session;
  #inflight?: Promise<string>;

  constructor(options: CloudClientOptions) {
    this.#opts = {
      scopes: ["library.read"],
      fetchImpl: fetch,
      now: Date.now,
      ...options,
      baseUrl: options.baseUrl.replace(/\/+$/, ""),
    };
  }

  async #post(
    path: string,
    body: unknown,
    headers: Record<string, string> = {},
  ): Promise<Response> {
    return this.#opts.fetchImpl(`${this.#opts.baseUrl}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json", ...headers },
      body: JSON.stringify(body),
    });
  }

  async #failure(res: Response, context: string): Promise<CloudApiError> {
    let code = "CLOUD_ERROR";
    let message = `${context} failed with HTTP ${res.status}`;
    try {
      const data = (await res.json()) as { error?: { code?: string; message?: string } };
      if (data.error?.code) code = data.error.code;
      if (data.error?.message) message = `${context}: ${data.error.message}`;
    } catch {
      /* non-JSON error body */
    }
    return new CloudApiError(res.status, code, message);
  }

  async #enroll(): Promise<string> {
    this.#keys ??= subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, false, [
      "sign",
      "verify",
    ]);
    const keys = await this.#keys;
    const publicKey = b64url(await subtle.exportKey("spki", keys.publicKey));
    const { deviceId, scopes, pairingSecret } = this.#opts;

    const challengeRes = await this.#post(
      "/v1/auth/enroll/challenge",
      { deviceId, deviceName: "Framebase Web Studio", publicKey, scopes },
      { "X-Pairing-Credential": pairingSecret },
    );
    if (!challengeRes.ok) throw await this.#failure(challengeRes, "Device enrollment challenge");
    const { challengeId, challenge } = (await challengeRes.json()) as {
      challengeId: string;
      challenge: string;
    };

    const payload = new TextEncoder().encode(`${challengeId}.${deviceId}.${challenge}`);
    const signature = b64url(
      await subtle.sign({ name: "ECDSA", hash: "SHA-256" }, keys.privateKey, payload),
    );
    const completeRes = await this.#post("/v1/auth/enroll/complete", { challengeId, signature });
    if (!completeRes.ok) throw await this.#failure(completeRes, "Device enrollment");
    const { token, expiresAt } = (await completeRes.json()) as { token: string; expiresAt: string };

    this.#session = { token, expiresAtMs: Date.parse(expiresAt) };
    return token;
  }

  /** Returns a valid session token, enrolling or refreshing at most once at a time. */
  async #token(forceRefresh = false): Promise<string> {
    const s = this.#session;
    if (!forceRefresh && s && s.expiresAtMs - SESSION_SKEW_MS > this.#opts.now()) return s.token;
    this.#inflight ??= this.#enroll().finally(() => {
      this.#inflight = undefined;
    });
    return this.#inflight;
  }

  /** Authenticated GET. A 401 triggers one re-enrollment and retry. */
  async get(path: string): Promise<Response> {
    const send = async (token: string) =>
      this.#opts.fetchImpl(`${this.#opts.baseUrl}${path}`, {
        headers: { authorization: `Bearer ${token}` },
      });
    let res = await send(await this.#token());
    if (res.status === 401) {
      await res.body?.cancel();
      res = await send(await this.#token(true));
    }
    return res;
  }

  /** Reads the entire catalog snapshot, following pagination. */
  async fetchCatalog(): Promise<{ entities: BootstrapEntity[]; watermarkRevision: number }> {
    const entities: BootstrapEntity[] = [];
    let watermarkRevision = 0;
    let cursor: string | null = "0";
    let first = true;
    while (cursor !== null) {
      const res = await this.get(
        `/v1/catalog/bootstrap?cursor=${encodeURIComponent(cursor)}&limit=500`,
      );
      if (!res.ok) throw await this.#failure(res, "Catalog bootstrap");
      const page = (await res.json()) as {
        watermarkRevision: number;
        entities: BootstrapEntity[];
        nextCursor: string | null;
      };
      if (first) watermarkRevision = page.watermarkRevision;
      first = false;
      entities.push(...page.entities);
      cursor = page.nextCursor;
    }
    return { entities, watermarkRevision };
  }

  /** Streams a cached derivative (thumbnail/preview) for an asset. Caller handles non-OK responses. */
  fetchVariant(assetId: string, variant: string): Promise<Response> {
    return this.get(
      `/v1/assets/${encodeURIComponent(assetId)}/variants/${encodeURIComponent(variant)}`,
    );
  }
}

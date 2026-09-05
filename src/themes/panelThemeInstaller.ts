import type { ThemeInstallRequest } from "./types";

export interface ThemeInstallResult {
  themeId: string;
  themeName: string;
  version: string;
  transaction: string;
}

export interface ThemeInstallHost {
  prepareRemote(themeId: string, expectedVersion: string): Promise<unknown>;
  commit(transaction: string): Promise<unknown>;
  discard(catalogId: string): Promise<unknown>;
  rollback(transaction: string): Promise<unknown>;
  recoveries(): Promise<unknown>;
  acknowledge(transaction: string): Promise<unknown>;
}

export interface ThemeInstallRecovery {
  transaction: string;
  themeName: string;
  previousVersion: string | null;
}

export class ThemeInstallError extends Error {
  constructor(readonly code: string, message: string) {
    super(message);
    this.name = "ThemeInstallError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

export class PanelThemeInstaller {
  constructor(private readonly host: ThemeInstallHost) {}

  async prepare(source: ThemeInstallRequest): Promise<ThemeInstallResult> {
    const catalogId = source.catalogId;
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(catalogId)) {
      throw new ThemeInstallError("unsupported_source", "Theme install source is not permitted");
    }
    if (
      source.kind !== "official-remote"
      || source.channelId !== "panel-pages-v1"
      || !/^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$/.test(source.expectedVersion)
    ) {
      throw new ThemeInstallError("unsupported_source", "Theme install source is not permitted");
    }
    const response = await this.host.prepareRemote(source.catalogId, source.expectedVersion);
    if (!isRecord(response) || typeof response.ok !== "boolean" || !nonEmptyString(response.code)) {
      throw new ThemeInstallError("malformed_response", "Panel returned an invalid theme install result");
    }
    if (!response.ok) {
      throw new ThemeInstallError(response.code, "Theme package installation failed");
    }
    if (
      response.code !== "prepared"
      || response.theme_id !== catalogId
      || !nonEmptyString(response.theme_name)
      || !nonEmptyString(response.version)
      || !nonEmptyString(response.transaction)
      || !/^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/.test(response.version)
      || (source.kind === "official-remote" && response.version !== source.expectedVersion)
    ) {
      throw new ThemeInstallError("malformed_response", "Panel returned an invalid theme install result");
    }
    return {
      themeId: catalogId,
      themeName: response.theme_name,
      version: response.version,
      transaction: response.transaction,
    };
  }

  async commit(transaction: string): Promise<void> {
    await this.finish("commit", transaction, "committed");
  }

  async discardReceipt(catalogId: string): Promise<void> {
    const response = await this.host.discard(catalogId);
    if (!isRecord(response) || typeof response.ok !== "boolean" || !nonEmptyString(response.code)) {
      throw new ThemeInstallError(
        "malformed_response",
        "Panel returned an invalid theme receipt discard result",
      );
    }
    if (!response.ok) {
      throw new ThemeInstallError(response.code, "Theme receipt discard failed");
    }
    if (response.code !== "discarded" && response.code !== "absent") {
      throw new ThemeInstallError(
        "malformed_response",
        "Panel returned an invalid theme receipt discard result",
      );
    }
  }

  async rollback(transaction: string): Promise<void> {
    await this.finish("rollback", transaction, "rolled_back");
  }

  async acknowledgeRollback(transaction: string): Promise<void> {
    await this.finish("acknowledge", transaction, "acknowledged");
  }

  async pendingRecoveries(): Promise<ThemeInstallRecovery[]> {
    const response = await this.host.recoveries();
    if (
      isRecord(response)
      && response.ok === false
      && nonEmptyString(response.code)
    ) {
      throw new ThemeInstallError(response.code, "Panel theme recovery is blocked");
    }
    if (
      !isRecord(response)
      || response.ok !== true
      || response.code !== "ready"
      || !Array.isArray(response.recoveries)
    ) {
      throw new ThemeInstallError("malformed_response", "Panel returned invalid theme recoveries");
    }
    return response.recoveries.map((value) => {
      if (
        !isRecord(value)
        || !nonEmptyString(value.transaction)
        || !nonEmptyString(value.theme_name)
        || (
          value.previous_version !== null
          && (!nonEmptyString(value.previous_version)
            || !/^v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/.test(value.previous_version))
        )
      ) {
        throw new ThemeInstallError("malformed_response", "Panel returned an invalid theme recovery");
      }
      return {
        transaction: value.transaction,
        themeName: value.theme_name,
        previousVersion: value.previous_version,
      };
    });
  }

  private async finish(
    operation: "commit" | "rollback" | "acknowledge",
    transaction: string,
    expectedCode: string,
  ): Promise<void> {
    if (!nonEmptyString(transaction)) {
      throw new ThemeInstallError("invalid_transaction", "Theme transaction is invalid");
    }
    const response = await this.host[operation](transaction);
    if (!isRecord(response) || typeof response.ok !== "boolean" || !nonEmptyString(response.code)) {
      throw new ThemeInstallError("malformed_response", "Panel returned an invalid theme transaction result");
    }
    if (!response.ok) {
      throw new ThemeInstallError(response.code, `Theme package ${operation} failed`);
    }
    if (response.code !== expectedCode) {
      throw new ThemeInstallError("malformed_response", "Panel returned an invalid theme transaction result");
    }
  }
}

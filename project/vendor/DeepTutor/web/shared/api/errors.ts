import zhMessages from "@/locales/zh/app.json";

export type AppErrorScope =
  | "turn"
  | "session"
  | "runtime"
  | "settings"
  | "network";

export interface AppError {
  code: string;
  message: string;
  retryable: boolean;
  scope: AppErrorScope;
  correlationId?: string;
  status?: number;
}

export class ApiError extends Error {
  readonly appError: AppError;

  constructor(appError: AppError, options?: ErrorOptions) {
    super(translateApiMessage(appError.message), options);
    this.name = "ApiError";
    this.appError = appError;
  }

  get code(): string {
    return this.appError.code;
  }

  get retryable(): boolean {
    return this.appError.retryable;
  }

  get correlationId(): string | undefined {
    return this.appError.correlationId;
  }

  get status(): number | undefined {
    return this.appError.status;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/** 保留结构化原始错误，仅将可展示的已知消息按中文词条显示。 */
export function translateApiMessage(message: string): string {
  const messages: Record<string, string> = zhMessages;
  const t = (value: string) => messages[value] ?? value;
  const status=message.match(/^(\d{3}) (.+)$/);
  return status ? `${status[1]} ${t(status[2])}` : String(t(message));
}

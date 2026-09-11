/**
 * Production-grade Type-Safe HTTP Client with Zod Validation
 * and AbortController Timeout Handling.
 */

import { z } from "zod";

export interface RequestOptions extends RequestInit {
  timeoutMs?: number;
}

export async function fetchValidated<TSchema extends z.ZodTypeAny>(
  url: string,
  schema: TSchema,
  options: RequestOptions = {}
): Promise<z.infer<TSchema>> {
  const { timeoutMs = 8000, ...fetchOptions } = options;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      ...fetchOptions,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...fetchOptions.headers,
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP Error ${response.status}: ${response.statusText}`);
    }

    const rawData: unknown = await response.json();
    const parseResult = schema.safeParse(rawData);

    if (!parseResult.success) {
      console.error("[ZodValidationError]", parseResult.error.format());
      throw new Error(`Schema validation failed: ${parseResult.error.message}`);
    }

    return parseResult.data;
  } catch (error: unknown) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error(`Request timed out after ${timeoutMs}ms: ${url}`);
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

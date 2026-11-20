export const functionIcons: [string, [string,string][]][];
export const functionIconIds: string[];
export function inferFunctionIcon(label: unknown): string;
export function functionIconFor(label: unknown, override?: string): string;
export function resolveFunctionIcon(id: string | undefined): string;
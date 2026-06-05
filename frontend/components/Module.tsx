"use client";

import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";

export function Module({
  title,
  index = 0,
  right,
  children,
}: {
  title: string;
  index?: number;
  right?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="module" style={{ animationDelay: `${index * 45}ms` }}>
      <div className="module-head">
        <span>
          <span className="tick">▸ </span>
          {title}
        </span>
        {right ? <span>{right}</span> : null}
      </div>
      {children}
    </section>
  );
}

// Wrap a module's data fetch with loading/error states so each panel is independent.
export function useEndpoint<T>(key: unknown[], fn: () => Promise<T>, enabled = true) {
  return useQuery({ queryKey: key, queryFn: fn, enabled });
}

export function Loading() {
  return <div className="loading">loading…</div>;
}
export function ErrBox({ msg }: { msg: string }) {
  return <div className="errbox">error · {msg}</div>;
}

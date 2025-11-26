"use client";

import { Streamdown } from "streamdown";

type Props = {
  content: string;
};

export default function ReviewPanel({ content }: Props) {
  if (!content) {
    return (
      <div
        style={{
          padding: 12,
          borderRadius: 8,
          border: '1px solid #ddd',
          background: '#fafafa',
          minHeight: 220,
          color: '#6b7280',
          fontSize: 14,
        }}
      >
        Results will stream here…
      </div>
    );
  }
  return (
    <div style={{
      padding: 12,
      borderRadius: 8,
      border: '1px solid #ddd',
      background: '#fafafa',
      minHeight: 220,
    }}>
      <Streamdown className="prose max-w-none">
        {content}
      </Streamdown>
    </div>
  );
}

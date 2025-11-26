"use client";

type Props = {
  value: number; // 0..100
};

export default function ProgressBar({ value }: Props) {
  const pct = Math.max(0, Math.min(100, Math.floor(value)));
  return (
    <div style={{ width: '100%', background: '#eee', borderRadius: 6, height: 10 }}>
      <div
        style={{
          width: `${pct}%`,
          height: '100%',
          background: '#0ea5e9',
          borderRadius: 6,
          transition: 'width 150ms linear',
        }}
      />
    </div>
  );
}


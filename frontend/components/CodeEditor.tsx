"use client";

import { useState } from 'react';

type Props = {
  initial?: string;
  onRun: (code: string) => void;
  disabled?: boolean;
};

export default function CodeEditor({ initial, onRun, disabled }: Props) {
  const [code, setCode] = useState(initial ?? 'def f(x):\n    return eval(x)\n');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <textarea
        value={code}
        onChange={(e) => setCode(e.target.value)}
        spellCheck={false}
        style={{
          width: '100%',
          height: 220,
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
          fontSize: 14,
          padding: 12,
          borderRadius: 8,
          border: '1px solid #ddd',
        }}
      />
      <div>
        <button
          onClick={() => onRun(code)}
          disabled={disabled}
          style={{
            padding: '8px 12px',
            background: disabled ? '#94a3b8' : '#2563eb',
            color: 'white',
            borderRadius: 6,
            border: 'none',
            cursor: disabled ? 'not-allowed' : 'pointer',
          }}
        >
          {disabled ? 'Running…' : 'Run Review'}
        </button>
      </div>
    </div>
  );
}


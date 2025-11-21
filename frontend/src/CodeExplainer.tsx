import { useCopilotAction, useCopilotReadable } from "@copilotkit/react-core";
import { useState } from "react";

export default function CodeExplainer() {
  const [code, setCode] = useState("");
  const [analysis, setAnalysis] = useState<string>("");

  useCopilotReadable({
    description: "The user's code to analyze",
    value: code,
  });

  useCopilotAction({
    name: "explainCode",
    description: "Analyze and explain the provided code",
    parameters: [
      {
        name: "code",
        type: "string",
        description: "The code to analyze",
        required: true,
      },
    ],
    handler: async ({ code }) => {
      // This will be called by the agent
      setAnalysis("Analyzing...");
      // The actual analysis happens on the backend
      return { success: true };
    },
  });

  return (
    <div
      style={{
        padding: "20px",
        height: "100vh",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <h1>Code Explanation Agent</h1>

      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          gap: "10px",
        }}
      >
        <label htmlFor="code-input">
          <strong>Paste your code here:</strong>
        </label>

        <textarea
          id="code-input"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)"
          style={{
            flex: 1,
            fontFamily: "monospace",
            fontSize: "14px",
            padding: "10px",
            borderRadius: "4px",
            border: "1px solid #ccc",
            resize: "none",
          }}
        />

        {analysis && (
          <div
            style={{
              padding: "10px",
              backgroundColor: "#f0f0f0",
              borderRadius: "4px",
              fontSize: "14px",
            }}
          >
            {analysis}
          </div>
        )}
      </div>

      <div style={{ marginTop: "20px", fontSize: "12px", color: "#666" }}>
        <p>
          💡 <strong>How to use:</strong>
        </p>
        <ul>
          <li>Paste code above</li>
          <li>Open chat sidebar →</li>
          <li>Ask: "Explain this code"</li>
          <li>Ask: "What issues do you see?"</li>
          <li>Ask: "Suggest improvements"</li>
        </ul>
      </div>
    </div>
  );
}

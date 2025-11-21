import { CopilotKit } from "@copilotkit/react-core";
import { CopilotSidebar } from "@copilotkit/react-ui";
import "@copilotkit/react-ui/styles.css";
import CodeExplainer from "./CodeExplainer";

function App() {
  return (
    <CopilotKit
      runtimeUrl="http://localhost:8000/explain"
      agent="code_explanation_agent"
    >
      <CopilotSidebar
        defaultOpen={true}
        labels={{
          title: "Code Explanation Agent",
          initial:
            "Hi! Paste your code and I'll explain it. I can also answer follow-up questions!",
        }}
      >
        <CodeExplainer />
      </CopilotSidebar>
    </CopilotKit>
  );
}

export default App;

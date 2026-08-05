import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { PipecatClientProvider, PipecatClientAudio } from "@pipecat-ai/client-react";
import { client } from "./jarvisClient";
import App from "./App.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PipecatClientProvider client={client}>
      <App />
      <PipecatClientAudio />
    </PipecatClientProvider>
  </StrictMode>,
);

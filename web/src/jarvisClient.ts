import { PipecatClient } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";
import { installMicConstraints } from "./micConstraints";

// A1 capture hardening (voice isolation plan): echo cancellation + browser
// noise suppression + auto gain control on every mic acquisition. Must run
// before the transport's internal getUserMedia call.
installMicConstraints();

export const client = new PipecatClient({
  transport: new SmallWebRTCTransport(),
  enableMic: true,
  callbacks: { /* wired in components via hooks where possible */ },
});

export const connect = () =>
  client.connect({ webrtcRequestParams: { endpoint: "http://localhost:7860/api/offer" } });

export const disconnect = () => client.disconnect();

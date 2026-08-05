import { PipecatClient } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";

export const client = new PipecatClient({
  transport: new SmallWebRTCTransport(),
  enableMic: true,
  callbacks: { /* wired in components via hooks where possible */ },
});

export const connect = () =>
  client.connect({ webrtcRequestParams: { endpoint: "http://localhost:7860/api/offer" } });

export const disconnect = () => client.disconnect();

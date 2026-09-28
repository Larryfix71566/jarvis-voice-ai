import { PipecatClient } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";
import { installMicConstraints } from "./micConstraints";
import { authHeaders, BOT_OFFER_URL } from "./api";

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
  client.connect({
    webrtcRequestParams: {
      endpoint: BOT_OFFER_URL,
      headers: authHeaders(),
    },
  });

export const disconnect = () => client.disconnect();

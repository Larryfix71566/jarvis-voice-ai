import Transcript from "./Transcript";

interface Props {
  open: boolean;
  onClose: () => void;
}

/** Slide-in transcript history — voice-first UI, text on demand. */
export default function TranscriptDrawer({ open, onClose }: Props) {
  return (
    <aside className={open ? "drawer drawer-open" : "drawer"} aria-hidden={!open}>
      <div className="drawer-head">
        <span className="panel-title">Transcript</span>
        <button type="button" className="btn" onClick={onClose}>
          Close (T)
        </button>
      </div>
      <div className="drawer-body">
        <Transcript />
      </div>
    </aside>
  );
}

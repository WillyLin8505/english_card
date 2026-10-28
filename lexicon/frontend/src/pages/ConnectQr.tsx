import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { ErrorBox, useLoad } from "../ui";

type Info = { default_url: string; lan_url: string | null; has_key: boolean };
const SHOW_SECONDS = 30;

export default function ConnectQr() {
  const info = useLoad<Info>("/admin/connect-qr/info", []);
  const [which, setWhich] = useState<"public" | "lan">("public");
  const [src, setSrc] = useState<string | null>(null);
  const [left, setLeft] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const hide = () => {
    if (timer.current) window.clearInterval(timer.current);
    timer.current = null;
    setLeft(0);
    setSrc((old) => {
      if (old) URL.revokeObjectURL(old);
      return null;
    });
  };
  useEffect(() => hide, []);

  const show = async () => {
    hide();
    setError(null);
    const d = info.data;
    const url = which === "lan" && d?.lan_url ? d.lan_url : d?.default_url ?? "https://api.willylinai.com/tag";
    try {
      const blob = await api.blob(`/admin/connect-qr.png?url=${encodeURIComponent(url)}`);
      setSrc(URL.createObjectURL(blob));
      setLeft(SHOW_SECONDS);
      timer.current = window.setInterval(() => {
        setLeft((n) => {
          if (n <= 1) {
            window.setTimeout(hide, 0);
            return 0;
          }
          return n - 1;
        });
      }, 1000);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="page">
      <h1>連線 QR code</h1>
      <p>給 iPad 掃：App → 設定 → 進階設定 → 照片辨識連線 → 掃描 QR code。</p>
      <p><strong>圖裡有金鑰，勿截圖外傳。</strong>只能在這台電腦上開啟；{SHOW_SECONDS} 秒後自動隱藏。</p>
      {info.error && <ErrorBox error={info.error} onRetry={() => info.reload(true)} />}
      {info.data && !info.data.has_key && <ErrorBox error="找不到辨識金鑰（tagger/.api_key），無法產生 QR code。" />}
      <div style={{ display: "flex", gap: 12, alignItems: "center", margin: "12px 0" }}>
        <label>
          連線網址{" "}
          <select value={which} onChange={(e) => setWhich(e.target.value as "public" | "lan")}>
            <option value="public">{info.data?.default_url ?? "https://api.willylinai.com/tag"}（預設）</option>
            {info.data?.lan_url && <option value="lan">{info.data.lan_url}（本機區網）</option>}
          </select>
        </label>
        <button type="button" className="btn" onClick={show} disabled={!info.data?.has_key}>顯示 QR code</button>
        {src && <button type="button" className="btn" onClick={hide}>立即隱藏</button>}
      </div>
      {error && <ErrorBox error={error} />}
      {src && (
        <div>
          <img src={src} alt="連線 QR code" style={{ width: 360, height: 360, imageRendering: "pixelated", background: "#fff", padding: 12 }} />
          <p>{left} 秒後自動隱藏</p>
        </div>
      )}
    </div>
  );
}

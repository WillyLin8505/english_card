import { Empty, ErrorBox, Loading, fmtTime, useLoad } from "../ui";

type Label = { word: string; pos?: string; cefr?: string; meaning?: string };
type Photo = { id: string; photo_id: string; title: string | null; device: string | null; language: string | null; size_bytes: number; labels: Label[]; uploaded_at: string };
type Result = { total: number; photos: Photo[] };

// 問題回報 #853 (card #724): photos the owner's developer-build phone uploads on its own.
export default function AppPhotos() {
  const data = useLoad<Result>("/app-photos", [], 10000);
  if (data.error) return <ErrorBox error={data.error} />;
  if (!data.data) return <Loading />;
  const { total, photos } = data.data;
  return (
    <div>
      <h1>手機上傳的照片</h1>
      <p className="muted">只有開發版的手機（設有辨識伺服器位址）會在拍照／辨識後自動送來；上架的 App 不會上傳。共 {total} 張。</p>
      {photos.length === 0 ? (
        <Empty>還沒有照片</Empty>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 12 }}>
          {photos.map((p) => (
            <div key={p.id} className="card">
              <img src={`/api/app-photos/${p.id}/file`} alt={p.title ?? p.photo_id} loading="lazy" style={{ width: "100%", height: 200, objectFit: "cover", borderRadius: 8 }} />
              <div className="muted">{p.title || p.photo_id} · {p.language ?? "?"} · {fmtTime(p.uploaded_at)}</div>
              <div>{p.labels.length ? p.labels.map((l) => `${l.word}${l.cefr ? ` (${l.cefr})` : ""}`).join("、") : "（還沒有標籤）"}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

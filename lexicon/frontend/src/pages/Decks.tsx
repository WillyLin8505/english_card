import { useState } from "react";
import { api } from "../api";
import { Empty, ErrorBox, Loading, useLoad, useToast } from "../ui";

// 卡片集／圖片集 (card #323): decks the app lists in 卡片集. Word decks take a pasted
// word list; picture decks are picked from the image library.
type Deck = {
  slug: string; kind: "words" | "photos"; title: string; cefr: string | null; topic: string | null;
  description: string | null; author: string | null; count: number; published: boolean;
  cover_asset_id: number | null;
};
type Pic = { id: number; n: number; words: string; at_level: number };

const LEVELS = ["", "A1", "A2", "B1", "B2", "C1", "C2"];

export default function Decks() {
  const decks = useLoad<{ decks: Deck[] }>("/decks", []);
  const { toast, node } = useToast();
  const [kind, setKind] = useState<"words" | "photos">("photos");
  const [form, setForm] = useState({ slug: "", title: "", cefr: "B1", topic: "", author: "", description: "" });
  const [words, setWords] = useState("");
  const [picked, setPicked] = useState<number[]>([]);
  const [q, setQ] = useState({ word: "", cefr: "" });
  const [pics, setPics] = useState<Pic[]>([]);

  const search = async () => {
    try {
      setPics(await api.get<Pic[]>(`/deck-images?word=${encodeURIComponent(q.word)}&cefr=${q.cefr}&limit=60`));
    } catch (e) {
      toast((e as Error).message, "bad");
    }
  };

  const create = async () => {
    try {
      const list = words.split(/\n/).map((l) => l.trim()).filter(Boolean).map((l) => {
        const [word, pos = "", cefr = ""] = l.split(/[,\t]/).map((x) => x.trim());
        return { word, pos, cefr: cefr || null };
      });
      await api.post("/decks", {
        ...form, kind, cefr: form.cefr || null, published: false,
        cover_asset_id: kind === "photos" ? picked[0] ?? null : null,
        words: kind === "words" ? list : null, asset_ids: kind === "photos" ? picked : null,
      });
      toast("已建立（尚未上架）");
      setPicked([]); setWords("");
      decks.reload(true);
    } catch (e) {
      toast((e as Error).message, "bad");
    }
  };

  const patch = async (slug: string, body: Record<string, unknown>) => {
    try {
      await api.put(`/decks/${slug}`, body);
      decks.reload(true);
    } catch (e) {
      toast((e as Error).message, "bad");
    }
  };

  const remove = async (slug: string) => {
    if (!window.confirm(`刪除集合「${slug}」？已下載的使用者不受影響。`)) return;
    try {
      await api.del(`/decks/${encodeURIComponent(slug)}`);
      decks.reload(true);
    } catch (e) {
      toast((e as Error).message, "bad");
    }
  };

  return (
    <div className="page">
      <h1>卡片集</h1>
      <p className="muted">App 的「卡片集」列出這裡上架的集合；使用者按「加入」就把單字或圖片放進自己的收藏。</p>
      {decks.error ? <ErrorBox error={decks.error} onRetry={decks.reload} /> : !decks.data ? <Loading /> :
        decks.data.decks.length === 0 ? <Empty>還沒有集合</Empty> : (
          <table className="table">
            <thead><tr><th>集合</th><th>種類</th><th>程度</th><th>數量</th><th>作者</th><th>上架</th><th /></tr></thead>
            <tbody>
              {decks.data.decks.map((d) => (
                <tr key={d.slug}>
                  <td>{d.title}<div className="muted">{d.slug}{d.topic ? ` · ${d.topic}` : ""}</div></td>
                  <td>{d.kind === "photos" ? "圖片集" : "單字集"}</td>
                  <td>
                    <select value={d.cefr ?? ""} onChange={(e) => patch(d.slug, { cefr: e.target.value || null })}>
                      {LEVELS.map((l) => <option key={l} value={l}>{l || "—"}</option>)}
                    </select>
                  </td>
                  <td>{d.count}</td>
                  <td>{d.author ?? "—"}</td>
                  <td><input type="checkbox" checked={d.published} onChange={(e) => patch(d.slug, { published: e.target.checked })} /></td>
                  <td><button className="btn btn-small" onClick={() => remove(d.slug)}>刪除</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

      <h2>建立集合</h2>
      <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
        <select value={kind} onChange={(e) => setKind(e.target.value as "words" | "photos")}>
          <option value="photos">圖片集</option><option value="words">單字集</option>
        </select>
        <input placeholder="代號（小寫英數與 -）" value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} />
        <input placeholder="名稱" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <select value={form.cefr} onChange={(e) => setForm({ ...form, cefr: e.target.value })}>
          {LEVELS.map((l) => <option key={l} value={l}>{l || "程度未定"}</option>)}
        </select>
        <input placeholder="主題" value={form.topic} onChange={(e) => setForm({ ...form, topic: e.target.value })} />
        <input placeholder="作者" value={form.author} onChange={(e) => setForm({ ...form, author: e.target.value })} />
      </div>
      <textarea placeholder="簡介" rows={2} style={{ width: "100%", marginTop: 8 }} value={form.description}
        onChange={(e) => setForm({ ...form, description: e.target.value })} />

      {kind === "words" ? (
        <textarea placeholder={"每行一個字：單字, 詞性, 程度\napple, noun, A1"} rows={8} style={{ width: "100%", marginTop: 8 }}
          value={words} onChange={(e) => setWords(e.target.value)} />
      ) : (
        <>
          <div className="row" style={{ gap: 8, marginTop: 8 }}>
            <input placeholder="標籤單字（例：tomato）" value={q.word} onChange={(e) => setQ({ ...q, word: e.target.value })} />
            <select value={q.cefr} onChange={(e) => setQ({ ...q, cefr: e.target.value })}>
              {LEVELS.map((l) => <option key={l} value={l}>{l || "任何程度"}</option>)}
            </select>
            <button className="btn" onClick={search}>從圖片庫找圖</button>
            <span className="muted">已選 {picked.length} 張（第一張當封面）</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(150px,1fr))", gap: 8, marginTop: 8 }}>
            {pics.map((p) => {
              const on = picked.includes(p.id);
              return (
                <label key={p.id} style={{ border: on ? "2px solid #4a90d9" : "1px solid #ddd", borderRadius: 8, padding: 4, cursor: "pointer" }}>
                  <img src={`/api/images/${p.id}/file`} alt={p.words} style={{ width: "100%", height: 100, objectFit: "cover", borderRadius: 6 }} />
                  <div className="muted" style={{ fontSize: 12 }}>{p.words}</div>
                  <input type="checkbox" checked={on}
                    onChange={() => setPicked(on ? picked.filter((x) => x !== p.id) : [...picked, p.id])} /> #{p.id}
                </label>
              );
            })}
          </div>
        </>
      )}
      <p><button className="btn btn-primary" onClick={create}>建立集合</button></p>
      {node}
    </div>
  );
}

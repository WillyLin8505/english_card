import { useEffect, useMemo, useRef, useState } from "react";
import { layoutPins } from "../pinLayout";
import { api } from "../api";
import { ErrorBox, Link, scoreText, TagScores } from "../ui";

export type WordAudio = {
  id: number; lexeme_id: number; pos: string; accent: string | null; default: boolean; status: string;
  source: string; source_page: string | null; license: string | null; attribution: string | null;
  duration_s: number | null; on_disk: boolean;
};

export type WordImage = {
  id: number; sense_id: number; ordinal: number; pos: string; gloss: string | null; native: string | null;
  asset_id: number; width: number; height: number; author: string | null; license_code: string | null;
  license_url: string | null; page_url: string | null; semantic_score: number | null; tag_status: string;
  tags: { word: string; pos: string | null; point: [number, number] | null;
          box: [number, number, number, number] | null; native: string | null;
          score?: number | null }[];
  /** Labels under 80%: listed under the picture, never drawn on it. */
  dropped_tags?: { word: string; pos: string | null; score?: number | null }[] | null;
};

type Tag = WordImage["tags"][number];

let measureCtx: CanvasRenderingContext2D | null = null;
function textWidth(text: string, font: string) {
  measureCtx ??= document.createElement("canvas").getContext("2d");
  if (!measureCtx) return text.length * 7;
  measureCtx.font = font;
  return measureCtx.measureText(text).width;
}

/** Where a label points: its point, or the middle of its area when the
 *  model gave the picture's middle as the point. */
function anchorOf(t: Tag): [number, number] | null {
  if (t.box && (!t.point || (t.point[0] === 0.5 && t.point[1] === 0.5))) {
    return [(t.box[0] + t.box[2]) / 2, (t.box[1] + t.box[3]) / 2];
  }
  return t.point;
}

/** A picture with its AI labels laid out as in the app (pinLayout). */
function TaggedImage({ im, lemma, alt }: { im: WordImage; lemma: string; alt: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const tags = im.tags.filter((t) => anchorOf(t));
  const placed = useMemo(() => {
    if (!size) return [];
    return layoutPins(tags.map((t, i) => {
      const [x, y] = anchorOf(t)!;
      const w = 22 + textWidth(t.word, "600 12px sans-serif")
        + (t.native ? 4 + textWidth(t.native, "11px sans-serif") : 0)
        + 4 + textWidth(scoreText(t.score), "600 10px sans-serif");
      return { id: String(i), anchor: { x: x * size.w, y: y * size.h }, w, h: 22 };
    }), size.w, size.h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size, im.id]);
  const self = (t: Tag) => t.word.toLowerCase() === lemma;
  return (
    <div ref={ref} className="word-image-frame" style={{ aspectRatio: `${im.width} / ${im.height}` }}>
      <img src={`/api/images/${im.asset_id}/file`} alt={alt} />
      {size && (
        <svg className="img-leaders" width={size.w} height={size.h}>
          {tags.map((t, i) => t.box && self(t) && (
            <rect key={`b${i}`} className="img-box" x={t.box[0] * size.w} y={t.box[1] * size.h}
                  width={(t.box[2] - t.box[0]) * size.w} height={(t.box[3] - t.box[1]) * size.h} />
          ))}
          {placed.map((p) => (
            <g key={p.id}>
              {p.leader > 1 && <line x1={p.anchor.x} y1={p.anchor.y} x2={p.joint.x} y2={p.joint.y} />}
              <circle cx={p.anchor.x} cy={p.anchor.y} r={4} />
            </g>
          ))}
        </svg>
      )}
      {placed.map((p) => {
        const t = tags[Number(p.id)];
        return (
          <span key={p.id} className={`img-tag ${self(t) ? "img-tag-self" : ""}`}
                style={{ left: p.badge.l, top: p.badge.t, width: p.badge.r - p.badge.l }}>
            <b>{t.word}</b>
            {t.native && <small>{t.native}</small>}
            <i className="img-tag-score" title="辨識分數">{scoreText(t.score)}</i>
          </span>
        );
      })}
    </div>
  );
}

/** The word's recorded pronunciations and its approved sense pictures, each
 *  with the AI labels where the vision model saw them (as on a learner's
 *  photo in the app). */
export default function WordMedia({ lemma, display, audio, images, imagesPending, onChanged, audioGaps = [] }: {
  lemma: string; display: string; audio: WordAudio[]; images: WordImage[]; imagesPending: number;
  /** 「缺漏：沒有英式真人發音」: the British / American recordings a word lacks. */
  audioGaps?: { target: string | null; message: string }[];
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const act = async (id: number, fn: () => Promise<unknown>) => {
    setBusy(id);
    setErr(null);
    try {
      await fn();
      onChanged();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  };
  return (
    <>
      <section className="card">
        <h2>發音</h2>
        <p className="muted">每個單字 2 個真人發音：英式（預設）＋美式；其他口音為額外選項。</p>
        {audioGaps.length > 0 && (
          <ul className="audio-list">
            {audioGaps.map((g) => (
              <li key={g.target ?? g.message}>
                <span className="pill">{g.target}</span>
                <span className="warn">{g.message}</span>
              </li>
            ))}
          </ul>
        )}
        {audio.length === 0 ? (
          <p className="muted">還沒有真人發音音檔（App 會用系統 TTS）。</p>
        ) : (
          <ul className="audio-list">
            {audio.map((a) => (
              <li key={a.id}>
                <span className="pill">{a.pos}{a.accent ? ` · ${a.accent}` : ""}{a.default ? " · 預設" : ""}</span>
                {a.on_disk && a.status === "ready" ? (
                  <audio controls preload="none" src={`/api/audio/${a.id}/file`} />
                ) : (
                  <span className="warn">檔案未就緒（{a.status}）</span>
                )}
                <small className="muted">
                  {a.license}{a.attribution ? ` · ${a.attribution}` : ""}
                  {a.source_page && <> · <a href={a.source_page} target="_blank" rel="noreferrer">來源 ↗</a></>}
                </small>
                {!a.default && (
                  <button className="btn btn-small" disabled={busy === a.id}
                          onClick={() => act(a.id, () => api.post(`/audio/${a.id}/default`, { lexeme_id: a.lexeme_id }))}>
                    設為預設
                  </button>
                )}
                <button className="btn btn-small" disabled={busy === a.id}
                        onClick={() => act(a.id, () => api.post(`/audio/${a.id}/redownload`))}>
                  重新下載
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="card">
        <h2>詞義圖片</h2>
        {images.length === 0 && <p className="muted">還沒有核准的圖片。</p>}
        {imagesPending > 0 && (
          <p className="warn">
            {imagesPending} 張圖片等待審核，<Link to="/images">到圖片庫核准</Link>後就會出現在這裡。
          </p>
        )}
        <div className="word-images">
          {images.map((im) => (
            <figure key={im.id} className="word-image">
              <TaggedImage im={im} lemma={lemma} alt={`${display}：${im.native ?? im.gloss ?? ""}`} />
              <figcaption>
                <strong>{im.pos} #{im.ordinal + 1}</strong> {im.native ?? ""}
                <span className="muted"> {im.gloss ?? ""}</span>
                <br />
                <small className="muted">
                  {im.tag_status === "done" ? `AI 標籤 ${im.tags.length} 個`
                    : im.tag_status === "failed" ? "AI 標籤失敗"
                    : im.tags.length > 0 ? `AI 標籤 ${im.tags.length} 個（已評分；不足 8 個，稍後再補看）`
                    : "AI 標籤處理中"}
                  {im.semantic_score != null && ` · 語意分數 ${im.semantic_score}`}
                  {" · "}{im.license_code}{im.author ? ` · ${im.author.slice(0, 60)}` : ""}
                  {im.page_url && <> · <a href={im.page_url} target="_blank" rel="noreferrer">來源 ↗</a></>}
                </small>
                <TagScores tags={im.tags} word={lemma} />
                {(im.dropped_tags?.length ?? 0) > 0 && <details>
                  <summary className="muted">未通過的標籤（辨識分數 &lt; 80%）{im.dropped_tags!.length} 個</summary>
                  <TagScores tags={im.dropped_tags} word={lemma} label="未通過的 AI 標籤" />
                </details>}
              </figcaption>
            </figure>
          ))}
        </div>
      </section>
      {err && <ErrorBox error={err} />}
    </>
  );
}

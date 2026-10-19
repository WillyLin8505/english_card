import { api } from "../api";
import { Empty, ErrorBox, Loading, fmtTime, useLoad, useToast } from "../ui";

type Row = {
  slug: string;
  title: string;
  kind: "words" | "photos";
  author: string | null;
  share_status: string;
  words: number;
  images: number;
  downloads: number;
  open_reports: number;
  created_at: string | null;
};
type Stats = { users: number; sharers: number; shared_decks: number; downloads: number; decks: Row[]; latest: Row[]; reported: Row[] };

const STATUS: Record<string, string> = { shared: "上架中", pending: "等安全檢查", private: "已撤回", removed: "圖片未通過", hidden: "後台下架" };

export default function ShareStats() {
  const stats = useLoad<Stats>("/share-stats", [], 10000);
  const { toast, node } = useToast();

  const takedown = async (slug: string, restore: boolean) => {
    try {
      await api.post(`/share-stats/${encodeURIComponent(slug)}/takedown?restore=${restore}`);
      toast(restore ? "已重新上架（會再過安全檢查）" : "已下架");
      stats.reload(true);
    } catch (e) {
      toast((e as Error).message, "bad");
    }
  };

  const table = (rows: Row[]) =>
    rows.length === 0 ? (
      <Empty>沒有資料</Empty>
    ) : (
      <table className="table">
        <thead>
          <tr><th>集合</th><th>作者</th><th>狀態</th><th>單字數</th><th>圖片數</th><th>下載次數</th><th>檢舉</th><th>分享時間</th><th /></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.slug}>
              <td>{r.title}<div className="muted">{r.slug}</div></td>
              <td>{r.author ?? "—"}</td>
              <td>{STATUS[r.share_status] ?? r.share_status}</td>
              <td>{r.words}</td>
              <td>{r.images}</td>
              <td>{r.downloads}</td>
              <td>{r.open_reports || "—"}</td>
              <td>{fmtTime(r.created_at)}</td>
              <td>
                {r.share_status === "shared" || r.share_status === "pending" ? (
                  <button className="btn" onClick={() => takedown(r.slug, false)}>下架</button>
                ) : r.share_status === "hidden" ? (
                  <button className="btn" onClick={() => takedown(r.slug, true)}>重新上架</button>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );

  return (
    <div className="page page-wide">
      {node}
      <header className="page-head">
        <div>
          <h1>分享統計（Shared Decks）</h1>
          <p className="muted">使用者分享到平台的單字集／圖片集：人數、內容數、下載次數、最新分享與被檢舉的集合。</p>
        </div>
      </header>
      {stats.error && <ErrorBox error={stats.error} />}
      {!stats.data ? (
        <Loading />
      ) : (
        <>
          <section className="card form-inline">
            <span>註冊使用者 <b>{stats.data.users}</b></span>
            <span>分享過的人 <b>{stats.data.sharers}</b></span>
            <span>上架中集合 <b>{stats.data.shared_decks}</b></span>
            <span>總下載次數 <b>{stats.data.downloads}</b></span>
          </section>
          <h2>被檢舉的集合</h2>
          {table(stats.data.reported)}
          <h2>最新分享</h2>
          {table(stats.data.latest)}
          <h2>所有分享的集合</h2>
          {table(stats.data.decks)}
        </>
      )}
    </div>
  );
}

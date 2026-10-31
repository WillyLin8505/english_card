import { Fragment, useState } from "react";
import { Empty, ErrorBox, Loading, fmtTime, useLoad } from "../ui";

type U = {
  id: number;
  email: string | null;
  provider: string;
  blocked: boolean;
  joined: string | null;
  albums: string[];
  album_count: number;
  reviews_total: number;
  reviews_7d: number;
  photos_taken: number;
  photos_opened: number;
  app_version: string | null;
  last_seen: string | null;
};
type Overview = { total_users: number; active_7d: number; matched: number; users: U[] };

type Ret = { eligible: number; returned: number; rate: number | null };
type Block = {
  installs: number;
  onboarded: number;
  onboarded_rate: number | null;
  first_photo: number;
  first_review: number;
  first_review_rate: number | null;
  d1: Ret;
  d7: Ret;
  d30: Ret;
};
type Retention = { total: Block; cohorts: (Block & { week_start: string })[]; definition: string; weeks: number };

const pct = (r: number | null) => (r === null ? "—" : `${(r * 100).toFixed(1)}%`);
const ret = (r: Ret) => (r.eligible ? `${pct(r.rate)}（${r.returned}/${r.eligible}）` : "—");

function RetentionBox() {
  const data = useLoad<Retention>("/admin/retention?weeks=12", [], 60000);
  if (data.error) return <ErrorBox error={data.error} />;
  if (!data.data) return <Loading />;
  const t = data.data.total;
  return (
    <section className="card">
      <h2>留存與活化（匿名安裝，近 {data.data.weeks} 週）</h2>
      <p className="muted">
        {data.data.definition}　資料來自 App 的匿名事件（隨機安裝編號，不含個資；使用者可在設定關閉）。
      </p>
      <p>
        新安裝 <b>{t.installs}</b>　引導完成率 <b>{pct(t.onboarded_rate)}</b>　第一次複習率 <b>{pct(t.first_review_rate)}</b>　第 1 天{" "}
        <b>{ret(t.d1)}</b>　第 7 天 <b>{ret(t.d7)}</b>　第 30 天 <b>{ret(t.d30)}</b>
      </p>
      {data.data.cohorts.length === 0 ? (
        <Empty>還沒有安裝事件</Empty>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>世代（週一起）</th>
              <th>新安裝</th>
              <th>引導完成</th>
              <th>第一次拍照</th>
              <th>第一次複習</th>
              <th>第 1 天</th>
              <th>第 7 天</th>
              <th>第 30 天</th>
            </tr>
          </thead>
          <tbody>
            {data.data.cohorts.map((c) => (
              <tr key={c.week_start}>
                <td>{c.week_start}</td>
                <td>{c.installs}</td>
                <td>{pct(c.onboarded_rate)}</td>
                <td>{c.first_photo}</td>
                <td>{pct(c.first_review_rate)}</td>
                <td>{ret(c.d1)}</td>
                <td>{ret(c.d7)}</td>
                <td>{ret(c.d30)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

const COLS: [string, string][] = [
  ["email", "Email"],
  ["album_count", "相片冊"],
  ["reviews_total", "複習累計"],
  ["reviews_7d", "近 7 天複習"],
  ["photos_taken", "拍攝照片"],
  ["photos_opened", "打開照片"],
  ["last_seen", "最後使用"],
];

export default function Users() {
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("last_seen");
  const [desc, setDesc] = useState(true);
  const [open, setOpen] = useState<number | null>(null);
  const data = useLoad<Overview>(`/admin/users?q=${encodeURIComponent(q)}&sort=${sort}&desc=${desc}`, [q, sort, desc], 15000);

  const pick = (k: string) => {
    if (k === sort) setDesc(!desc);
    else {
      setSort(k);
      setDesc(k !== "email");
    }
  };

  return (
    <div className="page page-wide">
      <header className="page-head">
        <div>
          <h1>使用者（Users）</h1>
          <p className="muted">
            只有登入雲端帳號的使用者會回傳數字（相片冊名稱、複習／照片次數），沒登入的人這裡看不到。不含照片與單字內容；除了 email 沒有其他個資。
          </p>
        </div>
      </header>
      <RetentionBox />
      {data.error && <ErrorBox error={data.error} />}
      {!data.data ? (
        <Loading />
      ) : (
        <>
          <section className="card form-inline">
            <span>總人數 <b>{data.data.total_users}</b></span>
            <span>近 7 天活躍 <b>{data.data.active_7d}</b></span>
            <input placeholder="搜尋 email 或相片冊名稱" value={q} onChange={(e) => setQ(e.target.value)} />
          </section>
          {data.data.users.length === 0 ? (
            <Empty>沒有符合的使用者</Empty>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  {COLS.map(([k, label]) => (
                    <th key={k} style={{ cursor: "pointer" }} onClick={() => pick(k)}>
                      {label}{sort === k ? (desc ? " ▼" : " ▲") : ""}
                    </th>
                  ))}
                  <th>版本</th>
                </tr>
              </thead>
              <tbody>
                {data.data.users.map((u) => (
                  <Fragment key={u.id}>
                    <tr style={{ cursor: "pointer" }} onClick={() => setOpen(open === u.id ? null : u.id)}>
                      <td>{u.email ?? `(${u.provider})`}{u.blocked ? " ⛔" : ""}</td>
                      <td>{u.album_count}</td>
                      <td>{u.reviews_total}</td>
                      <td>{u.reviews_7d}</td>
                      <td>{u.photos_taken}</td>
                      <td>{u.photos_opened}</td>
                      <td>{u.last_seen ? fmtTime(u.last_seen) : "—"}</td>
                      <td>{u.app_version ?? "—"}</td>
                    </tr>
                    {open === u.id && (
                      <tr>
                        <td colSpan={8}>
                          <div>註冊：{fmtTime(u.joined)}　登入方式：{u.provider}</div>
                          <div>下載的相片冊（{u.album_count}）：{u.albums.length ? u.albums.join("、") : "—"}</div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
